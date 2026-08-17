"""统一 Page、独立 Table 数据结构及页面解析组件的公共入口。

TextPdfParser 使用 PDF 文本层，OcrPdfParser 使用页面渲染和 RapidOCR；两条
路径均输出 Page。Table/TableCell 当前只表达独立二维证据，尚未接入Parser或
Page。PdfPageRouter 在单次遍历中逐页选择路径；Clause Parser仍属于后续任务。
"""

from .models import Page, ParseMethod, TextStatus
from .ocr_pdf_parser import DEFAULT_OCR_DPI, OcrPdfParser
from .pdf_page_router import MIN_MEANINGFUL_CHARACTERS, PdfPageRouter
from .text_pdf_parser import PdfOpenError, TextPdfParser
from .table_models import (
    BoundingBox,
    CellContentType,
    CellRiskFlag,
    ReviewStatus,
    Table,
    TableCell,
)

__all__ = [
    "DEFAULT_OCR_DPI",
    "BoundingBox",
    "CellContentType",
    "CellRiskFlag",
    "OcrPdfParser",
    "Page",
    "ParseMethod",
    "PdfPageRouter",
    "PdfOpenError",
    "ReviewStatus",
    "Table",
    "TableCell",
    "MIN_MEANINGFUL_CHARACTERS",
    "TextPdfParser",
    "TextStatus",
]
