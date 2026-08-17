"""测试PP-Structure dict到内部Table的确定性适配，不调用外部模型。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.inspection_plan.document_parser.table_adapter import (
    TableAdapterError,
    adapt_ppstructure_table,
    classify_cell_content_type,
)
from src.inspection_plan.document_parser.table_models import (
    CellContentType,
    CellRiskFlag,
    ReviewStatus,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ppstructure_table" / "simple_table.json"


def _fixture() -> dict[str, object]:
    """读取不含真实法规全文的最小PP-Structure结构fixture。"""

    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _adapt(**overrides: object):
    """使用显式来源字段转换fixture。"""

    arguments = {
        "table_result": _fixture(),
        "table_bbox": [0, 0, 300, 120],
        "table_id": "test_p6_t01",
        "document_id": "test",
        "source_category": "检验规范",
        "relative_path": "data/检验规范/test.pdf",
        "page_no": 6,
        "table_index": 1,
    }
    arguments.update(overrides)
    return adapt_ppstructure_table(**arguments)  # type: ignore[arg-type]


def test_normal_table_maps_source_and_shape() -> None:
    table = _adapt()
    assert (table.row_count, table.column_count, len(table.cells)) == (3, 3, 7)
    assert (table.document_id, table.page_no, table.table_index) == ("test", 6, 1)


def test_multiline_multicolumn_html_uses_one_based_indices() -> None:
    table = _adapt()
    assert [(cell.row_index, cell.column_index) for cell in table.cells] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
        (2, 3),
        (3, 2),
        (3, 3),
    ]


def test_rowspan_and_colspan_are_mapped() -> None:
    table = _adapt()
    assert (table.cells[1].rowspan, table.cells[1].colspan) == (1, 2)
    assert (table.cells[2].rowspan, table.cells[2].colspan) == (2, 1)


def test_raw_chinese_and_circled_text_are_preserved() -> None:
    table = _adapt()
    assert table.cells[0].raw_text == "项目"
    assert table.cells[-1].raw_text == "⑤⑨"
    assert "⑤⑨" in table.raw_html


def test_all_cells_start_unreviewed_without_verified_text() -> None:
    table = _adapt()
    assert all(cell.review_status is ReviewStatus.UNREVIEWED for cell in table.cells)
    assert all(cell.verified_text is None for cell in table.cells)


def test_numeric_and_special_symbol_risk_flags() -> None:
    table = _adapt()
    percent_cell = table.cells[4]
    circled_cell = table.cells[-1]
    assert percent_cell.content_type is CellContentType.NUMERIC
    assert percent_cell.risk_flags == (
        CellRiskFlag.NUMERIC_CONTENT,
        CellRiskFlag.MANUAL_REVIEW_REQUIRED,
    )
    assert CellRiskFlag.SPECIAL_SYMBOL in circled_cell.risk_flags
    assert CellRiskFlag.NUMERIC_CONTENT in circled_cell.risk_flags
    assert CellRiskFlag.MANUAL_REVIEW_REQUIRED in circled_cell.risk_flags
    assert circled_cell.content_type is CellContentType.NUMERIC


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", CellContentType.EMPTY),
        ("检验项目", CellContentType.TEXT),
        ("1.6 MPa", CellContentType.NUMERIC),
        ("GB/T 1234", CellContentType.MIXED),
        ("厚度20", CellContentType.MIXED),
    ],
)
def test_content_type_classification(text: str, expected: CellContentType) -> None:
    assert classify_cell_content_type(text) is expected


def test_table_and_cell_bbox_mapping() -> None:
    table = _adapt()
    assert table.bbox.to_dict() == {"x0": 0, "y0": 0, "x1": 300, "y1": 120}
    assert table.cells[-1].bbox.to_dict() == {
        "x0": 200,
        "y0": 80,
        "x1": 300,
        "y1": 120,
    }


def test_confidence_is_not_guessed_from_ocr_text_boxes() -> None:
    table = _adapt()
    assert all(cell.ocr_confidence is None for cell in table.cells)
    assert all(CellRiskFlag.OCR_LOW_CONFIDENCE not in cell.risk_flags for cell in table.cells)


def test_missing_pred_html_fails() -> None:
    fixture = _fixture()
    fixture.pop("pred_html")
    with pytest.raises(TableAdapterError, match="pred_html"):
        _adapt(table_result=fixture)


@pytest.mark.parametrize(
    "html",
    [
        "<table><tr><td>未闭合</table>",
        "<table></table>",
        "<table><tr><td>A</td></tr></table><table><tr><td>B</td></tr></table>",
    ],
)
def test_invalid_html_fails(html: str) -> None:
    fixture = _fixture()
    fixture["pred_html"] = html
    with pytest.raises(TableAdapterError):
        _adapt(table_result=fixture)


def test_cell_box_count_mismatch_fails() -> None:
    fixture = _fixture()
    fixture["cell_box_list"] = fixture["cell_box_list"][:-1]  # type: ignore[index]
    with pytest.raises(TableAdapterError, match="数量"):
        _adapt(table_result=fixture)


def test_invalid_bbox_fails() -> None:
    with pytest.raises(TableAdapterError, match="table_bbox"):
        _adapt(table_bbox=[10, 0, 1, 20])


def test_json_serialization_preserves_adapter_output() -> None:
    payload = json.loads(_adapt().to_json())
    assert payload["cells"][-1]["raw_text"] == "⑤⑨"
    assert payload["cells"][-1]["review_status"] == "unreviewed"


def test_adapter_module_does_not_import_paddleocr() -> None:
    source = Path(
        "src/inspection_plan/document_parser/table_adapter.py"
    ).read_text(encoding="utf-8")
    assert "import paddleocr" not in source
    assert "from paddleocr" not in source
