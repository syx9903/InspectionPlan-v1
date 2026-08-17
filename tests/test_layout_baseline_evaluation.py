"""测试复杂版面实验辅助逻辑，不固定任何外部模型识别结果。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluate_layout_baselines import (
    SAMPLES,
    build_timing,
    resolve_sample,
    summarize_raw_output,
    write_json,
)


def test_samples_cover_required_layout_types() -> None:
    assert {sample["layout_type"] for sample in SAMPLES.values()} == {
        "table",
        "flowchart",
        "figure",
        "mixed_layout",
    }


def test_sample_page_numbers_are_preserved() -> None:
    assert SAMPLES["PQ-015"]["page_no"] == 119
    assert SAMPLES["PQ-018"]["page_no"] == 122
    assert SAMPLES["PQ-014"]["page_no"] == 4
    assert SAMPLES["PQ-012"]["page_no"] == 6


def test_unknown_sample_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sample_id"):
        resolve_sample("PQ-999", tmp_path)


def test_missing_sample_image_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="页面图像不存在"):
        resolve_sample("PQ-015", tmp_path)


def test_timing_structure_has_total() -> None:
    assert build_timing(1.0, 2.0, 3.0) == {
        "init_ms": 1.0,
        "predict_ms": 2.0,
        "save_ms": 3.0,
        "total_ms": 6.0,
    }


def test_raw_output_summary_only_reports_observable_counts() -> None:
    raw = {
        "res": {
            "parsing_res_list": [
                {"block_label": "text"},
                {"block_label": "table"},
            ],
            "table_res_list": [{"pred_html": "<table></table>"}],
        }
    }
    assert summarize_raw_output(raw) == {
        "detected_block_count": 2,
        "detected_block_labels": ["text", "table"],
        "table_result_count": 1,
        "human_review_required": True,
    }


def test_write_json_creates_parent_and_utf8_file(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "summary.json"
    write_json(output, {"sample_id": "PQ-测试"})
    assert json.loads(output.read_text(encoding="utf-8"))["sample_id"] == "PQ-测试"
