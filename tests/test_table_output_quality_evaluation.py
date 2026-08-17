"""测试表格质量实验辅助逻辑，不断言外部模型识别固定文字。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.evaluate_table_output_quality import (
    extract_tables,
    inspect_html,
    stable_table_name,
    utf8_round_trip,
)


HTML = """<html><body><table>
<tr><th rowspan="2">材料</th><th colspan="2">检验项目</th></tr>
<tr><td>压力</td><td>1.6 MPa</td></tr>
</table></body></html>"""


def test_utf8_json_round_trip_preserves_chinese(tmp_path: Path) -> None:
    payload = {"html": "<td>压力容器 1.6 MPa</td>"}
    result = utf8_round_trip(tmp_path / "raw.json", payload)
    assert result["unicode_round_trip_ok"] is True
    assert result["utf8_bom_present"] is False


def test_html_row_and_cell_counts() -> None:
    result = inspect_html(HTML)
    assert result["html_parse_ok"] is True
    assert result["rows"] == 2
    assert result["td_count"] == 2
    assert result["th_count"] == 2


def test_html_merge_counts() -> None:
    result = inspect_html(HTML)
    assert result["rowspan_count"] == 1
    assert result["colspan_count"] == 1


def test_multiple_table_names_are_stable() -> None:
    assert [stable_table_name(index) for index in range(1, 4)] == [
        "table_001.html",
        "table_002.html",
        "table_003.html",
    ]


def test_table_index_must_start_at_one() -> None:
    with pytest.raises(ValueError, match="从1开始"):
        stable_table_name(0)


def test_extract_tables_does_not_modify_source() -> None:
    raw = {"res": {"table_res_list": [{"pred_html": HTML}]}}
    original = deepcopy(raw)
    tables = extract_tables(raw)
    tables[0]["pred_html"] = "changed"
    assert raw == original


def test_output_path_is_controlled_by_caller(tmp_path: Path) -> None:
    target = tmp_path / "sample" / stable_table_name(1)
    target.parent.mkdir(parents=True)
    target.write_text(HTML, encoding="utf-8")
    assert target.relative_to(tmp_path).as_posix() == "sample/table_001.html"
