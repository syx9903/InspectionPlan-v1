"""用 Page 级 Text/OCR 路由器解析单个 PDF 并生成 Page JSONL。

脚本默认输出到 ``data_processed/pages/<document_id>.jsonl``，重复执行会覆盖
同名产物。调用方必须提供来源类别和稳定文档标识，可用 1-based、包含端点的
页码范围做小规模验证。脚本不批量扫描资料，也不清洗或解释页面正文。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from inspection_plan.document_parser import PdfPageRouter  # noqa: E402


SAFE_DOCUMENT_ID_PATTERN = re.compile(r"^[^/\\]+$")


def parse_args() -> argparse.Namespace:
    """解析输入 PDF、来源元数据、页码范围和输出位置。"""

    parser = argparse.ArgumentParser(description="逐页自动选择 Text 或 OCR 并输出 JSONL")
    parser.add_argument("pdf", type=Path, help="待解析的项目内 PDF")
    parser.add_argument("--source-category", required=True, help="明确的资料来源类别")
    parser.add_argument("--document-id", required=True, help="调用方提供的稳定文档标识")
    parser.add_argument("--relative-path", help="项目相对路径；默认从输入路径计算")
    parser.add_argument("--output", type=Path, help="JSONL 输出；默认按 document-id 生成")
    parser.add_argument("--start-page", type=int, help="起始原始页码，1-based 且包含")
    parser.add_argument("--end-page", type=int, help="结束原始页码，1-based 且包含")
    return parser.parse_args()


def _resolve_relative_path(pdf_path: Path, supplied_path: str | None) -> str:
    """返回显式来源路径，或由项目内实际路径生成正斜杠相对路径。"""

    if supplied_path is not None:
        return supplied_path
    try:
        return pdf_path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("项目外 PDF 必须显式提供 --relative-path") from exc


def _resolve_output_path(document_id: str, supplied_path: Path | None) -> Path:
    """返回显式输出，或安全地生成默认 Page JSONL 路径。"""

    if supplied_path is not None:
        return supplied_path if supplied_path.is_absolute() else PROJECT_ROOT / supplied_path
    if not SAFE_DOCUMENT_ID_PATTERN.fullmatch(document_id) or document_id in {".", ".."}:
        raise ValueError("默认输出要求 document_id 不含路径分隔符")
    return PROJECT_ROOT / "data_processed" / "pages" / f"{document_id}.jsonl"


def main() -> int:
    """执行一次页级路由，输出统计和可复核 JSONL 路径。"""

    args = parse_args()
    pdf_path = args.pdf if args.pdf.is_absolute() else PROJECT_ROOT / args.pdf
    output_path = _resolve_output_path(args.document_id, args.output)
    router = PdfPageRouter()
    pages = router.parse_to_jsonl(
        pdf_path,
        output_path,
        document_id=args.document_id,
        source_category=args.source_category,
        relative_path=_resolve_relative_path(pdf_path, args.relative_path),
        start_page=args.start_page,
        end_page=args.end_page,
    )
    stats = router.last_run_stats
    print(
        f"解析完成：总页数 {stats['total_pages']}，text {stats['text_pages']}，"
        f"OCR {stats['ocr_pages']}，failed {stats['failed_pages']}。"
    )
    print(
        f"OCR 初始化 {stats['ocr_initializations']} 次，"
        f"总耗时 {stats['total_seconds']:.3f} 秒。"
    )
    for page in pages:
        print(f"page {page.page_no} -> {page.parse_method.value}")
    try:
        printable_output = output_path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        printable_output = str(output_path)
    print(f"输出：{printable_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
