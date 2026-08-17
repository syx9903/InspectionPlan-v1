"""从现有 Page JSONL 生成小规模、待人工复核的质量抽检表。

脚本只读取 TASK-002.7 已生成或按小范围补充生成的 JSONL，不重新解析 PDF，
也不自动判断质量。它按固定抽样清单保留原始页码和解析方式，生成160字符 preview、
简单字符统计以及空的人工标签字段。默认输出位于
``data_processed/evaluation/page_quality_sample.json``，重复执行会覆盖尚未人工填写的
同名文件，因此已标注结果应先另行保存或在确认后再重新生成。
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data_processed" / "evaluation" / "page_quality_sample.json"
)
PREVIEW_LENGTH = 160
QUALITY_LABELS = {"good", "acceptable", "bad"}
ERROR_TYPES = {
    "garbled_text",
    "ocr_typo",
    "number_error",
    "clause_number_error",
    "header_footer_noise",
    "watermark_noise",
    "missing_text",
    "reading_order_error",
    "table_layout_loss",
    "figure_label_error",
    "other",
}

# 清单明确记录来源文档类型，避免根据 parse_method 反推：mixed PDF 可以同时产生
# text 与 OCR Page，而 parse_method 本身不能表达整份来源文档的类型。
SAMPLE_SOURCES = (
    ("text_pdf", "data_processed/pages/TSG_R0005_2011_amendment_1_auto.jsonl", None),
    ("text_pdf", "data_processed/pages/GBT_3274_2017_quality_p1.jsonl", None),
    ("text_pdf", "data_processed/pages/GBT_18591_2001_quality_p3.jsonl", None),
    ("no_usable_text_pdf", "data_processed/pages/NBT_47018_1_2017_auto.jsonl", None),
    ("no_usable_text_pdf", "data_processed/pages/GBT_17261_2011_quality_p4.jsonl", None),
    ("mixed_pdf", "data_processed/pages/GBT_30579_2022_quality_119_122.jsonl", None),
    ("mixed_pdf", "data_processed/pages/GBT_30579_2022_quality_143_149.jsonl", None),
)


def read_page_jsonl(path: Path) -> list[dict[str, Any]]:
    """逐行读取 Page JSONL，并为非法 JSON 或非对象记录给出明确错误。"""

    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as input_file:
        for line_no, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} 第 {line_no} 行不是合法 JSON") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path} 第 {line_no} 行必须是 JSON 对象")
            records.append(record)
    return records


def filter_by_parse_method(
    records: Iterable[dict[str, Any]], parse_method: str
) -> list[dict[str, Any]]:
    """按现有 ``parse_method`` 精确筛选 Page，不推断页面质量。"""

    if parse_method not in {"text", "ocr"}:
        raise ValueError("parse_method 只允许 text 或 ocr")
    return [record for record in records if record.get("parse_method") == parse_method]


def build_text_preview(text: str, limit: int = PREVIEW_LENGTH) -> str:
    """稳定保留正文开头至多 ``limit`` 个字符，超长时追加省略号。"""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("preview limit 必须是大于等于 1 的整数")
    return text if len(text) <= limit else text[:limit] + "…"


def count_character_types(text: str) -> dict[str, int | float]:
    """统计中文、英文、数字及其他可见字符，结果只辅助人工判断。

    中文比例以中文、英文和数字三类有效字符总数为分母。该比例不是质量分数，
    不会自动赋予标签或改变 Text/OCR 路由。
    """

    chinese = english = digits = other_visible = 0
    for character in text:
        if "\u3400" <= character <= "\u4dbf" or "\u4e00" <= character <= "\u9fff":
            chinese += 1
        elif character.isascii() and character.isalpha():
            english += 1
        elif character.isascii() and character.isdigit():
            digits += 1
        elif not character.isspace():
            other_visible += 1
    effective = chinese + english + digits
    return {
        "chinese_char_count": chinese,
        "english_char_count": english,
        "digit_char_count": digits,
        "other_visible_char_count": other_visible,
        "effective_char_count": effective,
        "chinese_ratio": round(chinese / effective, 6) if effective else 0.0,
    }


def build_sample_record(
    record: dict[str, Any], *, sample_id: str, source_type: str
) -> dict[str, Any]:
    """把 Page 记录转换为带空人工标签的抽检记录。"""

    text = record.get("text")
    if not isinstance(text, str):
        raise ValueError("Page text 必须是字符串")
    statistics = count_character_types(text)
    return {
        "sample_id": sample_id,
        "source_type": source_type,
        "document_id": record.get("document_id"),
        "relative_path": record.get("relative_path"),
        "page_no": record.get("page_no"),
        "parse_method": record.get("parse_method"),
        **statistics,
        "text_preview": build_text_preview(text),
        "quality_label": None,
        "error_types": [],
        "notes": "",
    }


def create_sample(
    project_root: Path,
    sources: Sequence[tuple[str, str, Sequence[int] | None]] = SAMPLE_SOURCES,
) -> list[dict[str, Any]]:
    """按显式来源和可选页码清单创建稳定顺序的小规模样本。"""

    selected: list[tuple[str, dict[str, Any]]] = []
    for source_type, relative_jsonl, page_numbers in sources:
        records = read_page_jsonl(project_root / relative_jsonl)
        allowed_pages = set(page_numbers) if page_numbers is not None else None
        for record in records:
            if allowed_pages is None or record.get("page_no") in allowed_pages:
                selected.append((source_type, record))

    return [
        build_sample_record(record, sample_id=f"PQ-{index:03d}", source_type=source_type)
        for index, (source_type, record) in enumerate(selected, start=1)
    ]


def write_sample(output_path: Path, samples: Sequence[dict[str, Any]]) -> None:
    """覆盖写入 UTF-8 抽检 JSON，并明确标记标签尚待人工填写。"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "purpose": "PDF → Page 小规模人工质量抽检",
            "preview_length": PREVIEW_LENGTH,
            "labels_are_manually_reviewed": False,
            "labels_are_user_confirmed": False,
            "sample_count": len(samples),
        },
        "samples": list(samples),
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def apply_manual_labels(sample_path: Path, label_path: Path) -> None:
    """把独立人工复核记录合并进抽检 JSON，并保留评审依据声明。

    本函数只校验标签集合和 sample_id 覆盖关系，不根据字符统计自动生成标签。
    这样可区分辅助程序产出的客观字段与人工视觉判断。
    """

    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    label_payload = json.loads(label_path.read_text(encoding="utf-8"))
    labels = {item["sample_id"]: item for item in label_payload["labels"]}
    samples = payload["samples"]
    expected_ids = {sample["sample_id"] for sample in samples}
    if set(labels) != expected_ids:
        raise ValueError("人工标签 sample_id 必须完整且与抽检表一致")

    for sample in samples:
        annotation = labels[sample["sample_id"]]
        quality_label = annotation["quality_label"]
        error_types = annotation.get("error_types", [])
        if quality_label not in QUALITY_LABELS:
            raise ValueError(f"非法 quality_label：{quality_label}")
        unknown_errors = set(error_types) - ERROR_TYPES
        if unknown_errors:
            raise ValueError(f"非法 error_types：{sorted(unknown_errors)}")
        sample["quality_label"] = quality_label
        sample["error_types"] = error_types
        sample["notes"] = annotation.get("notes", "")

    payload["metadata"]["labels_are_manually_reviewed"] = True
    payload["metadata"]["labels_are_user_confirmed"] = False
    payload["metadata"]["reviewer"] = label_payload.get("reviewer")
    payload["metadata"]["review_basis"] = label_payload.get("review_basis")
    sample_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def render_review_images(
    project_root: Path,
    output_directory: Path,
    samples: Sequence[dict[str, Any]],
    *,
    dpi: int = 120,
) -> None:
    """把抽样对应的原 PDF 页渲染为仅供人工对照的 PNG。

    图片写入被忽略的 ``data_processed``，不会改变 Page JSONL 或参与自动标签。
    每份 PDF 只在需要时打开，页码仍按原始 1-based 值定位。
    """

    output_directory.mkdir(parents=True, exist_ok=True)
    documents: dict[str, Any] = {}
    try:
        for sample in samples:
            relative_path = str(sample["relative_path"])
            if relative_path not in documents:
                documents[relative_path] = pymupdf.open(project_root / relative_path)
            document = documents[relative_path]
            page_no = int(sample["page_no"])
            pixmap = document[page_no - 1].get_pixmap(
                matrix=pymupdf.Matrix(dpi / 72.0, dpi / 72.0),
                colorspace=pymupdf.csRGB,
                alpha=False,
            )
            pixmap.save(output_directory / f"{sample['sample_id']}_page_{page_no}.png")
    finally:
        for document in documents.values():
            document.close()


def parse_args() -> argparse.Namespace:
    """解析可选输出路径，样本来源由可审查的固定清单控制。"""

    parser = argparse.ArgumentParser(description="从现有 Page JSONL 生成质量抽检表")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--render-directory",
        type=Path,
        help="可选：把原 PDF 抽样页渲染到指定目录，供人工视觉对照",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        help="可选：合并完整的人工视觉复核标签 JSON；程序不会自动生成标签",
    )
    return parser.parse_args()


def main() -> int:
    """生成空标签抽检表并打印方法和来源类型数量。"""

    args = parse_args()
    output_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    samples = create_sample(PROJECT_ROOT)
    write_sample(output_path, samples)
    if args.labels is not None:
        label_path = args.labels if args.labels.is_absolute() else PROJECT_ROOT / args.labels
        apply_manual_labels(output_path, label_path)
    if args.render_directory is not None:
        render_directory = (
            args.render_directory
            if args.render_directory.is_absolute()
            else PROJECT_ROOT / args.render_directory
        )
        render_review_images(PROJECT_ROOT, render_directory, samples)
    text_count = len(filter_by_parse_method(samples, "text"))
    ocr_count = len(filter_by_parse_method(samples, "ocr"))
    mixed_count = sum(sample["source_type"] == "mixed_pdf" for sample in samples)
    label_status = "已合并人工视觉复核标签" if args.labels is not None else "质量标签待人工填写"
    print(
        f"抽检表已生成：总 Page {len(samples)}，text {text_count}，OCR {ocr_count}，"
        f"mixed 来源 {mixed_count}；{label_status}。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
