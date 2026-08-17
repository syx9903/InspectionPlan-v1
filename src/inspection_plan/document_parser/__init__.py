"""统一 Page 数据结构、两类 Parser 及页级路由器的公共入口。

TextPdfParser 使用 PDF 文本层，OcrPdfParser 使用页面渲染和 RapidOCR；两条
路径均输出 Page。PdfPageRouter 在单次遍历中逐页选择路径；Clause Parser
仍属于后续任务。
"""

from .models import Page, ParseMethod, TextStatus
from .ocr_pdf_parser import DEFAULT_OCR_DPI, OcrPdfParser
from .pdf_page_router import MIN_MEANINGFUL_CHARACTERS, PdfPageRouter
from .text_pdf_parser import PdfOpenError, TextPdfParser

__all__ = [
    "DEFAULT_OCR_DPI",
    "OcrPdfParser",
    "Page",
    "ParseMethod",
    "PdfPageRouter",
    "PdfOpenError",
    "MIN_MEANINGFUL_CHARACTERS",
    "TextPdfParser",
    "TextStatus",
]
