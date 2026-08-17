"""按页面文本层可用性在 Text 与 OCR 路径之间路由 PDF。

路由器只打开一次 PDF，并按原始页序提取临时文本。中文、英文和数字有效字符
达到 20 个的页面直接保留原始文本层；不足阈值的页面才惰性创建并复用
``OcrPdfParser``。两条路径最终产生同一 Page 模型，统计信息独立保存在路由器，
不进入 Page Schema。本模块不清洗文本、不判断乱码，也不执行版面或语义处理。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

import pymupdf

from .models import Page, ParseMethod, TextStatus
from .ocr_pdf_parser import DEFAULT_OCR_DPI, OcrPdfParser
from .text_pdf_parser import PdfOpenError, TextPdfParser


MIN_MEANINGFUL_CHARACTERS = 20
MEANINGFUL_CHARACTER_PATTERN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fffA-Za-z0-9]"
)


class PageOcrParser(Protocol):
    """描述路由器复用 OCR 单页能力所需的最小接口。"""

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
        """把当前已打开文档中的一页转换为 OCR Page。"""


class PdfPageRouter:
    """在单次 PDF 遍历中逐页选择文本层或 OCR。

    路由条件严格复用 TASK-002.2 的透明字符规则。阈值只选择解析方式，不会
    删除短文本页。OCR Parser 工厂仅在首个不可用文本页出现时调用一次，因此
    纯文本 PDF 完全不会初始化 RapidOCR，mixed 与扫描 PDF 则复用同一实例。
    """

    def __init__(
        self,
        *,
        min_meaningful_characters: int = MIN_MEANINGFUL_CHARACTERS,
        ocr_dpi: int = DEFAULT_OCR_DPI,
        ocr_parser_factory: Callable[[], PageOcrParser] | None = None,
    ) -> None:
        """配置页级阈值与惰性 OCR 工厂。

        Args:
            min_meaningful_characters: 中文、英文和数字有效字符阈值。默认 20；
                这是解析路径 baseline，不代表页面正文质量或语义正确性。
            ocr_dpi: 默认 OCR Parser 首次创建时使用的渲染 DPI。
            ocr_parser_factory: 可选无参工厂，测试可注入 mock Parser；未提供时
                首个 OCR 页会创建一个正式 ``OcrPdfParser``。
        """

        if (
            isinstance(min_meaningful_characters, bool)
            or not isinstance(min_meaningful_characters, int)
        ):
            raise TypeError("有效字符阈值必须是整数")
        if min_meaningful_characters < 1:
            raise ValueError("有效字符阈值必须大于等于 1")
        OcrPdfParser._validate_dpi(ocr_dpi)

        self.min_meaningful_characters = min_meaningful_characters
        self.ocr_dpi = ocr_dpi
        self._ocr_parser_factory = ocr_parser_factory
        self._ocr_parser: PageOcrParser | None = None
        self.last_run_stats: dict[str, int | float] = self._empty_stats()

    def parse(
        self,
        pdf_path: Path,
        *,
        document_id: str,
        source_category: str,
        relative_path: str,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> list[Page]:
        """单次打开 PDF，按原页码范围逐页路由并返回 Page。

        ``start_page`` 和 ``end_page`` 均为 1-based 且包含端点；省略时覆盖整份
        文档。OCR 实例在一次路由器生命周期内复用，统计中的初始化次数表示
        本次 ``parse`` 是否首次触发工厂。
        """

        path = Path(pdf_path)
        self._validate_pdf_path(path)
        self._validate_page_range_shape(start_page, end_page)
        started_at = perf_counter()
        pages: list[Page] = []
        initializations_before = int(self._ocr_parser is not None)

        try:
            with pymupdf.open(path) as document:
                first_page, last_page = self._resolve_page_range(
                    len(document), start_page, end_page
                )
                for page_no in range(first_page, last_page + 1):
                    pdf_page = document[page_no - 1]
                    pages.append(
                        self._route_page(
                            pdf_page,
                            page_no=page_no,
                            document_id=document_id,
                            source_category=source_category,
                            relative_path=relative_path,
                            file_name=path.name,
                        )
                    )
        except (FileNotFoundError, ValueError):
            raise
        except Exception as exc:  # noqa: BLE001 - 统一为明确的文档容器异常。
            raise PdfOpenError(
                f"无法打开或遍历 PDF {path.name}：{type(exc).__name__}: {exc}"
            ) from exc

        self.last_run_stats = self._build_stats(
            pages,
            ocr_initializations=int(self._ocr_parser is not None)
            - initializations_before,
            total_seconds=perf_counter() - started_at,
        )
        return pages

    def _route_page(
        self,
        pdf_page: Any,
        *,
        page_no: int,
        document_id: str,
        source_category: str,
        relative_path: str,
        file_name: str,
    ) -> Page:
        """提取一次文本层，达到阈值时用 Text，否则只对当前页 OCR。"""

        try:
            text = TextPdfParser._extract_text(pdf_page)
        except Exception:  # noqa: BLE001 - 文本读取失败时尝试 OCR 保留页面。
            return self._get_ocr_parser()._parse_page(
                pdf_page,
                page_no=page_no,
                document_id=document_id,
                source_category=source_category,
                relative_path=relative_path,
                file_name=file_name,
            )

        if self.count_meaningful_characters(text) >= self.min_meaningful_characters:
            return Page(
                document_id=document_id,
                source_category=source_category,
                relative_path=relative_path,
                file_name=file_name,
                page_no=page_no,
                text=text,
                parse_method=ParseMethod.TEXT,
                text_status=TextStatus.SUCCESS,
            )

        return self._get_ocr_parser()._parse_page(
            pdf_page,
            page_no=page_no,
            document_id=document_id,
            source_category=source_category,
            relative_path=relative_path,
            file_name=file_name,
        )

    def _get_ocr_parser(self) -> PageOcrParser:
        """首次需要 OCR 时创建一次 Parser，后续页面复用该实例。"""

        if self._ocr_parser is None:
            if self._ocr_parser_factory is None:
                self._ocr_parser = OcrPdfParser(dpi=self.ocr_dpi)
            else:
                self._ocr_parser = self._ocr_parser_factory()
        return self._ocr_parser

    @staticmethod
    def count_meaningful_characters(text: str) -> int:
        """按 TASK-002.2 规则统计中文、英文和数字字符。"""

        return len(MEANINGFUL_CHARACTER_PATTERN.findall(text))

    @staticmethod
    def write_jsonl(pages: Iterable[Page], output_path: Path) -> int:
        """按现有 Page Schema 和输入顺序覆盖写出 UTF-8 JSONL。"""

        return TextPdfParser.write_jsonl(pages, output_path)

    def parse_to_jsonl(
        self,
        pdf_path: Path,
        output_path: Path,
        *,
        document_id: str,
        source_category: str,
        relative_path: str,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> list[Page]:
        """完成页级路由并把同一 Page 列表写入 JSONL。"""

        pages = self.parse(
            pdf_path,
            document_id=document_id,
            source_category=source_category,
            relative_path=relative_path,
            start_page=start_page,
            end_page=end_page,
        )
        self.write_jsonl(pages, output_path)
        return pages

    @staticmethod
    def _validate_pdf_path(path: Path) -> None:
        """在打开前拒绝缺失文件和非 PDF 输入。"""

        if not path.is_file():
            raise FileNotFoundError(f"PDF 文件不存在或不是普通文件：{path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"PdfPageRouter 只接受 PDF 文件：{path.name}")

    @staticmethod
    def _validate_page_range_shape(
        start_page: int | None, end_page: int | None
    ) -> None:
        """校验可选页码的类型、1-based 下限和前后关系。"""

        for field_name, value in (("start_page", start_page), ("end_page", end_page)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise TypeError(f"{field_name} 必须是整数或 None")
            if value is not None and value < 1:
                raise ValueError(f"{field_name} 必须大于等于 1")
        if start_page is not None and end_page is not None and start_page > end_page:
            raise ValueError("start_page 不能大于 end_page")

    @staticmethod
    def _resolve_page_range(
        total_pages: int, start_page: int | None, end_page: int | None
    ) -> tuple[int, int]:
        """根据文档总页数补全范围并拒绝越界页码。"""

        first_page = 1 if start_page is None else start_page
        last_page = total_pages if end_page is None else end_page
        if total_pages < 1:
            raise ValueError("PDF 不包含可解析页面")
        if first_page > total_pages or last_page > total_pages:
            raise ValueError(f"页码范围超出 PDF 总页数 {total_pages}")
        return first_page, last_page

    @staticmethod
    def _empty_stats() -> dict[str, int | float]:
        """返回尚未解析文档时的零值统计。"""

        return {
            "total_pages": 0,
            "text_pages": 0,
            "ocr_pages": 0,
            "success_pages": 0,
            "empty_pages": 0,
            "failed_pages": 0,
            "ocr_initializations": 0,
            "total_seconds": 0.0,
        }

    @staticmethod
    def _build_stats(
        pages: list[Page], *, ocr_initializations: int, total_seconds: float
    ) -> dict[str, int | float]:
        """从最终 Page 计算独立文档统计，不向 Page 添加重复字段。"""

        methods = Counter(page.parse_method for page in pages)
        statuses = Counter(page.text_status for page in pages)
        return {
            "total_pages": len(pages),
            "text_pages": methods[ParseMethod.TEXT],
            "ocr_pages": methods[ParseMethod.OCR],
            "success_pages": statuses[TextStatus.SUCCESS],
            "empty_pages": statuses[TextStatus.EMPTY],
            "failed_pages": statuses[TextStatus.FAILED],
            "ocr_initializations": ocr_initializations,
            "total_seconds": total_seconds,
        }
