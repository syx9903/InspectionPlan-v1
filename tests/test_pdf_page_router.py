"""验证 Page 级 Text/OCR 路由、惰性初始化、范围和统计。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from src.inspection_plan.document_parser import pdf_page_router as router_module
from src.inspection_plan.document_parser import (
    Page,
    ParseMethod,
    PdfOpenError,
    PdfPageRouter,
    TextStatus,
)


def _make_pdf(path: Path, texts: list[str]) -> Path:
    """创建具有指定文本层的极小 PDF 测试夹具。"""

    document = pymupdf.open()
    for text in texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.save(path)
    document.close()
    return path


class FakeOcrParser:
    """按队列结果模拟 OCR 单页 Parser，并记录处理页码。"""

    def __init__(self, outcomes: list[str | Exception] | None = None) -> None:
        self.outcomes = list(outcomes or ["mock ocr text"])
        self.page_numbers: list[int] = []

    def _parse_page(self, pdf_page: Any, **metadata: Any) -> Page:
        """返回 OCR Page；异常对象映射为 failed 并允许下一页继续。"""

        del pdf_page
        self.page_numbers.append(metadata["page_no"])
        outcome = self.outcomes.pop(0) if self.outcomes else "mock ocr text"
        common = {
            key: metadata[key]
            for key in (
                "document_id",
                "source_category",
                "relative_path",
                "file_name",
                "page_no",
            )
        }
        if isinstance(outcome, Exception):
            return Page(
                **common,
                text="",
                parse_method=ParseMethod.OCR,
                text_status=TextStatus.FAILED,
                error=f"{type(outcome).__name__}: {outcome}",
            )
        if not outcome.strip():
            return Page(
                **common,
                text="",
                parse_method=ParseMethod.OCR,
                text_status=TextStatus.EMPTY,
            )
        return Page(
            **common,
            text=outcome,
            parse_method=ParseMethod.OCR,
            text_status=TextStatus.SUCCESS,
        )


def _parse(router: PdfPageRouter, pdf_path: Path, **range_args: Any) -> list[Page]:
    """使用固定合法元数据调用路由器，减少测试样板代码。"""

    return router.parse(
        pdf_path,
        document_id="doc",
        source_category="检验规范",
        relative_path=f"data/检验规范/{pdf_path.name}",
        **range_args,
    )


def test_normal_text_page_routes_to_text(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "text.pdf", ["A" * 20])
    pages = _parse(PdfPageRouter(ocr_parser_factory=lambda: FakeOcrParser()), pdf_path)
    assert pages[0].parse_method is ParseMethod.TEXT


@pytest.mark.parametrize("text", ["", "page 1"])
def test_empty_or_short_noise_routes_to_ocr(tmp_path: Path, text: str) -> None:
    pdf_path = _make_pdf(tmp_path / "short.pdf", [text])
    pages = _parse(PdfPageRouter(ocr_parser_factory=lambda: FakeOcrParser()), pdf_path)
    assert pages[0].parse_method is ParseMethod.OCR


def test_exact_threshold_routes_to_text() -> None:
    assert PdfPageRouter.count_meaningful_characters("中文" + "A1" * 9) == 20


def test_one_pdf_can_produce_text_and_ocr_in_original_order(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "mixed.pdf", ["A" * 20, "short", "B" * 21])
    pages = _parse(PdfPageRouter(ocr_parser_factory=lambda: FakeOcrParser()), pdf_path)
    assert [page.parse_method for page in pages] == [
        ParseMethod.TEXT,
        ParseMethod.OCR,
        ParseMethod.TEXT,
    ]
    assert [page.page_no for page in pages] == [1, 2, 3]


def test_router_opens_pdf_only_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = _make_pdf(tmp_path / "single_open.pdf", ["A" * 20, ""])
    original_open = pymupdf.open
    open_calls = 0

    def counting_open(*args: Any, **kwargs: Any) -> Any:
        """记录路由器打开文档次数，并委托真实 PyMuPDF。"""

        nonlocal open_calls
        open_calls += 1
        return original_open(*args, **kwargs)

    monkeypatch.setattr(router_module.pymupdf, "open", counting_open)
    _parse(PdfPageRouter(ocr_parser_factory=lambda: FakeOcrParser()), pdf_path)
    assert open_calls == 1


def test_ocr_is_initialized_lazily_once_for_multiple_pages(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "scan.pdf", ["", ""])
    calls = 0

    def factory() -> FakeOcrParser:
        nonlocal calls
        calls += 1
        return FakeOcrParser(["one", "two"])

    router = PdfPageRouter(ocr_parser_factory=factory)
    _parse(router, pdf_path)
    assert calls == 1
    assert router.last_run_stats["ocr_initializations"] == 1


def test_text_pdf_does_not_initialize_ocr(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "text.pdf", ["A" * 20, "B" * 20])

    def forbidden_factory() -> FakeOcrParser:
        raise AssertionError("纯文本 PDF 不应初始化 OCR")

    router = PdfPageRouter(ocr_parser_factory=forbidden_factory)
    _parse(router, pdf_path)
    assert router.last_run_stats["ocr_initializations"] == 0


def test_ocr_failure_does_not_stop_later_page(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "fail.pdf", ["", ""])
    fake = FakeOcrParser([RuntimeError("bad page"), "recovered"])
    pages = _parse(PdfPageRouter(ocr_parser_factory=lambda: fake), pdf_path)
    assert [page.text_status for page in pages] == [TextStatus.FAILED, TextStatus.SUCCESS]


def test_jsonl_contains_mixed_parse_methods(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "mixed.pdf", ["A" * 20, ""])
    output_path = tmp_path / "pages.jsonl"
    router = PdfPageRouter(ocr_parser_factory=lambda: FakeOcrParser())
    router.parse_to_jsonl(
        pdf_path,
        output_path,
        document_id="doc",
        source_category="检验规范",
        relative_path="data/检验规范/mixed.pdf",
    )
    records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert [record["parse_method"] for record in records] == ["text", "ocr"]


def test_page_range_preserves_original_page_numbers(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "range.pdf", ["A" * 20] * 5)
    pages = _parse(PdfPageRouter(), pdf_path, start_page=2, end_page=4)
    assert [page.page_no for page in pages] == [2, 3, 4]


@pytest.mark.parametrize(
    ("start_page", "end_page", "error_type"),
    [(0, 1, ValueError), (3, 2, ValueError), (1, 9, ValueError), (True, 2, TypeError)],
)
def test_invalid_page_range(
    tmp_path: Path,
    start_page: Any,
    end_page: Any,
    error_type: type[Exception],
) -> None:
    pdf_path = _make_pdf(tmp_path / "range.pdf", ["A" * 20] * 3)
    with pytest.raises(error_type):
        _parse(PdfPageRouter(), pdf_path, start_page=start_page, end_page=end_page)


def test_missing_document_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _parse(PdfPageRouter(), tmp_path / "missing.pdf")


def test_document_open_error_is_wrapped(tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"not a pdf")
    with pytest.raises(PdfOpenError):
        _parse(PdfPageRouter(), pdf_path)


def test_document_stats_are_correct(tmp_path: Path) -> None:
    pdf_path = _make_pdf(tmp_path / "stats.pdf", ["A" * 20, "", ""])
    fake = FakeOcrParser(["ocr", ""])
    router = PdfPageRouter(ocr_parser_factory=lambda: fake)
    _parse(router, pdf_path)
    assert router.last_run_stats | {"total_seconds": 0.0} == {
        "total_pages": 3,
        "text_pages": 1,
        "ocr_pages": 2,
        "success_pages": 2,
        "empty_pages": 1,
        "failed_pages": 0,
        "ocr_initializations": 1,
        "total_seconds": 0.0,
    }
