"""测试 bad Page 复核数据整理，不测试人工版面判断本身。"""

from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.review_bad_page_layouts import (
    apply_manual_annotations,
    build_statistics,
    select_bad_pages,
    validate_annotation,
)


def _sample(sample_id: str, label: str, page_no: int = 1) -> dict[str, object]:
    """构造最小质量抽检记录。"""

    return {
        "sample_id": sample_id,
        "document_id": "doc",
        "relative_path": "data/检验规范/test.pdf",
        "page_no": page_no,
        "parse_method": "text",
        "quality_label": label,
        "error_types": ["missing_text"],
        "text_preview": "preview",
    }


def _annotation(sample_id: str) -> dict[str, object]:
    """构造合法人工版面标注。"""

    return {
        "sample_id": sample_id,
        "layout_type": "table",
        "failure_category": "layout_structure",
        "linear_text_sufficient": False,
        "notes": "人工复核说明",
    }


def test_only_bad_pages_are_selected() -> None:
    payload = {"samples": [_sample("bad", "bad"), _sample("good", "good"), _sample("ok", "acceptable")]}
    assert [item["sample_id"] for item in select_bad_pages(payload)] == ["bad"]


def test_sample_id_and_page_number_are_preserved() -> None:
    payload = {"samples": [_sample("PQ-100", "bad", page_no=123)]}
    review = select_bad_pages(payload)[0]
    assert review["sample_id"] == "PQ-100"
    assert review["page_no"] == 123


@pytest.mark.parametrize("layout_type", ["invalid", ""])
def test_layout_type_enum_is_validated(layout_type: str) -> None:
    annotation = _annotation("PQ-001")
    annotation["layout_type"] = layout_type
    with pytest.raises(ValueError, match="layout_type"):
        validate_annotation(annotation)


def test_failure_category_enum_is_validated() -> None:
    annotation = _annotation("PQ-001")
    annotation["failure_category"] = "invalid"
    with pytest.raises(ValueError, match="failure_category"):
        validate_annotation(annotation)


@pytest.mark.parametrize("value", [None, 0, 1, "false"])
def test_linear_text_sufficient_must_be_bool(value: object) -> None:
    annotation = _annotation("PQ-001")
    annotation["linear_text_sufficient"] = value
    with pytest.raises(TypeError, match="bool"):
        validate_annotation(annotation)


def test_statistics_total_matches_input() -> None:
    reviews = []
    for index in range(3):
        review = select_bad_pages({"samples": [_sample(f"PQ-{index}", "bad")]})[0]
        reviews.append(
            apply_manual_annotations(
                [review], {"annotations": [_annotation(f"PQ-{index}")]}
            )[0]
        )
    statistics = build_statistics(reviews)
    assert statistics["total_bad_pages"] == 3
    assert statistics["structured_layout_pages"] == 3
    assert statistics["by_linear_text_sufficient"]["false"] == 3


def test_source_quality_payload_is_not_modified() -> None:
    payload = {"samples": [_sample("PQ-001", "bad")]}
    original = deepcopy(payload)
    reviews = select_bad_pages(payload)
    apply_manual_annotations(reviews, {"annotations": [_annotation("PQ-001")]})
    assert payload == original
