"""统一 Page 数据结构及文本型、扫描型 PDF Parser 的公共入口。

TextPdfParser 使用 PDF 文本层，OcrPdfParser 使用页面渲染和 RapidOCR；两条
路径均输出 Page。自动路由与 Clause Parser 将在后续任务中实现。
"""

from .models import Page, ParseMethod, TextStatus
from .ocr_pdf_parser import DEFAULT_OCR_DPI, OcrPdfParser
from .text_pdf_parser import PdfOpenError, TextPdfParser

__all__ = [
    "DEFAULT_OCR_DPI",
    "OcrPdfParser",
    "Page",
    "ParseMethod",
    "PdfOpenError",
    "TextPdfParser",
    "TextStatus",
]
