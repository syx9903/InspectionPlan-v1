"""离线转换TASK-002.10.2已有PP-Structure raw表格并生成真实验证产物。

脚本只读取 ``data_processed/table_experiments`` 中3页既有raw JSON，不调用或导入
PP-StructureV3。它先按顺序核对table block与table_res数量，并要求每对
``block_content == pred_html``，确认bbox配对后调用单表Adapter。每张Table单独写入
被Git忽略的 ``data_processed/tables``，重复运行会覆盖同名实验JSON。

该脚本不定义正式存储方案、不接入Page/Router，也不修改OCR或人工核验值。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.inspection_plan.document_parser.table_adapter import (  # noqa: E402
    TableAdapterError,
    adapt_ppstructure_table,
)


OUTPUT_ROOT = PROJECT_ROOT / "data_processed" / "tables"
SAMPLES: dict[str, dict[str, Any]] = {
    "PQ-015": {
        "document_id": "GBT_30579_2022",
        "source_category": "检验规范",
        "relative_path": "data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf",
        "page_no": 119,
    },
    "PQ-016": {
        "document_id": "GBT_30579_2022",
        "source_category": "检验规范",
        "relative_path": "data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf",
        "page_no": 120,
    },
    "PQ-012": {
        "document_id": "NBT_47018_1_2017",
        "source_category": "检验规范",
        "relative_path": "data/检验规范/34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf",
        "page_no": 6,
    },
}


def pair_table_blocks(page_result: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """安全配对table block与table_res，不仅依赖列表顺序猜测bbox。

    真实raw中两路结果顺序一致且block_content与pred_html完全相等。数量或内容任一
    不一致时停止，避免把其他表格区域坐标错误赋给当前Table。
    """

    blocks = [
        block
        for block in page_result.get("parsing_res_list", [])
        if block.get("block_label") == "table"
    ]
    table_results = page_result.get("table_res_list", [])
    if not isinstance(table_results, list) or len(blocks) != len(table_results):
        raise TableAdapterError("table block与table_res数量不一致")
    pairs = list(zip(blocks, table_results, strict=True))
    for table_index, (block, table_result) in enumerate(pairs, start=1):
        if block.get("block_content") != table_result.get("pred_html"):
            raise TableAdapterError(
                f"第{table_index}张表的block_content与pred_html不一致，无法确认bbox"
            )
    return pairs


def adapt_sample(sample_id: str, output_root: Path = OUTPUT_ROOT) -> list[dict[str, Any]]:
    """转换一个真实样本页，并返回供manifest人工核对的结构摘要。"""

    metadata = SAMPLES[sample_id]
    raw_path = (
        PROJECT_ROOT / "data_processed" / "table_experiments" / sample_id / "raw.json"
    )
    page_result = json.loads(raw_path.read_text(encoding="utf-8"))["res"]
    summaries: list[dict[str, Any]] = []
    output_root.mkdir(parents=True, exist_ok=True)

    for table_index, (block, table_result) in enumerate(
        pair_table_blocks(page_result), start=1
    ):
        table_id = (
            f"{metadata['document_id']}_p{metadata['page_no']}_t{table_index:02d}"
        )
        table = adapt_ppstructure_table(
            table_result,
            table_bbox=block["block_bbox"],
            table_id=table_id,
            document_id=metadata["document_id"],
            source_category=metadata["source_category"],
            relative_path=metadata["relative_path"],
            page_no=metadata["page_no"],
            table_index=table_index,
        )
        output_path = output_root / f"{table_id}.json"
        output_path.write_text(table.to_json() + "\n", encoding="utf-8")
        summaries.append(
            {
                "sample_id": sample_id,
                "table_id": table.table_id,
                "page_no": table.page_no,
                "table_index": table.table_index,
                "row_count": table.row_count,
                "column_count": table.column_count,
                "cell_count": len(table.cells),
                "rowspan_cell_count": sum(cell.rowspan > 1 for cell in table.cells),
                "colspan_cell_count": sum(cell.colspan > 1 for cell in table.cells),
                "unreviewed_cell_count": sum(
                    cell.review_status.value == "unreviewed" for cell in table.cells
                ),
                "verified_text_non_null_count": sum(
                    cell.verified_text is not None for cell in table.cells
                ),
                "numeric_risk_cell_count": sum(
                    any(flag.value == "numeric_content" for flag in cell.risk_flags)
                    for cell in table.cells
                ),
                "special_symbol_risk_cell_count": sum(
                    any(flag.value == "special_symbol" for flag in cell.risk_flags)
                    for cell in table.cells
                ),
                "output_path": output_path.relative_to(PROJECT_ROOT).as_posix(),
            }
        )
    return summaries


def main() -> int:
    """转换3页5表并写出实验manifest。"""

    summaries = [
        summary
        for sample_id in SAMPLES
        for summary in adapt_sample(sample_id)
    ]
    manifest = {
        "purpose": "TASK-002.10.4 PP-Structure输出到Table模型真实验证",
        "production_storage_format": False,
        "model_inference_rerun": False,
        "tables": summaries,
    }
    (OUTPUT_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"离线适配完成：{len(summaries)}张Table。")
    print("输出目录：data_processed/tables/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
