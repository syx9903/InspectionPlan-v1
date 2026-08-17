"""诊断 PP-StructureV3 表格输出编码并生成小样本质量评价产物。

脚本复用 TASK-002.10.1 的 PQ-015、PQ-012 raw JSON，只对新增 PQ-016
按需运行一次 PP-StructureV3。每张表保存原始 HTML、实验 normalized 统计、
Python repr 和 UTF-8 JSON round-trip 结果，再合并人工结构与关键 cell 标注。
输出位于被 Git 忽略的 ``data_processed/table_experiments``，可重复覆盖。

本模块只验证实验输出层，不自动修复 OCR 字符，不定义正式 Table Schema，也不
修改 Page、Router 或任何生产 Parser。法规数字即使只有一个字符不一致，也必须
标为错误，不能用模糊匹配静默放行。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data_processed" / "table_experiments"
DEFAULT_LABELS_PATH = DEFAULT_OUTPUT_ROOT / "manual_labels.json"
SAMPLES: dict[str, dict[str, Any]] = {
    "PQ-015": {
        "relative_path": "data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf",
        "page_no": 119,
        "page_characteristics": "规则型4列表；中文、条款号和圈号数字",
        "image_path": "data_processed/evaluation/page_quality_images/PQ-015_page_119.png",
        "source_raw_path": "data_processed/layout_experiments/PQ-015/paddle/raw.json",
    },
    "PQ-016": {
        "relative_path": "data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf",
        "page_no": 120,
        "page_characteristics": "低质量续表；中文、条款号、圈号及水印",
        "image_path": "data_processed/evaluation/page_quality_images/PQ-016_page_120.png",
        "source_raw_path": None,
    },
    "PQ-012": {
        "relative_path": "data/检验规范/34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf",
        "page_no": 6,
        "page_characteristics": "mixed layout复杂表；rowspan、colspan、标准号",
        "image_path": "data_processed/evaluation/page_quality_images/PQ-012_page_6.png",
        "source_raw_path": "data_processed/layout_experiments/PQ-012/paddle/raw.json",
    },
}


class TableHTMLInspector(HTMLParser):
    """用标准库统计表格行、单元格和合并属性，并保留逐行文字。"""

    def __init__(self) -> None:
        super().__init__()
        self.table_count = 0
        self.rows: list[list[str]] = []
        self.rowspan_count = 0
        self.colspan_count = 0
        self.td_count = 0
        self.th_count = 0
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """记录HTML结构；rowspan/colspan按出现的属性个数统计。"""

        attributes = dict(attrs)
        if tag == "table":
            self.table_count += 1
        elif tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self.td_count += tag == "td"
            self.th_count += tag == "th"
            self.rowspan_count += "rowspan" in attributes
            self.colspan_count += "colspan" in attributes
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        """收集单元格可见文字，不执行任何OCR纠错或规范化。"""

        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        """在单元格和行结束时固化内容。"""

        if tag in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append("".join(self._current_cell).strip())
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            self.rows.append(self._current_row)
            self._current_row = None


def inspect_html(html: str) -> dict[str, Any]:
    """返回HTML可解析性、行列和合并单元格的实验统计。"""

    inspector = TableHTMLInspector()
    inspector.feed(html)
    inspector.close()
    columns = max((len(row) for row in inspector.rows), default=0)
    return {
        "html_parse_ok": inspector.table_count == 1,
        "table_count": inspector.table_count,
        "rows": len(inspector.rows),
        "columns_by_max_explicit_cells": columns,
        "cells_per_row": [len(row) for row in inspector.rows],
        "td_count": inspector.td_count,
        "th_count": inspector.th_count,
        "rowspan_count": inspector.rowspan_count,
        "colspan_count": inspector.colspan_count,
        "cell_text_rows": inspector.rows,
    }


def utf8_round_trip(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """明确使用UTF-8和ensure_ascii=False写回，并逐对象检查完全相等。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(serialized, encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return {
        "encoding": "utf-8",
        "ensure_ascii": False,
        "unicode_round_trip_ok": loaded == payload,
        "utf8_bom_present": path.read_bytes().startswith(b"\xef\xbb\xbf"),
    }


def stable_table_name(table_index: int) -> str:
    """使用从1开始的三位编号，保证多表输出文件名稳定。"""

    if table_index < 1:
        raise ValueError("table_index 必须从1开始")
    return f"table_{table_index:03d}.html"


def extract_tables(raw_output: dict[str, Any]) -> list[dict[str, Any]]:
    """复制第三方表格关键字段，避免修改原始PP-Structure对象。"""

    result = raw_output.get("res", raw_output)
    tables = result.get("table_res_list", [])
    return [deepcopy(table) for table in tables]


def run_model(image_path: Path, clock: Callable[[], float] = time.perf_counter) -> tuple[dict[str, Any], dict[str, float]]:
    """在当前Windows CPU兼容配置下运行一次PP-StructureV3。

    `enable_mkldnn=False` 沿用TASK-002.10.1已经验证的兼容配置。函数保留返回
    Python对象到JSON字典的时点，使调用方可以在落盘前记录repr和round-trip证据。
    """

    from paddleocr import PPStructureV3

    init_started = clock()
    pipeline = PPStructureV3(
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_region_detection=False,
    )
    init_ms = (clock() - init_started) * 1000
    predict_started = clock()
    result = next(iter(pipeline.predict(str(image_path))))
    predict_ms = (clock() - predict_started) * 1000
    return result.json, {
        "pipeline_init_ms": round(init_ms, 3),
        "predict_ms": round(predict_ms, 3),
    }


def load_labels(path: Path | None) -> dict[str, Any]:
    """加载人工Gold；未提供时返回空标签，便于先生成核对模板。"""

    if path is None or not path.is_file():
        return {"samples": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_cells(cell_checks: list[dict[str, Any]]) -> dict[str, Any]:
    """按人工标签分别统计中文、数字、单位和标准/条款号准确性。"""

    summary: dict[str, Any] = {}
    for category in ("chinese", "numeric", "unit", "standard_or_clause"):
        checks = [item for item in cell_checks if item["category"] == category]
        exact = sum(item["status"] == "correct" for item in checks)
        wrong = sum(item["status"] in {"minor_error", "wrong"} for item in checks)
        summary[category] = {
            "checked": len(checks),
            "exact": exact,
            "wrong": wrong,
            "exact_rate": round(exact / len(checks), 4) if checks else None,
        }
    return summary


def process_sample(
    sample_id: str,
    raw_output: dict[str, Any],
    output_root: Path,
    labels: dict[str, Any],
    timing: dict[str, float] | None,
    object_source: str,
) -> dict[str, Any]:
    """保存单个样本的诊断产物，并合并人工质量评价。"""

    sample = SAMPLES[sample_id]
    sample_dir = output_root / sample_id
    tables = extract_tables(raw_output)
    sample_labels = labels.get("samples", {}).get(sample_id, {})
    normalized_tables: list[dict[str, Any]] = []
    repr_tables: list[dict[str, Any]] = []

    for table_index, table in enumerate(tables, start=1):
        html = table.get("pred_html", "")
        html_name = stable_table_name(table_index)
        (sample_dir / html_name).parent.mkdir(parents=True, exist_ok=True)
        (sample_dir / html_name).write_text(html, encoding="utf-8")
        html_stats = inspect_html(html)
        normalized_tables.append(
            {
                "experimental_normalized_output": True,
                "table_index": table_index,
                "html_file": html_name,
                **{key: value for key, value in html_stats.items() if key != "cell_text_rows"},
                "cell_text_rows": html_stats["cell_text_rows"],
            }
        )
        ocr_texts = table.get("table_ocr_pred", {}).get("rec_texts", [])
        repr_tables.append(
            {
                "table_index": table_index,
                "pred_html_repr": repr(html),
                "ocr_texts_repr": repr(ocr_texts),
            }
        )

    round_trip = utf8_round_trip(sample_dir / "raw.json", raw_output)
    (sample_dir / "normalized.json").write_text(
        json.dumps({"tables": normalized_tables}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (sample_dir / "python_repr.json").write_text(
        json.dumps({"tables": repr_tables}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (sample_dir / "round_trip.json").write_text(
        json.dumps(round_trip, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    table_checks = sample_labels.get("table_checks", [])
    cell_checks = sample_labels.get("cell_checks", [])
    summary = {
        "sample_id": sample_id,
        "input_metadata": sample,
        "object_source": object_source,
        "table_count": len(tables),
        "unicode_round_trip": round_trip,
        "timing": timing,
        "table_checks": table_checks,
        "cell_checks": cell_checks,
        "cell_quality": evaluate_cells(cell_checks),
    }
    (sample_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def parse_args() -> argparse.Namespace:
    """解析样本、人工标签、输出目录和新增样本模型开关。"""

    parser = argparse.ArgumentParser(description="诊断PP-StructureV3表格输出质量")
    parser.add_argument("--samples", nargs="+", choices=sorted(SAMPLES), default=list(SAMPLES))
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-missing", action="store_true")
    return parser.parse_args()


def main() -> int:
    """处理3个表格页并生成可追溯实验清单。"""

    args = parse_args()
    output_root = args.output_root if args.output_root.is_absolute() else PROJECT_ROOT / args.output_root
    labels_path = args.labels if args.labels.is_absolute() else PROJECT_ROOT / args.labels
    labels = load_labels(labels_path)
    summaries: list[dict[str, Any]] = []

    for sample_id in args.samples:
        sample = SAMPLES[sample_id]
        source_raw_path = sample["source_raw_path"]
        timing = None
        if source_raw_path:
            raw_output = json.loads((PROJECT_ROOT / source_raw_path).read_text(encoding="utf-8"))
            object_source = "reloaded_task_002_10_1_utf8_json"
        elif (output_root / sample_id / "raw.json").is_file():
            raw_output = json.loads((output_root / sample_id / "raw.json").read_text(encoding="utf-8"))
            object_source = "reloaded_previous_direct_model_utf8_json"
        elif args.run_missing:
            raw_output, timing = run_model(PROJECT_ROOT / sample["image_path"])
            object_source = "direct_ppstructure_python_object"
        else:
            raise FileNotFoundError(f"{sample_id} 缺少raw输出；请使用 --run-missing")
        summaries.append(
            process_sample(sample_id, raw_output, output_root, labels, timing, object_source)
        )

    manifest = {
        "purpose": "TASK-002.10.2表格输出质量与编码诊断",
        "production_schema": False,
        "samples": summaries,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"表格实验完成：{len(summaries)}页，{sum(item['table_count'] for item in summaries)}张表。")
    print("输出目录：data_processed/table_experiments/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
