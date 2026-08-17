"""对 TASK-002.8 的人工工程抽检 Text Page 执行离线特征分析。

脚本从抽检 JSON 获取 sample_id 与标签，再从 ``data_processed/pages`` 中定位完整
Page 文本，调用纯特征模块并输出不含整页正文的 JSON。它只分析
``parse_method=text``，不会计算 OCR 质量、修改标签、改变路由或重新解析 PDF。
默认输出会覆盖 ``data_processed/evaluation/text_quality_features.json``。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from inspection_plan.document_parser.text_quality import (  # noqa: E402
    extract_text_quality_features,
)


DEFAULT_SAMPLE_PATH = (
    PROJECT_ROOT / "data_processed" / "evaluation" / "page_quality_sample.json"
)
DEFAULT_PAGES_DIRECTORY = PROJECT_ROOT / "data_processed" / "pages"
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT / "data_processed" / "evaluation" / "text_quality_features.json"
)
PREVIEW_LENGTH = 120


def load_page_index(pages_directory: Path) -> dict[tuple[str, int], dict[str, Any]]:
    """扫描已有 Page JSONL，以 document_id/page_no 建立完整文本索引。"""

    index: dict[tuple[str, int], dict[str, Any]] = {}
    for jsonl_path in sorted(Path(pages_directory).glob("*.jsonl")):
        with jsonl_path.open("r", encoding="utf-8") as input_file:
            for line_no, line in enumerate(input_file, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                key = (record["document_id"], record["page_no"])
                existing = index.get(key)
                if existing is not None and existing != record:
                    raise ValueError(f"Page 索引冲突：{key}，来源 {jsonl_path}:{line_no}")
                index[key] = record
    return index


def analyze_text_samples(
    sample_payload: dict[str, Any],
    page_index: dict[tuple[str, int], dict[str, Any]],
) -> list[dict[str, Any]]:
    """仅对 Text Page 合并人工标签、短 preview 与确定性特征。"""

    results: list[dict[str, Any]] = []
    for sample in sample_payload["samples"]:
        if sample["parse_method"] != "text":
            continue
        key = (sample["document_id"], sample["page_no"])
        if key not in page_index:
            raise KeyError(f"找不到抽检 Page：{key}")
        page = page_index[key]
        text = page["text"]
        features = extract_text_quality_features(text)
        results.append(
            {
                "sample_id": sample["sample_id"],
                "document_id": sample["document_id"],
                "page_no": sample["page_no"],
                "quality_label": sample["quality_label"],
                "error_types": sample["error_types"],
                "text_preview": text[:PREVIEW_LENGTH] + ("…" if len(text) > PREVIEW_LENGTH else ""),
                "features": features.to_dict(),
            }
        )
    return results


def summarize_by_label(results: list[dict[str, Any]]) -> dict[str, Any]:
    """按人工标签汇总每个数值特征的 min/median/max，避免只看平均值。"""

    if not results:
        return {}
    feature_names = list(results[0]["features"])
    summary: dict[str, Any] = {}
    for label in ("good", "acceptable", "bad"):
        group = [result for result in results if result["quality_label"] == label]
        if not group:
            continue
        summary[label] = {
            "sample_count": len(group),
            "features": {
                feature_name: {
                    "min": min(result["features"][feature_name] for result in group),
                    "median": statistics.median(
                        result["features"][feature_name] for result in group
                    ),
                    "max": max(result["features"][feature_name] for result in group),
                }
                for feature_name in feature_names
            },
        }
    return summary


def write_analysis(
    output_path: Path,
    sample_metadata: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    """写出特征、人工标签定位及分组统计，不保存不必要的整页正文。"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "purpose": "Text Page 确定性质量特征 baseline 探索",
            "text_pages_only": True,
            "sample_count": len(results),
            "labels_are_manually_reviewed": sample_metadata.get(
                "labels_are_manually_reviewed"
            ),
            "labels_are_user_confirmed": sample_metadata.get(
                "labels_are_user_confirmed"
            ),
            "quality_decision_implemented": False,
        },
        "summary_by_label": summarize_by_label(results),
        "samples": results,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    """解析抽检文件、Page 目录和特征输出路径。"""

    parser = argparse.ArgumentParser(description="分析人工抽检 Text Page 的质量特征")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE_PATH)
    parser.add_argument("--pages-directory", type=Path, default=DEFAULT_PAGES_DIRECTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def _resolve_project_path(path: Path) -> Path:
    """把相对 CLI 路径解释为项目根目录下路径。"""

    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> int:
    """运行12个 Text Page 的离线特征分析。"""

    args = parse_args()
    sample_path = _resolve_project_path(args.sample)
    pages_directory = _resolve_project_path(args.pages_directory)
    output_path = _resolve_project_path(args.output)
    sample_payload = json.loads(sample_path.read_text(encoding="utf-8"))
    results = analyze_text_samples(sample_payload, load_page_index(pages_directory))
    write_analysis(output_path, sample_payload["metadata"], results)
    label_counts = {
        label: sum(result["quality_label"] == label for result in results)
        for label in ("good", "acceptable", "bad")
    }
    print(
        f"Text 特征分析完成：样本 {len(results)}，good {label_counts['good']}，"
        f"acceptable {label_counts['acceptable']}，bad {label_counts['bad']}。"
    )
    print("仅生成离线特征；未实现质量判定或修改路由。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
