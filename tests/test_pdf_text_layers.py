"""验证 PDF 文本层可用性检测的页级阈值与文档级分类。"""

from scripts.inventory_pdf_text_layers import (
    MIN_MEANINGFUL_CHARACTERS,
    analyze_text,
    build_summary,
    classify_document,
)


def test_empty_text_is_not_usable() -> None:
    """空白页面应标记为 empty 且不可用。"""

    result = analyze_text(" \n\t", page_no=1)

    assert result["has_usable_text"] is False
    assert result["text_status"] == "empty"
    assert result["non_whitespace_length"] == 0


def test_short_noise_is_not_usable() -> None:
    """页码、标点和短网址等少量噪声不能被视为正常正文。"""

    result = analyze_text("1 . www...", page_no=2)

    assert result["has_usable_text"] is False
    assert result["text_status"] == "too_short"
    assert result["meaningful_character_length"] < MIN_MEANINGFUL_CHARACTERS


def test_normal_text_is_usable() -> None:
    """达到有效字符阈值的普通文本页应标记为 usable。"""

    result = analyze_text("压力容器定期检验应当依据安全技术规范进行现场检查。", page_no=3)

    assert result["has_usable_text"] is True
    assert result["text_status"] == "usable"
    assert result["meaningful_character_length"] >= MIN_MEANINGFUL_CHARACTERS


def test_document_ratio_summary_is_correct() -> None:
    """文档和页数汇总应正确累计可用比例所需的计数。"""

    documents = [
        _document("检验规范", "text", total_pages=10, usable_pages=9),
        _document("球罐标准", "mixed", total_pages=10, usable_pages=5),
    ]

    summary = build_summary(documents)

    assert summary["total_pdf"] == 2
    assert summary["total_pages"] == 20
    assert summary["usable_text_pages"] == 14
    assert summary["non_usable_text_pages"] == 6
    assert summary["by_source_category"]["检验规范"]["usable_text_pages"] == 9


def test_text_document_classification() -> None:
    """至少九成页面可用的文档应归为 text。"""

    assert classify_document(90, 100) == "text"


def test_mixed_document_classification() -> None:
    """可用页比例处于两端阈值之间的文档应归为 mixed。"""

    assert classify_document(50, 100) == "mixed"


def test_no_usable_text_document_classification() -> None:
    """最多一成页面可用的文档应归为 no_usable_text。"""

    assert classify_document(10, 100) == "no_usable_text"


def _document(
    source_category: str,
    document_text_type: str,
    total_pages: int,
    usable_pages: int,
) -> dict[str, object]:
    """创建汇总测试所需的最小文档记录。"""

    return {
        "source_category": source_category,
        "document_text_type": document_text_type,
        "total_pages": total_pages,
        "usable_text_pages": usable_pages,
        "non_usable_text_pages": total_pages - usable_pages,
        "readable": True,
    }
