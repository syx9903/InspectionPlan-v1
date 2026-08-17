"""运行 TASK-002.10.1 的极小规模复杂版面 baseline 实验。

脚本固定使用 TASK-002.9.2A 选出的4个 sample_id，并读取已经生成的页面 PNG，
避免改变现有 PDF 渲染与 Page 解析链路。当前唯一可执行后端为环境中已有的
PP-StructureV3；每个样本分别保存原始 JSON、可视化图片、最小摘要和耗时。
输出目录 ``data_processed/layout_experiments`` 已被 Git 忽略，可重复运行并覆盖
同一 sample/backend 的实验文件。本脚本不修改 Page Schema、Router 或生产 JSONL。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data_processed" / "layout_experiments"
SAMPLES: dict[str, dict[str, Any]] = {
    "PQ-015": {
        "layout_type": "table",
        "relative_path": "data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf",
        "page_no": 119,
        "image_path": "data_processed/evaluation/page_quality_images/PQ-015_page_119.png",
    },
    "PQ-018": {
        "layout_type": "flowchart",
        "relative_path": "data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf",
        "page_no": 122,
        "image_path": "data_processed/evaluation/page_quality_images/PQ-018_page_122.png",
    },
    "PQ-014": {
        "layout_type": "figure",
        "relative_path": "data/球罐标准/GBT 17261-2011 钢制球形储罐型式与基本参数.pdf",
        "page_no": 4,
        "image_path": "data_processed/evaluation/page_quality_images/PQ-014_page_4.png",
    },
    "PQ-012": {
        "layout_type": "mixed_layout",
        "relative_path": "data/检验规范/34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf",
        "page_no": 6,
        "image_path": "data_processed/evaluation/page_quality_images/PQ-012_page_6.png",
    },
}


def resolve_sample(sample_id: str, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """返回带绝对输入路径的样本副本，并校验 sample_id 和页面图像。"""

    if sample_id not in SAMPLES:
        raise ValueError(f"未知 sample_id：{sample_id}")
    sample = {"sample_id": sample_id, **SAMPLES[sample_id]}
    image_path = project_root / sample["image_path"]
    if not image_path.is_file():
        raise FileNotFoundError(f"页面图像不存在：{image_path}")
    sample["resolved_image_path"] = image_path
    return sample


def build_timing(init_ms: float, predict_ms: float, save_ms: float) -> dict[str, float]:
    """生成统一毫秒耗时结构，便于不同后端以后横向比较。"""

    return {
        "init_ms": round(init_ms, 3),
        "predict_ms": round(predict_ms, 3),
        "save_ms": round(save_ms, 3),
        "total_ms": round(init_ms + predict_ms + save_ms, 3),
    }


def summarize_raw_output(raw_output: dict[str, Any]) -> dict[str, Any]:
    """只提取稳定的区域标签与表格输出数量，不评价模型语义质量。"""

    result = raw_output.get("res", raw_output)
    blocks = result.get("parsing_res_list", []) if isinstance(result, dict) else []
    labels = [block.get("block_label") for block in blocks if isinstance(block, dict)]
    tables = result.get("table_res_list", []) if isinstance(result, dict) else []
    return {
        "detected_block_count": len(blocks),
        "detected_block_labels": labels,
        "table_result_count": len(tables),
        "human_review_required": True,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """以 UTF-8 写出可人工检查的 JSON，并创建所需目录。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_paddle(
    sample_ids: list[str],
    output_root: Path,
    clock: Callable[[], float] = time.perf_counter,
) -> list[dict[str, Any]]:
    """初始化一次 PP-StructureV3，并逐样本保存原始输出和耗时。

    模型输出可能随 PaddleOCR 或模型版本变化，因此脚本不自动宣称表格或流程关系
    识别成功。流程图箭头、分支以及图示标签位置必须结合可视化结果人工复核。
    """

    from paddleocr import PPStructureV3

    init_started = clock()
    pipeline = PPStructureV3(
        # PaddlePaddle 3.3.1 在当前 Windows CPU 上执行 PP-DocLayout 的 oneDNN
        # 路径会触发未实现的 PIR Attribute 转换；使用公开参数切回标准 Paddle
        # 执行器，不改变模型权重、输入图像或后处理规则。
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_region_detection=False,
    )
    init_ms = (clock() - init_started) * 1000
    summaries: list[dict[str, Any]] = []

    for sample_id in sample_ids:
        sample = resolve_sample(sample_id)
        sample_dir = output_root / sample_id / "paddle"
        predict_started = clock()
        results: Iterator[Any] = pipeline.predict(str(sample["resolved_image_path"]))
        result = next(iter(results))
        predict_ms = (clock() - predict_started) * 1000

        save_started = clock()
        raw_output = result.json
        write_json(sample_dir / "raw.json", raw_output)
        result.save_to_img(str(sample_dir / "visualizations"))
        save_ms = (clock() - save_started) * 1000

        summary = {
            "input_metadata": {
                key: value
                for key, value in sample.items()
                if key != "resolved_image_path"
            },
            "backend": "PP-StructureV3",
            "backend_version": "PaddleOCR 3.7.0",
            "run_success": True,
            "timing": build_timing(init_ms, predict_ms, save_ms),
            "automatic_observations": summarize_raw_output(raw_output),
            "limitations": [
                "区域或文字被检测到不代表流程箭头和分支关系已恢复。",
                "figure 标签被 OCR 不代表标签与几何位置关系已理解。",
                "表格行列、合并单元格和数字列对应关系仍需人工复核。",
            ],
        }
        write_json(sample_dir / "summary.json", summary)
        summaries.append(summary)
    return summaries


def parse_args() -> argparse.Namespace:
    """解析固定样本集合和被忽略的实验输出目录。"""

    parser = argparse.ArgumentParser(description="运行复杂版面 PP-StructureV3 baseline")
    parser.add_argument(
        "--samples", nargs="+", choices=sorted(SAMPLES), default=list(SAMPLES)
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    """运行 baseline，并写出总清单供实验报告追溯。"""

    args = parse_args()
    output_root = (
        args.output_root
        if args.output_root.is_absolute()
        else PROJECT_ROOT / args.output_root
    )
    summaries = run_paddle(args.samples, output_root)
    write_json(
        output_root / "manifest.json",
        {
            "purpose": "TASK-002.10.1 极小规模复杂版面 baseline",
            "production_parser": False,
            "samples": summaries,
        },
    )
    print(f"实验完成：PP-StructureV3 成功处理 {len(summaries)} 个样本。")
    # 项目目录名含零宽字符，Windows GBK 终端无法编码绝对路径；固定打印
    # 可移植的项目相对路径，同时避免泄露本机目录信息。
    print("输出目录：data_processed/layout_experiments/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
