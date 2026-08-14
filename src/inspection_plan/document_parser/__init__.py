"""统一文档解析数据结构的公共入口。

当前包只公开 Page 数据模型及其最小枚举。PDF 文本提取、OCR 和 Clause
解析器将在后续任务中实现，并统一以 Page 作为页面级输出契约。
"""

from .models import Page, ParseMethod, TextStatus

__all__ = ["Page", "ParseMethod", "TextStatus"]
