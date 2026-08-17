"""整理 TASK-002.8 bad Page 的人工版面复核记录并生成统计。

脚本从现有质量抽检 JSON 中只筛选 ``quality_label=bad``，保留 sample_id、页码、
解析方式和已有错误类型。版面类型、失败类别及线性文本充分性必须由独立人工标签
文件提供；程序只校验、合并和统计，不读取图像自动识别版面，也不修改原质量标签。
默认输出到被忽略的 ``data_processed/evaluation/bad_page_layout_review.json``。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_PATH = (
    PROJECT_ROOT / "data_processed" / "evaluation" / "page_quality_sample.json"
)
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT / "data_processed" / "evaluation" / "bad_page_layout_review.json"
)
LAYOUT_TYPES = {
    "plain_text",
    "table",
    "flowchart",
    "figure",
    "mixed_layout",
    "cover",
    "other",
}
FAILURE_CATEGORIES = {
    "text_quality",
    "layout_structure",
    "both",
    "metadata_only",
    "other",
}


def select_bad_pages(sample_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """只复制 bad Page 的追溯字段，不修改原抽检数据。"""

    reviews: list[dict[str, Any]] = []
    for sample in sample_payload["samples"]:
        if sample["quality_label"] != "bad":
            continue
        reviews.append(
            {
                "sample_id": sample["sample_id"],
                "document_id": sample["document_id"],
                "relative_path": sample["relative_path"],
                "page_no": sample["page_no"],
                "parse_method": sample["parse_method"],
                "quality_label": sample["quality_label"],
                "existing_error_types": deepcopy(sample["error_types"]),
                "text_preview": sample["text_preview"],
                "layout_type": None,
                "failure_category": None,
                "linear_text_sufficient": None,
                "notes": "",
            }
        )
    return reviews


def validate_annotation(annotation: dict[str, Any]) -> None:
    """校验人工版面标签属于最小枚举，且充分性字段严格为 bool。"""

    if annotation.get("layout_type") not in LAYOUT_TYPES:
        raise ValueError(f"非法 layout_type：{annotation.get('layout_type')}")
    if annotation.get("failure_category") not in FAILURE_CATEGORIES:
        raise ValueError(
            f"非法 failure_category：{annotation.get('failure_category')}"
        )
    if not isinstance(annotation.get("linear_text_sufficient"), bool):
        raise TypeError("linear_text_sufficient 必须是 bool")
    if annotation["layout_type"] == "other" and not str(
        annotation.get("notes", "")
    ).strip():
        raise ValueError("layout_type=other 必须提供 notes")


def apply_manual_annotations(
    reviews: list[dict[str, Any]], label_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """完整合并人工版面标签，不允许缺失或多余 sample_id。"""

    annotations = {
        annotation["sample_id"]: annotation
        for annotation in label_payload["annotations"]
    }
    expected_ids = {review["sample_id"] for review in reviews}
    if set(annotations) != expected_ids:
        raise ValueError("人工版面标签 sample_id 必须完整且与 bad Page 一致")

    merged = deepcopy(reviews)
    for review in merged:
        annotation = annotations[review["sample_id"]]
        validate_annotation(annotation)
        review["layout_type"] = annotation["layout_type"]
        review["failure_category"] = annotation["failure_category"]
        review["linear_text_sufficient"] = annotation[
            "linear_text_sufficient"
        ]
        review["notes"] = annotation.get("notes", "")
    return merged


def build_statistics(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """按版面、失败类别、充分性及解析方式生成可核对计数。"""

    layout_counts = Counter(review["layout_type"] for review in reviews)
    failure_counts = Counter(review["failure_category"] for review in reviews)
    sufficient_counts = Counter(
        str(review["linear_text_sufficient"]).lower() for review in reviews
    )
    by_parse_method: dict[str, dict[str, int]] = {}
    for parse_method in ("text", "ocr"):
        method_reviews = [
            review for review in reviews if review["parse_method"] == parse_method
        ]
        method_counts = Counter(
            review["failure_category"] for review in method_reviews
        )
        by_parse_method[parse_method] = {
            category: method_counts[category]
            for category in sorted(FAILURE_CATEGORIES)
        }

    structured_layout_types = {"table", "flowchart", "figure", "mixed_layout"}
    structured_layout_pages = sum(
        review["layout_type"] in structured_layout_types for review in reviews
    )
    return {
        "total_bad_pages": len(reviews),
        "by_layout_type": {
            layout_type: layout_counts[layout_type]
            for layout_type in sorted(LAYOUT_TYPES)
        },
        "by_failure_category": {
            category: failure_counts[category]
            for category in sorted(FAILURE_CATEGORIES)
        },
        "by_linear_text_sufficient": {
            "true": sufficient_counts["true"],
            "false": sufficient_counts["false"],
        },
        "by_parse_method_and_failure": by_parse_method,
        "structured_layout_pages": structured_layout_pages,
    }


def write_review(
    output_path: Path,
    reviews: list[dict[str, Any]],
    label_payload: dict[str, Any],
) -> None:
    """写出人工复核记录与统计，并声明其非自动、非用户确认性质。"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "purpose": "bad Page 版面类型人工复核",
            "annotations_are_manually_reviewed": True,
            "annotations_are_user_confirmed": False,
            "automatic_layout_detection_used": False,
            "reviewer": label_payload.get("reviewer"),
            "review_basis": label_payload.get("review_basis"),
        },
        "statistics": build_statistics(reviews),
        "reviews": reviews,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    """解析抽检、人工标签和输出路径。"""

    parser = argparse.ArgumentParser(description="整理 bad Page 人工版面复核结果")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE_PATH)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def _resolve_path(path: Path) -> Path:
    """把相对路径解释为项目根目录下路径。"""

    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> int:
    """合并14个 bad Page 的人工版面标签并打印核心统计。"""

    args = parse_args()
    sample_payload = json.loads(_resolve_path(args.sample).read_text(encoding="utf-8"))
    label_payload = json.loads(_resolve_path(args.labels).read_text(encoding="utf-8"))
    reviews = apply_manual_annotations(select_bad_pages(sample_payload), label_payload)
    output_path = _resolve_path(args.output)
    write_review(output_path, reviews, label_payload)
    statistics = build_statistics(reviews)
    print(
        f"复核完成：bad Page {statistics['total_bad_pages']}，"
        f"structured layout {statistics['structured_layout_pages']}，"
        f"linear text insufficient "
        f"{statistics['by_linear_text_sufficient']['false']}。"
    )
    print("版面标签来自人工视觉复核；未执行自动 Layout Detection。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
