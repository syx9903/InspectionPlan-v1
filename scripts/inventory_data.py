"""盘点 InspectionPlan 原始资料文件并生成 JSON 与 Markdown 报告。

脚本只读取文件路径、扩展名、大小以及 PDF 页数，不读取 PDF 正文，
也不解析 DOCX 的段落、表格或其他内容。每个文件独立处理，单个文件损坏时
会在记录中保存异常摘要，并继续盘点剩余文件。

默认输入为项目根目录下的 ``data/``，默认输出为
``data_processed/inventory/data_inventory.json`` 和
``docs/data_inventory.md``。重复执行会用最新盘点结果覆盖这两个生成文件。
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pymupdf


SOURCE_CATEGORIES = ("检验规范", "球罐标准", "检验方案")


def normalize_extension(path: Path) -> str:
    """返回文件名后缀的小写形式，无后缀时返回空字符串。"""

    return path.suffix.lower()


def inspect_file(path: Path, project_root: Path, source_category: str) -> dict[str, Any]:
    """读取单个文件在本任务范围内允许获取的基础元数据。

    Args:
        path: 待盘点文件路径。
        project_root: 用于生成可迁移相对路径的项目根目录。
        source_category: 文件所属的三类原始资料目录名称。

    Returns:
        包含路径、类型、大小、PDF 页数和读取状态的记录。任何读取异常都会
        转换为 ``readable=false`` 的记录，不会继续向上抛出并中止批处理。
    """

    extension = normalize_extension(path)
    record: dict[str, Any] = {
        "source_category": source_category,
        "relative_path": path.relative_to(project_root).as_posix(),
        "file_name": path.name,
        "extension": extension,
        "size_bytes": None,
        "pdf_pages": None,
        "readable": False,
        "error": None,
    }

    try:
        record["size_bytes"] = path.stat().st_size
        if extension == ".pdf":
            # 这里只读取文档容器的页数，禁止加载页面或提取页面正文。
            with pymupdf.open(path) as document:
                record["pdf_pages"] = len(document)
        else:
            # 读取一个字节仅验证文件可打开，不解释 DOCX 或其他文件的内容。
            with path.open("rb") as file_handle:
                file_handle.read(1)
        record["readable"] = True
    except Exception as exc:  # noqa: BLE001 - 批处理必须隔离任意单文件读取异常。
        record["error"] = f"{type(exc).__name__}: {exc}"

    return record


def scan_source_directories(project_root: Path) -> list[dict[str, Any]]:
    """按固定的三类来源目录递归扫描文件并返回稳定排序的盘点记录。

    缺失的来源目录属于项目结构错误，会直接抛出 ``FileNotFoundError``；
    目录存在后，单个文件的异常由 :func:`inspect_file` 隔离。
    """

    records: list[dict[str, Any]] = []
    for source_category in SOURCE_CATEGORIES:
        source_directory = project_root / "data" / source_category
        if not source_directory.is_dir():
            raise FileNotFoundError(f"缺少原始资料目录：data/{source_category}")

        files = sorted(
            (path for path in source_directory.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(project_root).as_posix().casefold(),
        )
        records.extend(
            inspect_file(path, project_root, source_category) for path in files
        )

    return records


def build_summary(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """汇总总体及各来源目录的文件数量、类型、页数和读取状态。"""

    record_list = list(records)
    by_source_category: dict[str, dict[str, int]] = {}

    for source_category in SOURCE_CATEGORIES:
        category_records = [
            record
            for record in record_list
            if record["source_category"] == source_category
        ]
        by_source_category[source_category] = _summarize_records(category_records)

    summary = _summarize_records(record_list)
    summary["by_source_category"] = by_source_category
    return summary


def _summarize_records(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    """计算一组盘点记录的基础统计，供总体和分类汇总复用。"""

    total_pdf = sum(record["extension"] == ".pdf" for record in records)
    total_docx = sum(record["extension"] == ".docx" for record in records)
    readable_files = sum(bool(record["readable"]) for record in records)
    return {
        "total_files": len(records),
        "total_pdf": total_pdf,
        "total_docx": total_docx,
        "total_other": len(records) - total_pdf - total_docx,
        "total_pdf_pages": sum(record["pdf_pages"] or 0 for record in records),
        "readable_files": readable_files,
        "unreadable_files": len(records) - readable_files,
    }


def write_json_inventory(
    output_path: Path,
    summary: dict[str, Any],
    records: Sequence[dict[str, Any]],
) -> None:
    """以 UTF-8 JSON 写入机器可读盘点结果，并创建所需父目录。"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "files": list(records)}
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_markdown_report(
    report_path: Path,
    summary: dict[str, Any],
    records: Sequence[dict[str, Any]],
) -> None:
    """生成便于人工核对的 Markdown 汇总、文件明细与异常列表。"""

    lines = [
        "# 原始资料文件盘点",
        "",
        "> 本报告只统计文件基础元数据和 PDF 页数，不代表 PDF 正文可解析。",
        "",
        "## 总体统计",
        "",
        "| 项目 | 数量 |",
        "| --- | ---: |",
        f"| 总文件 | {summary['total_files']} |",
        f"| PDF | {summary['total_pdf']} |",
        f"| DOCX | {summary['total_docx']} |",
        f"| 其他 | {summary['total_other']} |",
        f"| PDF 总页数 | {summary['total_pdf_pages']} |",
        f"| 无法读取 | {summary['unreadable_files']} |",
        "",
        "## 按目录统计",
        "",
        "| 目录类别 | 文件数 | PDF 数 | DOCX 数 | PDF 总页数 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]

    for source_category in SOURCE_CATEGORIES:
        category = summary["by_source_category"][source_category]
        lines.append(
            f"| {source_category} | {category['total_files']} | "
            f"{category['total_pdf']} | {category['total_docx']} | "
            f"{category['total_pdf_pages']} |"
        )

    lines.extend(
        [
            "",
            "## 文件明细",
            "",
            "| 目录类别 | 文件名 | 类型 | 文件大小（字节） | PDF 页数 | 读取状态 |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for record in records:
        file_name = _escape_markdown_cell(record["file_name"])
        pages = record["pdf_pages"] if record["pdf_pages"] is not None else "—"
        size = record["size_bytes"] if record["size_bytes"] is not None else "—"
        status = "正常" if record["readable"] else "异常"
        lines.append(
            f"| {record['source_category']} | {file_name} | "
            f"{record['extension'] or '无扩展名'} | {size} | {pages} | {status} |"
        )

    unreadable_records = [record for record in records if not record["readable"]]
    lines.extend(["", "## 异常文件", ""])
    if unreadable_records:
        lines.extend(
            [
                "| 相对路径 | 异常摘要 |",
                "| --- | --- |",
            ]
        )
        for record in unreadable_records:
            lines.append(
                f"| {_escape_markdown_cell(record['relative_path'])} | "
                f"{_escape_markdown_cell(record['error'] or '')} |"
            )
    else:
        lines.append("未发现基础元数据读取异常文件。")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _escape_markdown_cell(value: str) -> str:
    """转义 Markdown 表格中会破坏列结构的竖线和换行。"""

    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def create_inventory(project_root: Path) -> dict[str, Any]:
    """执行完整盘点并写入默认 JSON 与 Markdown 输出文件。"""

    resolved_root = project_root.resolve()
    records = scan_source_directories(resolved_root)
    summary = build_summary(records)
    write_json_inventory(
        resolved_root / "data_processed" / "inventory" / "data_inventory.json",
        summary,
        records,
    )
    write_markdown_report(
        resolved_root / "docs" / "data_inventory.md",
        summary,
        records,
    )
    return {"summary": summary, "files": records}


def parse_args() -> argparse.Namespace:
    """解析可选项目根目录参数，默认使用脚本所在仓库根目录。"""

    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="盘点三类 InspectionPlan 原始资料")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=default_root,
        help="项目根目录；默认自动定位当前脚本所在仓库",
    )
    return parser.parse_args()


def main() -> int:
    """运行盘点并在控制台输出关键统计，成功时返回零退出码。"""

    args = parse_args()
    inventory = create_inventory(args.project_root)
    summary = inventory["summary"]
    print(
        "盘点完成："
        f"文件 {summary['total_files']} 个，PDF {summary['total_pdf']} 个，"
        f"DOCX {summary['total_docx']} 个，异常 {summary['unreadable_files']} 个。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
