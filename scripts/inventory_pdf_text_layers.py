"""检测法规 PDF 的页面文本层可用性并生成 JSON 与 Markdown 报告。

脚本只处理 ``data/检验规范/`` 和 ``data/球罐标准/`` 中的 PDF。每页通过
PyMuPDF 临时提取文本并计算字符数量，输出仅保留统计值和分类，不保存正文。
脚本不渲染页面、不执行 OCR，也不把“无可用文本层”等同于已确认扫描件。

默认输出会覆盖 ``data_processed/inventory/pdf_text_layer_inventory.json`` 和
``docs/pdf_text_layer_analysis.md``，因此脚本可以在原始资料不变时重复执行。
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pymupdf


PDF_SOURCE_CATEGORIES = ("检验规范", "球罐标准")

# 少于 20 个中文、英文或数字字符的页面很可能只有页码、水印或孤立标记。
# 该值是可调整 baseline；它不评价文本是否正确，只排除明显过短的文本层。
MIN_MEANINGFUL_CHARACTERS = 20

# 文档中至少 90% 页面具有可用文本层时，暂归类为文本型文档。
TEXT_DOCUMENT_MIN_RATIO = 0.90

# 文档中最多 10% 页面具有可用文本层时，暂归类为基本无可用文本层。
NO_USABLE_TEXT_MAX_RATIO = 0.10

MEANINGFUL_CHARACTER_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fffA-Za-z0-9]")


def analyze_text(text: str, page_no: int) -> dict[str, Any]:
    """根据透明字符阈值判断单页提取文本是否达到 baseline 可用标准。

    Args:
        text: PyMuPDF 从当前页面提取的临时文本；函数不会保存其内容。
        page_no: 从 1 开始的 PDF 页码，用于后续人工定位。

    Returns:
        页码、三类字符长度、布尔判断和状态。``empty`` 表示没有非空白字符，
        ``too_short`` 表示存在文本但有效字符不足，``usable`` 表示达到阈值。
    """

    raw_text_length = len(text)
    non_whitespace_length = sum(not character.isspace() for character in text)
    meaningful_character_length = len(MEANINGFUL_CHARACTER_PATTERN.findall(text))

    if non_whitespace_length == 0:
        text_status = "empty"
        has_usable_text = False
    elif meaningful_character_length < MIN_MEANINGFUL_CHARACTERS:
        text_status = "too_short"
        has_usable_text = False
    else:
        text_status = "usable"
        has_usable_text = True

    return {
        "page_no": page_no,
        "raw_text_length": raw_text_length,
        "non_whitespace_length": non_whitespace_length,
        "meaningful_character_length": meaningful_character_length,
        "has_usable_text": has_usable_text,
        "text_status": text_status,
        "error": None,
    }


def classify_document(usable_text_pages: int, total_pages: int) -> str:
    """按可用文本页比例将 PDF 分类为 text、mixed 或 no_usable_text。

    ``text`` 仅表示至少 90% 页面达到页级字符阈值；``no_usable_text`` 仅表示
    最多 10% 页面达到阈值；其他比例为 ``mixed``。零页或无法打开的文档没有
    可验证文本页，保守归入 ``no_usable_text``，同时由文档 error 字段说明异常。
    """

    usable_text_ratio = usable_text_pages / total_pages if total_pages else 0.0
    if usable_text_ratio >= TEXT_DOCUMENT_MIN_RATIO:
        return "text"
    if usable_text_ratio <= NO_USABLE_TEXT_MAX_RATIO:
        return "no_usable_text"
    return "mixed"


def analyze_pdf(
    pdf_path: Path,
    project_root: Path,
    source_category: str,
) -> dict[str, Any]:
    """检测单个 PDF 的页级文本统计并生成文档级汇总。

    单页文本提取异常会生成 ``text_status=error`` 的不可用页并继续处理后续页；
    PDF 容器无法打开时则返回零页文档及异常摘要，使批处理继续处理其他文件。
    """

    page_results: list[dict[str, Any]] = []
    document_error: str | None = None

    try:
        with pymupdf.open(pdf_path) as document:
            total_pages = len(document)
            for page_index in range(total_pages):
                try:
                    # 本任务只临时提取文本用于计数，不保存正文或进行语义分析。
                    text = document[page_index].get_text("text")
                    page_results.append(analyze_text(text, page_index + 1))
                except Exception as exc:  # noqa: BLE001 - 单页异常不得中断整份 PDF。
                    page_results.append(
                        {
                            "page_no": page_index + 1,
                            "raw_text_length": 0,
                            "non_whitespace_length": 0,
                            "meaningful_character_length": 0,
                            "has_usable_text": False,
                            "text_status": "error",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
    except Exception as exc:  # noqa: BLE001 - 单文件异常不得中断全库检测。
        total_pages = 0
        document_error = f"{type(exc).__name__}: {exc}"

    usable_text_pages = sum(page["has_usable_text"] for page in page_results)
    non_usable_text_pages = total_pages - usable_text_pages
    usable_text_ratio = usable_text_pages / total_pages if total_pages else 0.0

    return {
        "source_category": source_category,
        "file_name": pdf_path.name,
        "relative_path": pdf_path.relative_to(project_root).as_posix(),
        "total_pages": total_pages,
        "usable_text_pages": usable_text_pages,
        "non_usable_text_pages": non_usable_text_pages,
        "usable_text_ratio": round(usable_text_ratio, 6),
        "document_text_type": classify_document(usable_text_pages, total_pages),
        "readable": document_error is None,
        "error": document_error,
        "pages": page_results,
    }


def scan_pdf_documents(project_root: Path) -> list[dict[str, Any]]:
    """扫描两个法规来源目录中的 PDF，并稳定排序返回文档检测结果。"""

    documents: list[dict[str, Any]] = []
    for source_category in PDF_SOURCE_CATEGORIES:
        source_directory = project_root / "data" / source_category
        if not source_directory.is_dir():
            raise FileNotFoundError(f"缺少 PDF 来源目录：data/{source_category}")

        pdf_paths = sorted(
            (
                path
                for path in source_directory.rglob("*")
                if path.is_file() and path.suffix.lower() == ".pdf"
            ),
            key=lambda path: path.relative_to(project_root).as_posix().casefold(),
        )
        documents.extend(
            analyze_pdf(path, project_root, source_category) for path in pdf_paths
        )

    return documents


def build_summary(documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """汇总整体及两个来源目录的文档分类和页级可用数量。"""

    document_list = list(documents)
    summary = _summarize_documents(document_list)
    summary["by_source_category"] = {
        source_category: _summarize_documents(
            [
                document
                for document in document_list
                if document["source_category"] == source_category
            ]
        )
        for source_category in PDF_SOURCE_CATEGORIES
    }
    return summary


def _summarize_documents(documents: Sequence[dict[str, Any]]) -> dict[str, int]:
    """计算一组 PDF 的文档类型、总页数、可用页数和异常数。"""

    return {
        "total_pdf": len(documents),
        "text_documents": sum(
            document["document_text_type"] == "text" for document in documents
        ),
        "mixed_documents": sum(
            document["document_text_type"] == "mixed" for document in documents
        ),
        "no_usable_text_documents": sum(
            document["document_text_type"] == "no_usable_text"
            for document in documents
        ),
        "total_pages": sum(document["total_pages"] for document in documents),
        "usable_text_pages": sum(
            document["usable_text_pages"] for document in documents
        ),
        "non_usable_text_pages": sum(
            document["non_usable_text_pages"] for document in documents
        ),
        "unreadable_documents": sum(not document["readable"] for document in documents),
    }


def select_samples(documents: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """为报告选择 2 个文本型、2 个无文本型及最多 2 个混合型真实样本。

    文本型选择比例最高者，无可用文本型选择比例最低者，混合型选择最接近
    50% 的文档，以便报告展示清晰的典型案例而不是复制大量正文。
    """

    text_documents = sorted(
        (
            document
            for document in documents
            if document["document_text_type"] == "text"
        ),
        key=lambda document: (-document["usable_text_ratio"], document["relative_path"]),
    )
    no_text_documents = sorted(
        (
            document
            for document in documents
            if document["document_text_type"] == "no_usable_text"
        ),
        key=lambda document: (document["usable_text_ratio"], document["relative_path"]),
    )
    mixed_documents = sorted(
        (
            document
            for document in documents
            if document["document_text_type"] == "mixed"
        ),
        key=lambda document: (
            abs(document["usable_text_ratio"] - 0.5),
            document["relative_path"],
        ),
    )
    return {
        "text": text_documents[:2],
        "no_usable_text": no_text_documents[:2],
        "mixed": mixed_documents[:2],
    }


def write_json_inventory(
    output_path: Path,
    summary: dict[str, Any],
    documents: Sequence[dict[str, Any]],
) -> None:
    """写入只包含字符统计、不包含正文的 UTF-8 JSON 运行产物。"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {"summary": summary, "documents": list(documents)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_markdown_report(
    report_path: Path,
    summary: dict[str, Any],
    documents: Sequence[dict[str, Any]],
) -> None:
    """生成检测方法、阈值、统计、文档明细、样本和局限说明。"""

    lines = [
        "# PDF 文本层可用性检测",
        "",
        "> 本报告描述文本层 baseline，不把无可用文本层等同于已确认扫描件。",
        "",
        "## 1. 检测方法",
        "",
        "```text",
        "PDF 页面",
        "→ PyMuPDF 提取临时文本",
        "→ 统计原始、非空白及中文/英文/数字字符",
        "→ 页级判断",
        "→ 文档级汇总与分类",
        "```",
        "",
        "完整正文不会写入 JSON 或报告，也未渲染页面或执行 OCR。",
        "",
        "## 2. 判定阈值",
        "",
        f"- 页级：中文、英文和数字字符合计至少 `{MIN_MEANINGFUL_CHARACTERS}` 个，判为 `usable`。",
        "- 页级：无非空白字符判为 `empty`；有字符但未达到阈值判为 `too_short`。",
        f"- 文档级：可用页比例 `>= {TEXT_DOCUMENT_MIN_RATIO:.2f}` 判为 `text`。",
        f"- 文档级：可用页比例 `<= {NO_USABLE_TEXT_MAX_RATIO:.2f}` 判为 `no_usable_text`。",
        "- 文档级：介于上述两个边界之间判为 `mixed`。",
        "",
        "20 字符阈值用于排除页码、水印和孤立标记。真实资料抽样中存在每页固定约 13 个有效字符的页面，若阈值为 10 会被误判为正文；阈值为 30 又会明显扩大不可用页面范围，因此采用 20 作为可调整 baseline。",
        "",
        "## 3. 总体统计",
        "",
        "| 项目 | 数量 |",
        "| --- | ---: |",
        f"| PDF 总数 | {summary['total_pdf']} |",
        f"| 总页数 | {summary['total_pages']} |",
        f"| 文本层可用页 | {summary['usable_text_pages']} |",
        f"| 不可用页 | {summary['non_usable_text_pages']} |",
        f"| 文本型 PDF | {summary['text_documents']} |",
        f"| 混合型 PDF | {summary['mixed_documents']} |",
        f"| 基本无可用文本层 PDF | {summary['no_usable_text_documents']} |",
        f"| 无法打开的 PDF | {summary['unreadable_documents']} |",
        "",
        "## 4. 按目录统计",
        "",
        "| 目录 | PDF | 总页数 | 可用页 | 不可用页 | 文本型 | 混合型 | 基本无可用文本层 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for source_category in PDF_SOURCE_CATEGORIES:
        category = summary["by_source_category"][source_category]
        lines.append(
            f"| {source_category} | {category['total_pdf']} | {category['total_pages']} | "
            f"{category['usable_text_pages']} | {category['non_usable_text_pages']} | "
            f"{category['text_documents']} | {category['mixed_documents']} | "
            f"{category['no_usable_text_documents']} |"
        )

    lines.extend(
        [
            "",
            "### 文档明细",
            "",
            "| 目录 | 文件名 | 页数 | 可用页 | 不可用页 | 可用比例 | 分类 |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for document in documents:
        lines.append(_document_markdown_row(document))

    lines.extend(["", "## 5. 抽样案例", ""])
    samples = select_samples(documents)
    sample_labels = {
        "text": "文本型",
        "no_usable_text": "基本无可用文本层",
        "mixed": "混合型",
    }
    for document_type in ("text", "no_usable_text", "mixed"):
        lines.extend([f"### {sample_labels[document_type]}", ""])
        if samples[document_type]:
            lines.extend(
                [
                    "| 文件名 | 页数 | 可用页 | 比例 | 分类 |",
                    "| --- | ---: | ---: | ---: | --- |",
                ]
            )
            for document in samples[document_type]:
                lines.append(
                    f"| {_escape_markdown_cell(document['file_name'])} | "
                    f"{document['total_pages']} | {document['usable_text_pages']} | "
                    f"{document['usable_text_ratio']:.2%} | "
                    f"{document['document_text_type']} |"
                )
        else:
            lines.append("当前资料中未发现该类型样本。")
        lines.append("")

    lines.extend(
        [
            "## 6. 局限",
            "",
            "- 有文本层不等于文本内容正确、完整或排版顺序可靠。",
            "- 已有 OCR 字符层仍可能乱码，但本任务不评价字符质量或语义。",
            "- 无可用文本层不等于 PDF 损坏，也不等于已确认扫描件。",
            "- 封面、目录、图纸和纯表格页可能因字符较少而被 baseline 判为不可用。",
            "- 20 字符及 90%/10% 阈值是可解释初始值，仍需结合人工抽查调整。",
            "- 是否真正需要 OCR 应由后续任务结合页面视觉内容和业务需求决定。",
        ]
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _document_markdown_row(document: dict[str, Any]) -> str:
    """把一条文档统计转换为 Markdown 表格行。"""

    return (
        f"| {document['source_category']} | "
        f"{_escape_markdown_cell(document['file_name'])} | "
        f"{document['total_pages']} | {document['usable_text_pages']} | "
        f"{document['non_usable_text_pages']} | "
        f"{document['usable_text_ratio']:.2%} | "
        f"{document['document_text_type']} |"
    )


def _escape_markdown_cell(value: str) -> str:
    """转义 Markdown 表格中的竖线和换行，避免破坏列结构。"""

    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def create_inventory(project_root: Path) -> dict[str, Any]:
    """执行全库文本层检测并写入默认 JSON 与 Markdown 输出。"""

    resolved_root = project_root.resolve()
    documents = scan_pdf_documents(resolved_root)
    summary = build_summary(documents)
    write_json_inventory(
        resolved_root
        / "data_processed"
        / "inventory"
        / "pdf_text_layer_inventory.json",
        summary,
        documents,
    )
    write_markdown_report(
        resolved_root / "docs" / "pdf_text_layer_analysis.md",
        summary,
        documents,
    )
    return {"summary": summary, "documents": documents}


def parse_args() -> argparse.Namespace:
    """解析可选项目根目录参数，默认自动定位脚本所在仓库。"""

    parser = argparse.ArgumentParser(description="检测法规 PDF 的文本层可用情况")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="项目根目录；默认自动定位当前脚本所在仓库",
    )
    return parser.parse_args()


def main() -> int:
    """运行文本层检测并输出总体结果，成功时返回零退出码。"""

    inventory = create_inventory(parse_args().project_root)
    summary = inventory["summary"]
    print(
        f"检测完成：PDF {summary['total_pdf']} 份，页面 {summary['total_pages']} 页；"
        f"文本型 {summary['text_documents']} 份，混合型 {summary['mixed_documents']} 份，"
        f"基本无可用文本层 {summary['no_usable_text_documents']} 份。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
