"""验证原始资料盘点脚本的页数、容错、汇总和路径行为。"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from scripts.inventory_data import (
    SOURCE_CATEGORIES,
    build_summary,
    inspect_file,
    normalize_extension,
    scan_source_directories,
)


def _create_source_directories(project_root: Path) -> None:
    """在临时项目中创建脚本要求的三类来源目录。"""

    for source_category in SOURCE_CATEGORIES:
        (project_root / "data" / source_category).mkdir(parents=True)


def _create_pdf(path: Path, page_count: int) -> None:
    """创建只含指定空白页数的临时 PDF，避免依赖真实业务资料。"""

    with pymupdf.open() as document:
        for _ in range(page_count):
            document.new_page()
        document.save(path)


def test_pdf_page_count_is_recorded(tmp_path: Path) -> None:
    """PDF 记录应包含容器页数，且基础读取状态为成功。"""

    pdf_path = tmp_path / "sample.pdf"
    _create_pdf(pdf_path, 3)

    record = inspect_file(pdf_path, tmp_path, "检验规范")

    assert record["pdf_pages"] == 3
    assert record["readable"] is True
    assert record["error"] is None


def test_extension_is_normalized_to_lowercase() -> None:
    """混合大小写扩展名应统一转换为小写。"""

    assert normalize_extension(Path("历史方案.DoCx")) == ".docx"


def test_broken_pdf_does_not_stop_batch(tmp_path: Path) -> None:
    """损坏 PDF 应记录异常，同时后续正常文件仍能完成盘点。"""

    _create_source_directories(tmp_path)
    broken_pdf = tmp_path / "data" / "检验规范" / "a-broken.pdf"
    broken_pdf.write_bytes(b"not a pdf")
    valid_pdf = tmp_path / "data" / "检验规范" / "b-valid.pdf"
    _create_pdf(valid_pdf, 2)

    records = scan_source_directories(tmp_path)

    assert len(records) == 2
    assert records[0]["readable"] is False
    assert records[0]["error"]
    assert records[1]["readable"] is True
    assert records[1]["pdf_pages"] == 2


def test_summary_counts_types_pages_and_readability() -> None:
    """总体和分类汇总应正确计算类型、页数及异常数量。"""

    records = [
        {
            "source_category": "检验规范",
            "extension": ".pdf",
            "pdf_pages": 10,
            "readable": True,
        },
        {
            "source_category": "球罐标准",
            "extension": ".pdf",
            "pdf_pages": None,
            "readable": False,
        },
        {
            "source_category": "检验方案",
            "extension": ".docx",
            "pdf_pages": None,
            "readable": True,
        },
        {
            "source_category": "检验方案",
            "extension": ".txt",
            "pdf_pages": None,
            "readable": True,
        },
    ]

    summary = build_summary(records)

    assert summary["total_files"] == 4
    assert summary["total_pdf"] == 2
    assert summary["total_docx"] == 1
    assert summary["total_other"] == 1
    assert summary["total_pdf_pages"] == 10
    assert summary["readable_files"] == 3
    assert summary["unreadable_files"] == 1
    assert summary["by_source_category"]["检验方案"]["total_files"] == 2


def test_relative_path_does_not_contain_project_root(tmp_path: Path) -> None:
    """输出路径必须相对项目根目录，不能泄漏本机绝对路径。"""

    file_path = tmp_path / "data" / "检验方案" / "示例.DOCX"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"fixture")

    record = inspect_file(file_path, tmp_path, "检验方案")

    assert record["relative_path"] == "data/检验方案/示例.DOCX"
    assert not Path(record["relative_path"]).is_absolute()
    assert str(tmp_path) not in record["relative_path"]
