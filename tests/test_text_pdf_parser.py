"""验证文本型 PDF 到 Page 及 JSONL 的最小解析链路。"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from src.inspection_plan.document_parser import Page, TextPdfParser, TextStatus


def _create_pdf(path: Path, page_texts: list[str | None]) -> None:
    """动态创建极小 PDF；None 表示不插入文字的空白页。"""

    with pymupdf.open() as document:
        for text in page_texts:
            page = document.new_page()
            if text is not None:
                page.insert_text((72, 72), text)
        document.save(path)


def _parse(parser: TextPdfParser, pdf_path: Path) -> list[Page]:
    """使用固定测试元数据解析临时 PDF，减少重复参数。"""

    return parser.parse(
        pdf_path,
        document_id="test_document",
        source_category="球罐标准",
        relative_path=f"data/球罐标准/{pdf_path.name}",
    )


def test_one_page_pdf_generates_one_page_model(tmp_path: Path) -> None:
    """单页文本 PDF 应生成一个统一 Page。"""

    pdf_path = tmp_path / "one-page.pdf"
    _create_pdf(pdf_path, ["One page text"])

    pages = _parse(TextPdfParser(), pdf_path)

    assert len(pages) == 1
    assert pages[0].file_name == pdf_path.name


def test_multiple_pages_keep_order_and_one_based_numbers(tmp_path: Path) -> None:
    """多页输出应保持原始顺序，并把 PyMuPDF 索引转换为 1-based 页码。"""

    pdf_path = tmp_path / "three-pages.pdf"
    _create_pdf(pdf_path, ["First", "Second", "Third"])

    pages = _parse(TextPdfParser(), pdf_path)

    assert [page.page_no for page in pages] == [1, 2, 3]
    assert [page.text.strip() for page in pages] == ["First", "Second", "Third"]


def test_text_page_status_is_success(tmp_path: Path) -> None:
    """任何非空白提取文本都应忠实保留并标记为 success。"""

    pdf_path = tmp_path / "short-text.pdf"
    _create_pdf(pdf_path, ["A"])

    page = _parse(TextPdfParser(), pdf_path)[0]

    assert page.text.strip() == "A"
    assert page.text_status is TextStatus.SUCCESS


def test_blank_page_status_is_empty(tmp_path: Path) -> None:
    """提取成功但没有正文的页面应映射为合法 empty Page。"""

    pdf_path = tmp_path / "blank.pdf"
    _create_pdf(pdf_path, [None])

    page = _parse(TextPdfParser(), pdf_path)[0]

    assert page.text == ""
    assert page.text_status is TextStatus.EMPTY
    assert page.error is None


def test_char_count_matches_extracted_text(tmp_path: Path) -> None:
    """Parser 生成的 Page 字符数必须由最终提取文本自动计算。"""

    pdf_path = tmp_path / "count.pdf"
    _create_pdf(pdf_path, ["Count me"])

    page = _parse(TextPdfParser(), pdf_path)[0]

    assert page.char_count == len(page.text)


def test_jsonl_line_count_matches_pages_and_can_be_loaded(tmp_path: Path) -> None:
    """JSONL 应一页一行、保持顺序，并能逐行重新解析为字典。"""

    pdf_path = tmp_path / "jsonl.pdf"
    output_path = tmp_path / "output" / "pages.jsonl"
    _create_pdf(pdf_path, ["First", None, "Third"])
    parser = TextPdfParser()

    pages = _parse(parser, pdf_path)
    written_count = parser.write_jsonl(pages, output_path)
    lines = output_path.read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in lines]

    assert written_count == len(pages) == len(lines) == 3
    assert [payload["page_no"] for payload in payloads] == [1, 2, 3]
    assert payloads[1]["text_status"] == "empty"


def test_jsonl_keeps_utf8_chinese_without_ascii_escaping(tmp_path: Path) -> None:
    """JSONL 中文应按 UTF-8 原样保存，而不是转换为 Unicode 转义序列。"""

    output_path = tmp_path / "chinese.jsonl"
    page = Page(
        document_id="test_document",
        source_category="球罐标准",
        relative_path="data/球罐标准/test.pdf",
        file_name="test.pdf",
        page_no=1,
        text="测试页面正文。",
        parse_method="text",
        text_status="success",
    )

    TextPdfParser.write_jsonl([page], output_path)
    jsonl_text = output_path.read_text(encoding="utf-8")

    assert "测试页面正文" in jsonl_text
    assert "\\u6d4b" not in jsonl_text


def test_missing_input_has_clear_error(tmp_path: Path) -> None:
    """不存在的输入应在文档级立即给出明确 FileNotFoundError。"""

    missing_path = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError, match="PDF 文件不存在"):
        _parse(TextPdfParser(), missing_path)


def test_single_page_failure_becomes_failed_and_later_pages_continue(
    tmp_path: Path,
) -> None:
    """单页提取异常应生成 failed Page，且不得阻止后续页解析。"""

    pdf_path = tmp_path / "page-failure.pdf"
    _create_pdf(pdf_path, ["First", "Second", "Third"])

    class FailingSecondPageParser(TextPdfParser):
        """仅在第二次提取时抛错，用于验证页面级异常边界。"""

        def __init__(self) -> None:
            """初始化调用计数器，以便稳定触发第二页模拟异常。"""

            self.call_count = 0

        def _extract_text(self, pdf_page: object) -> str:
            """第二次调用模拟提取失败，其他页面走真实文本提取。"""

            self.call_count += 1
            if self.call_count == 2:
                raise RuntimeError("模拟页面提取失败")
            return super()._extract_text(pdf_page)

    pages = _parse(FailingSecondPageParser(), pdf_path)

    assert [page.text_status for page in pages] == [
        TextStatus.SUCCESS,
        TextStatus.FAILED,
        TextStatus.SUCCESS,
    ]
    assert pages[1].error == "RuntimeError: 模拟页面提取失败"
    assert pages[2].text.strip() == "Third"
