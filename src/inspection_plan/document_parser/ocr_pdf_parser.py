"""把单个明确选择 OCR 路径的扫描型 PDF 转换为 Page 和 JSONL。

Parser 初始化时创建或接收一个 OCR 引擎，同一实例供整份 PDF 的全部页面复用。
每页按默认 200 DPI 渲染为 RGB、无 alpha 的内存 PNG，RapidOCR 行文本按返回
顺序用换行拼接。模块不判断是否需要 OCR，不回退文本层，也不保存 bbox、
confidence、图片或性能字段到 Page。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

import pymupdf

from .models import Page, ParseMethod, TextStatus
from .text_pdf_parser import PdfOpenError


DEFAULT_OCR_DPI = 200
MIN_OCR_DPI = 72
MAX_OCR_DPI = 600


class OcrEngine(Protocol):
    """描述 OcrPdfParser 需要的最小 RapidOCR 兼容调用接口。"""

    def __call__(self, image: bytes) -> tuple[Any, Any]:
        """接收图片字节，返回 OCR 行结果与引擎内部耗时。"""


class OcrPdfParser:
    """将一个扫描型 PDF 的每一页通过 RapidOCR 转换为统一 Page。

    调用方显式选择 OCR 路径并提供文档元数据。构造函数只初始化一次 OCR；
    ``parse`` 遍历时不会重复创建模型。``last_run_stats`` 仅保存最近一次解析的
    文档级耗时，不进入 Page Schema，也不作为 OCR 质量结论。
    """

    def __init__(
        self,
        dpi: int = DEFAULT_OCR_DPI,
        ocr_engine: OcrEngine | None = None,
    ) -> None:
        """校验渲染 DPI，并初始化或接收一个可复用 OCR 引擎。

        Args:
            dpi: 页面渲染分辨率，默认使用 TASK-002.5 选定的 200 DPI baseline。
            ocr_engine: 可选 RapidOCR 兼容实例；测试可注入 mock，生产默认创建
                项目虚拟环境中已有的 RapidOCR。
        """

        self.dpi = self._validate_dpi(dpi)
        self._ocr_engine = ocr_engine or self._create_ocr_engine()
        self.last_run_stats: dict[str, int | float] = {
            "total_pages": 0,
            "total_seconds": 0.0,
            "average_seconds_per_page": 0.0,
        }

    def parse(
        self,
        pdf_path: Path,
        *,
        document_id: str,
        source_category: str,
        relative_path: str,
    ) -> list[Page]:
        """OCR 整个单文件 PDF，并按原始页序返回 Page 列表。

        Args:
            pdf_path: 本机待解析扫描型 PDF 的实际路径。
            document_id: 调用方提供的稳定文档标识。
            source_category: 调用方明确指定的来源类别。
            relative_path: 相对于项目根目录、使用正斜杠的追溯路径。

        Raises:
            FileNotFoundError: 输入不存在或不是普通文件。
            ValueError: 输入不是 PDF，或 Page 元数据违反统一模型约束。
            PdfOpenError: 文件存在但 PDF 容器无法打开或遍历。
        """

        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF 文件不存在或不是普通文件：{path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"OcrPdfParser 只接受 PDF 文件：{path.name}")

        started_at = perf_counter()
        pages: list[Page] = []
        try:
            with pymupdf.open(path) as document:
                for page_index in range(len(document)):
                    pages.append(
                        self._parse_page(
                            document[page_index],
                            page_no=page_index + 1,
                            document_id=document_id,
                            source_category=source_category,
                            relative_path=relative_path,
                            file_name=path.name,
                        )
                    )
        except (FileNotFoundError, ValueError):
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转换为文档级打开异常。
            raise PdfOpenError(
                f"无法打开或遍历 PDF {path.name}：{type(exc).__name__}: {exc}"
            ) from exc

        total_seconds = perf_counter() - started_at
        self.last_run_stats = {
            "total_pages": len(pages),
            "total_seconds": total_seconds,
            "average_seconds_per_page": total_seconds / len(pages) if pages else 0.0,
        }
        return pages

    def _parse_page(
        self,
        pdf_page: Any,
        *,
        page_no: int,
        document_id: str,
        source_category: str,
        relative_path: str,
        file_name: str,
    ) -> Page:
        """渲染并 OCR 单页，将结果映射为 success、empty 或 failed Page。"""

        try:
            image_bytes = self._render_page(pdf_page)
            raw_result, _engine_elapsed = self._ocr_engine(image_bytes)
            text = self._join_ocr_lines(raw_result)
        except Exception as exc:  # noqa: BLE001 - 单页失败必须记录后继续。
            return Page(
                document_id=document_id,
                source_category=source_category,
                relative_path=relative_path,
                file_name=file_name,
                page_no=page_no,
                text="",
                parse_method=ParseMethod.OCR,
                text_status=TextStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )

        if text.strip():
            page_text = text
            text_status = TextStatus.SUCCESS
        else:
            page_text = ""
            text_status = TextStatus.EMPTY

        return Page(
            document_id=document_id,
            source_category=source_category,
            relative_path=relative_path,
            file_name=file_name,
            page_no=page_no,
            text=page_text,
            parse_method=ParseMethod.OCR,
            text_status=text_status,
        )

    def _render_page(self, pdf_page: Any) -> bytes:
        """按当前 DPI 渲染 RGB、无 alpha 的内存 PNG，不保存页面图片。"""

        zoom = self.dpi / 72.0
        pixmap = pdf_page.get_pixmap(
            matrix=pymupdf.Matrix(zoom, zoom),
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        return pixmap.tobytes("png")

    @staticmethod
    def _join_ocr_lines(raw_result: Any) -> str:
        """按 RapidOCR 返回顺序换行拼接文字，不保存框和置信度。

        RapidOCR 正常无结果时返回 ``None``，映射为空正文。非标准结果结构会
        抛出异常并由页面级边界转换成 failed Page，避免静默丢失内容。
        """

        if raw_result is None:
            return ""

        texts: list[str] = []
        for index, item in enumerate(raw_result):
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                raise ValueError(
                    f"OCR 第 {index + 1} 条结果不是 [box, text, confidence]"
                )
            text = item[1]
            texts.append("" if text is None else str(text))
        return "\n".join(texts)

    @staticmethod
    def _validate_dpi(dpi: int) -> int:
        """限制 DPI 为 72～600 的整数，避免无效或异常大的渲染。"""

        if isinstance(dpi, bool) or not isinstance(dpi, int):
            raise TypeError("DPI 必须是整数")
        if not MIN_OCR_DPI <= dpi <= MAX_OCR_DPI:
            raise ValueError(f"DPI 必须位于 {MIN_OCR_DPI}～{MAX_OCR_DPI} 之间")
        return dpi

    @staticmethod
    def _create_ocr_engine() -> OcrEngine:
        """创建一次项目已有 RapidOCR，引擎在 Parser 生命周期内复用。"""

        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR()

    @staticmethod
    def write_jsonl(pages: Iterable[Page], output_path: Path) -> int:
        """按输入页序覆盖写入 UTF-8 Page JSONL，并返回行数。"""

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        page_count = 0
        with path.open("w", encoding="utf-8", newline="\n") as output_file:
            for page in pages:
                output_file.write(page.to_json())
                output_file.write("\n")
                page_count += 1
        return page_count

    def parse_to_jsonl(
        self,
        pdf_path: Path,
        output_path: Path,
        *,
        document_id: str,
        source_category: str,
        relative_path: str,
    ) -> list[Page]:
        """OCR 一个 PDF、写出 Page JSONL，并返回生成的 Page 列表。"""

        pages = self.parse(
            pdf_path,
            document_id=document_id,
            source_category=source_category,
            relative_path=relative_path,
        )
        self.write_jsonl(pages, output_path)
        return pages
