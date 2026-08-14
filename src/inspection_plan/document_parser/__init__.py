"""统一文档解析数据结构与文本型 PDF Parser 的公共入口。

当前包公开 Page 数据模型和最小文本型 PDF Parser。OCR 与 Clause Parser
将在后续任务中实现，并统一以 Page 作为页面级数据契约。
"""

from .models import Page, ParseMethod, TextStatus
from .text_pdf_parser import PdfOpenError, TextPdfParser

__all__ = [
    "Page",
    "ParseMethod",
    "PdfOpenError",
    "TextPdfParser",
    "TextStatus",
]
