"""验证独立Table/Cell模型的结构、风险、核验状态和Unicode序列化。"""

from __future__ import annotations

import json

import pytest

from src.inspection_plan.document_parser.table_models import (
    BoundingBox,
    CellContentType,
    CellRiskFlag,
    ReviewStatus,
    Table,
    TableCell,
)


def _cell(**overrides: object) -> TableCell:
    """创建一个包含数字风险的最小合法单元格。"""

    values = {
        "row_index": 1,
        "column_index": 1,
        "bbox": BoundingBox(10, 20, 30, 40),
        "raw_text": "⑤⑨",
        "content_type": "numeric",
        "risk_flags": ("numeric_content", "special_symbol"),
        "ocr_confidence": 0.93,
    }
    values.update(overrides)
    return TableCell(**values)  # type: ignore[arg-type]


def _table(**overrides: object) -> Table:
    """创建2×3的最小合法来源表格。"""

    values = {
        "table_id": "test_t1",
        "document_id": "test",
        "source_category": "检验规范",
        "relative_path": "data/检验规范/test.pdf",
        "page_no": 6,
        "table_index": 1,
        "bbox": BoundingBox(0, 0, 300, 200),
        "row_count": 2,
        "column_count": 3,
        "cells": (_cell(),),
        "raw_html": "<table><tr><td>⑤⑨</td></tr></table>",
    }
    values.update(overrides)
    return Table(**values)  # type: ignore[arg-type]


def test_normal_table_and_cell_creation() -> None:
    table = _table()
    assert table.cells[0].raw_text == "⑤⑨"
    assert table.cells[0].content_type is CellContentType.NUMERIC
    assert table.cells[0].review_status is ReviewStatus.UNREVIEWED


@pytest.mark.parametrize("field_name", ["row_index", "column_index"])
def test_cell_indices_are_one_based(field_name: str) -> None:
    with pytest.raises(ValueError, match="1-based"):
        _cell(**{field_name: 0})


def test_rowspan_and_colspan_are_preserved() -> None:
    cell = _cell(rowspan=2, colspan=3)
    assert (cell.rowspan, cell.colspan) == (2, 3)


@pytest.mark.parametrize(
    ("coordinates", "message"),
    [((2, 0, 1, 3), "x1"), ((0, 4, 3, 2), "y1")],
)
def test_bbox_direction_is_validated(
    coordinates: tuple[int, int, int, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        BoundingBox(*coordinates)


def test_raw_text_is_not_replaced_by_verified_text() -> None:
    cell = _cell(
        raw_text="9",
        verified_text="⑤⑨",
        review_status="corrected",
    )
    assert cell.raw_text == "9"
    assert cell.verified_text == "⑤⑨"


def test_corrected_requires_verified_text() -> None:
    with pytest.raises(ValueError, match="必须提供 verified_text"):
        _cell(review_status="corrected")


def test_reviewed_confirms_raw_text() -> None:
    cell = _cell(review_status="reviewed", verified_text="⑤⑨")
    assert cell.verified_text == cell.raw_text


def test_reviewed_rejects_changed_text() -> None:
    with pytest.raises(ValueError, match="必须等于 raw_text"):
        _cell(review_status="reviewed", verified_text="59")


def test_unreviewed_rejects_verified_text() -> None:
    with pytest.raises(ValueError, match="必须为 None"):
        _cell(verified_text="⑤⑨")


def test_row_out_of_table_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="row_index"):
        _table(cells=(_cell(row_index=3),))


def test_column_out_of_table_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="column_index"):
        _table(cells=(_cell(column_index=4),))


def test_span_out_of_table_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="rowspan"):
        _table(cells=(_cell(row_index=2, rowspan=2),))


def test_numeric_content_and_quality_risk_are_separate() -> None:
    cell = _cell()
    assert cell.content_type is CellContentType.NUMERIC
    assert cell.risk_flags == (
        CellRiskFlag.NUMERIC_CONTENT,
        CellRiskFlag.SPECIAL_SYMBOL,
    )


def test_confidence_is_optional_and_bounded() -> None:
    assert _cell(ocr_confidence=None).ocr_confidence is None
    with pytest.raises(ValueError, match="0到1"):
        _cell(ocr_confidence=1.1)


def test_table_serializes_to_json_compatible_dict() -> None:
    payload = _table().to_dict()
    assert payload["bbox"] == {"x0": 0, "y0": 0, "x1": 300, "y1": 200}
    assert payload["cells"][0]["risk_flags"] == [
        "numeric_content",
        "special_symbol",
    ]


def test_special_unicode_round_trip_is_lossless() -> None:
    serialized = _table().to_json()
    assert "⑤⑨" in serialized
    assert json.loads(serialized)["cells"][0]["raw_text"] == "⑤⑨"


def test_model_has_no_ppstructure_dependency() -> None:
    import src.inspection_plan.document_parser.table_models as table_models

    source_names = set(table_models.__dict__)
    assert "paddleocr" not in source_names
    assert "PPStructureV3" not in source_names
