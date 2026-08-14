"""通过命令行把一个明确选择 OCR 路径的扫描 PDF 转成 Page JSONL。

脚本要求调用方提供来源类别和文档标识，默认使用 200 DPI 并输出到
``data_processed/pages/<document_id>.jsonl``。重复执行会覆盖同名文件。
脚本不自动判断解析路径、不回退文本层，也不保存 OCR bbox 或 confidence。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from inspection_plan.document_parser import (  # noqa: E402
    DEFAULT_OCR_DPI,
    OcrPdfParser,
)


SAFE_DOCUMENT_ID_PATTERN = re.compile(r"^[^/\\]+$")


def parse_args() -> argparse.Namespace:
    """解析单个扫描 PDF、业务元数据、DPI 与输出路径参数。"""

    parser = argparse.ArgumentParser(description="把一个扫描型 PDF OCR 为 Page JSONL")
    parser.add_argument("pdf", type=Path, help="待 OCR 的项目内 PDF")
    parser.add_argument("--source-category", required=True, help="明确的来源目录类别")
    parser.add_argument("--document-id", required=True, help="调用方提供的稳定文档标识")
    parser.add_argument(
        "--relative-path",
        help="Page 项目相对路径；默认根据项目根目录计算",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="JSONL 输出；默认 data_processed/pages/<document-id>.jsonl",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_OCR_DPI,
        help=f"OCR 渲染 DPI；默认 {DEFAULT_OCR_DPI}",
    )
    return parser.parse_args()


def _resolve_relative_path(pdf_path: Path, supplied_path: str | None) -> str:
    """使用显式路径，或要求输入位于项目内并生成正斜杠相对路径。"""

    if supplied_path is not None:
        return supplied_path
    try:
        return pdf_path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("项目外 PDF 必须显式提供 --relative-path") from exc


def _resolve_output_path(document_id: str, supplied_path: Path | None) -> Path:
    """返回显式输出，或根据安全 document_id 生成默认 JSONL 路径。"""

    if supplied_path is not None:
        return supplied_path
    if not SAFE_DOCUMENT_ID_PATTERN.fullmatch(document_id) or document_id in {".", ".."}:
        raise ValueError("默认输出要求 document_id 不含路径分隔符")
    return PROJECT_ROOT / "data_processed" / "pages" / f"{document_id}.jsonl"


def main() -> int:
    """初始化一次 OCR，解析整份单文件 PDF 并输出状态与性能摘要。"""

    args = parse_args()
    pdf_path = args.pdf if args.pdf.is_absolute() else PROJECT_ROOT / args.pdf
    relative_path = _resolve_relative_path(pdf_path, args.relative_path)
    output_path = _resolve_output_path(args.document_id, args.output)

    parser = OcrPdfParser(dpi=args.dpi)
    pages = parser.parse_to_jsonl(
        pdf_path,
        output_path,
        document_id=args.document_id,
        source_category=args.source_category,
        relative_path=relative_path,
    )
    statuses = Counter(page.text_status.value for page in pages)
    stats = parser.last_run_stats
    print(
        f"OCR 完成：总页数 {len(pages)}，success {statuses['success']}，"
        f"empty {statuses['empty']}，failed {statuses['failed']}。"
    )
    print(
        f"耗时：总计 {stats['total_seconds']:.3f} 秒，"
        f"平均 {stats['average_seconds_per_page']:.3f} 秒/页。"
    )
    print(f"输出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
