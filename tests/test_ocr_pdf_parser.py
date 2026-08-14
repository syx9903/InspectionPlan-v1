"""验证扫描型 PDF 经 mock OCR 转换为 Page 与 JSONL 的正式链路。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from src.inspection_plan.document_parser import (
    DEFAULT_OCR_DPI,
    OcrPdfParser,
    ParseMethod,
    TextStatus,
)


def _create_pdf(path: Path, page_count: int) -> None:
    """动态创建指定空白页数的极小 PDF，不依赖真实法规 fixture。"""

    with pymupdf.open() as document:
        for _ in range(page_count):
            document.new_page(width=200, height=300)
        document.save(path)


def _ocr_line(text: str, confidence: float = 0.99) -> list[object]:
    """创建一条 RapidOCR 兼容的 box、text、confidence 结果。"""

    return [[[0, 0], [10, 0], [10, 5], [0, 5]], text, confidence]


class QueueOcrEngine:
    """按调用顺序返回预设结果或异常，用于隔离真实 OCR 波动。"""

    def __init__(self, responses: list[Any]) -> None:
        """保存逐页响应队列并初始化调用计数。"""

        self.responses = responses
        self.call_count = 0

    def __call__(self, image: bytes) -> tuple[Any, list[float]]:
        """验证收到 PNG，并返回当前页预设响应。"""

        assert image.startswith(b"\x89PNG")
        response = self.responses[self.call_count]
        self.call_count += 1
        if isinstance(response, Exception):
            raise response
        return response, [0.01, 0.0, 0.02]


def _parse(parser: OcrPdfParser, pdf_path: Path) -> list[Any]:
    """使用固定元数据解析临时 PDF，减少测试参数重复。"""

    return parser.parse(
        pdf_path,
        document_id="scan_test",
        source_category="检验规范",
        relative_path=f"data/检验规范/{pdf_path.name}",
    )


def test_single_page_ocr_success() -> None:
    """OCR 返回非空文本时应生成 success Page。"""

    engine = QueueOcrEngine([[_ocr_line("扫描正文")]])
    parser = OcrPdfParser(ocr_engine=engine)

    with pymupdf.open() as document:
        page = document.new_page(width=200, height=300)
        result = parser._parse_page(
            page,
            page_no=1,
            document_id="scan_test",
            source_category="检验规范",
            relative_path="data/检验规范/test.pdf",
            file_name="test.pdf",
        )

    assert result.text == "扫描正文"
    assert result.text_status is TextStatus.SUCCESS
    assert result.parse_method is ParseMethod.OCR


def test_multiple_pages_keep_one_based_order(tmp_path: Path) -> None:
    """多页 OCR 输出必须保持顺序并使用 1-based 页码。"""

    pdf_path = tmp_path / "multiple.pdf"
    _create_pdf(pdf_path, 3)
    engine = QueueOcrEngine(
        [[_ocr_line("第一页")], [_ocr_line("第二页")], [_ocr_line("第三页")]]
    )

    pages = _parse(OcrPdfParser(ocr_engine=engine), pdf_path)

    assert [page.page_no for page in pages] == [1, 2, 3]
    assert [page.text for page in pages] == ["第一页", "第二页", "第三页"]
    assert all(page.parse_method is ParseMethod.OCR for page in pages)


def test_ocr_lines_are_joined_in_return_order(tmp_path: Path) -> None:
    """Page.text 应按 OCR 返回顺序使用换行拼接。"""

    pdf_path = tmp_path / "lines.pdf"
    _create_pdf(pdf_path, 1)
    engine = QueueOcrEngine(
        [[_ocr_line("第一行"), _ocr_line("第二行"), _ocr_line("第三行")]]
    )

    page = _parse(OcrPdfParser(ocr_engine=engine), pdf_path)[0]

    assert page.text == "第一行\n第二行\n第三行"


@pytest.mark.parametrize("empty_result", [None, [], [_ocr_line("")]])
def test_empty_ocr_result_becomes_empty_page(
    tmp_path: Path,
    empty_result: Any,
) -> None:
    """OCR 正常无文字时应生成 empty，而不是 failed Page。"""

    pdf_path = tmp_path / "empty.pdf"
    _create_pdf(pdf_path, 1)

    page = _parse(
        OcrPdfParser(ocr_engine=QueueOcrEngine([empty_result])),
        pdf_path,
    )[0]

    assert page.text == ""
    assert page.text_status is TextStatus.EMPTY
    assert page.error is None


def test_ocr_exception_becomes_failed_and_next_page_continues(tmp_path: Path) -> None:
    """单页 OCR 异常应记录 failed，并继续解析后续页面。"""

    pdf_path = tmp_path / "failure.pdf"
    _create_pdf(pdf_path, 3)
    engine = QueueOcrEngine(
        [[_ocr_line("第一页")], RuntimeError("模拟 OCR 失败"), [_ocr_line("第三页")]]
    )

    pages = _parse(OcrPdfParser(ocr_engine=engine), pdf_path)

    assert [page.text_status for page in pages] == [
        TextStatus.SUCCESS,
        TextStatus.FAILED,
        TextStatus.SUCCESS,
    ]
    assert pages[1].error == "RuntimeError: 模拟 OCR 失败"
    assert pages[2].text == "第三页"


def test_jsonl_has_one_utf8_loadable_line_per_page(tmp_path: Path) -> None:
    """JSONL 应一页一行、中文原样保存，并可逐行重新解析。"""

    pdf_path = tmp_path / "jsonl.pdf"
    output_path = tmp_path / "pages" / "scan.jsonl"
    _create_pdf(pdf_path, 2)
    parser = OcrPdfParser(
        ocr_engine=QueueOcrEngine([[_ocr_line("中文第一页")], [_ocr_line("中文第二页")]])
    )

    pages = parser.parse_to_jsonl(
        pdf_path,
        output_path,
        document_id="scan_test",
        source_category="检验规范",
        relative_path=f"data/检验规范/{pdf_path.name}",
    )
    text = output_path.read_text(encoding="utf-8")
    payloads = [json.loads(line) for line in text.splitlines()]

    assert len(payloads) == len(pages) == 2
    assert "中文第一页" in text
    assert "\\u4e2d" not in text
    assert all(payload["parse_method"] == "ocr" for payload in payloads)


def test_default_dpi_is_200() -> None:
    """构造时未覆盖参数应使用 TASK-002.5 确定的 200 DPI。"""

    parser = OcrPdfParser(ocr_engine=QueueOcrEngine([]))

    assert DEFAULT_OCR_DPI == 200
    assert parser.dpi == 200


@pytest.mark.parametrize("dpi", [0, 71, 601, 1000])
def test_invalid_dpi_is_rejected(dpi: int) -> None:
    """非法 DPI 必须在创建 OCR 引擎前拒绝。"""

    with pytest.raises(ValueError, match="DPI"):
        OcrPdfParser(dpi=dpi, ocr_engine=QueueOcrEngine([]))


def test_missing_pdf_is_document_level_error(tmp_path: Path) -> None:
    """不存在的 PDF 应抛文档级错误，不伪造 failed Page。"""

    missing_path = tmp_path / "missing.pdf"
    parser = OcrPdfParser(ocr_engine=QueueOcrEngine([]))

    with pytest.raises(FileNotFoundError, match="PDF 文件不存在"):
        _parse(parser, missing_path)


def test_ocr_engine_is_initialized_once_and_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一 Parser 解析多页时只能创建一次 OCR 引擎。"""

    pdf_path = tmp_path / "reuse.pdf"
    _create_pdf(pdf_path, 3)
    engine = QueueOcrEngine(
        [[_ocr_line("第一页")], [_ocr_line("第二页")], [_ocr_line("第三页")]]
    )
    initialization_count = 0

    def create_engine() -> QueueOcrEngine:
        """记录引擎工厂调用次数并返回同一个 mock。"""

        nonlocal initialization_count
        initialization_count += 1
        return engine

    monkeypatch.setattr(OcrPdfParser, "_create_ocr_engine", staticmethod(create_engine))
    parser = OcrPdfParser()

    pages = _parse(parser, pdf_path)

    assert len(pages) == 3
    assert initialization_count == 1
    assert engine.call_count == 3
    assert parser.last_run_stats["total_pages"] == 3
