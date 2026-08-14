"""通过命令行把一个文本型 PDF 解析为 Page JSONL。

脚本输入一个 PDF，以及调用方明确提供的来源类别和文档标识。默认相对路径根据
项目根目录计算，默认输出为 ``data_processed/pages/<document_id>.jsonl``。
重复执行会覆盖同名输出。脚本只提取文本层，不渲染页面、不 OCR、不清洗正文。
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

from inspection_plan.document_parser import TextPdfParser  # noqa: E402


SAFE_DOCUMENT_ID_PATTERN = re.compile(r"^[^/\\]+$")


def parse_args() -> argparse.Namespace:
    """解析单文件 PDF、来源类别、文档标识、相对路径和输出路径参数。"""

    parser = argparse.ArgumentParser(description="把一个文本型 PDF 解析为 Page JSONL")
    parser.add_argument("pdf", type=Path, help="待解析 PDF，可使用项目相对路径")
    parser.add_argument("--source-category", required=True, help="明确的来源目录类别")
    parser.add_argument("--document-id", required=True, help="调用方提供的稳定文档标识")
    parser.add_argument(
        "--relative-path",
        help="写入 Page 的项目相对路径；默认根据项目根目录计算",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="JSONL 输出路径；默认 data_processed/pages/<document-id>.jsonl",
    )
    return parser.parse_args()


def _resolve_relative_path(pdf_path: Path, supplied_path: str | None) -> str:
    """优先使用显式相对路径，否则要求输入文件位于项目根目录内。"""

    if supplied_path is not None:
        return supplied_path
    try:
        return pdf_path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("项目外 PDF 必须显式提供 --relative-path") from exc


def _resolve_output_path(document_id: str, supplied_path: Path | None) -> Path:
    """生成安全默认输出路径，显式输出路径则保持调用方选择。"""

    if supplied_path is not None:
        return supplied_path
    if not SAFE_DOCUMENT_ID_PATTERN.fullmatch(document_id) or document_id in {".", ".."}:
        raise ValueError("默认输出要求 document_id 不含路径分隔符")
    return PROJECT_ROOT / "data_processed" / "pages" / f"{document_id}.jsonl"


def main() -> int:
    """运行单文件解析，输出 Page 状态统计和 JSONL 路径。"""

    args = parse_args()
    pdf_path = args.pdf if args.pdf.is_absolute() else PROJECT_ROOT / args.pdf
    relative_path = _resolve_relative_path(pdf_path, args.relative_path)
    output_path = _resolve_output_path(args.document_id, args.output)

    parser = TextPdfParser()
    pages = parser.parse_to_jsonl(
        pdf_path,
        output_path,
        document_id=args.document_id,
        source_category=args.source_category,
        relative_path=relative_path,
    )
    statuses = Counter(page.text_status.value for page in pages)
    print(
        f"解析完成：总页数 {len(pages)}，success {statuses['success']}，"
        f"empty {statuses['empty']}，failed {statuses['failed']}。"
    )
    print(f"输出：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
