"""测试质量抽样辅助逻辑，不伪造人工质量标签。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.sample_page_quality import (
    build_sample_record,
    build_text_preview,
    count_character_types,
    create_sample,
    filter_by_parse_method,
    read_page_jsonl,
)


def _page(page_no: int, method: str, text: str = "正文") -> dict[str, object]:
    """构造辅助脚本需要的最小 Page JSON 对象。"""

    return {
        "document_id": "doc",
        "relative_path": "data/检验规范/test.pdf",
        "page_no": page_no,
        "parse_method": method,
        "text": text,
    }


def test_read_page_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "pages.jsonl"
    path.write_text(json.dumps(_page(1, "text"), ensure_ascii=False) + "\n", encoding="utf-8")
    assert read_page_jsonl(path)[0]["page_no"] == 1


def test_filter_by_parse_method() -> None:
    records = [_page(1, "text"), _page(2, "ocr"), _page(3, "text")]
    assert [item["page_no"] for item in filter_by_parse_method(records, "text")] == [1, 3]


def test_create_sample_count_and_original_page_number(tmp_path: Path) -> None:
    path = tmp_path / "pages.jsonl"
    path.write_text(
        "\n".join(json.dumps(_page(number, "text")) for number in (100, 101, 102)) + "\n",
        encoding="utf-8",
    )
    samples = create_sample(tmp_path, [("mixed_pdf", "pages.jsonl", [101, 102])])
    assert len(samples) == 2
    assert [sample["page_no"] for sample in samples] == [101, 102]


def test_preview_truncation_is_stable() -> None:
    assert build_text_preview("abcdef", 4) == "abcd…"
    assert build_text_preview("abcd", 4) == "abcd"


def test_character_statistics_are_correct() -> None:
    assert count_character_types("中文Ab12，! \n") == {
        "chinese_char_count": 2,
        "english_char_count": 2,
        "digit_char_count": 2,
        "other_visible_char_count": 2,
        "effective_char_count": 6,
        "chinese_ratio": 0.333333,
    }


def test_sample_has_empty_manual_labels() -> None:
    sample = build_sample_record(_page(7, "ocr"), sample_id="PQ-001", source_type="mixed_pdf")
    assert sample["quality_label"] is None
    assert sample["error_types"] == []
    assert sample["notes"] == ""


def test_helpers_do_not_modify_original_record() -> None:
    record = _page(8, "text", "原始正文")
    original = deepcopy(record)
    build_sample_record(record, sample_id="PQ-001", source_type="text_pdf")
    assert record == original


def test_invalid_parse_method_filter_is_rejected() -> None:
    with pytest.raises(ValueError, match="parse_method"):
        filter_by_parse_method([], "unknown")
