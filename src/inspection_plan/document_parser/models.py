"""定义文本提取与 OCR 解析路径共享的最小 Page 数据模型。

Page 位于解析器与 Clause Parser 之间，只表达页面最终文本、来源、解析方式和
状态。模型不读取 PDF、不执行 OCR，也不保存坐标、表格、图片或 Clause。
调用者提供字段后，模型负责拒绝明显矛盾状态，并提供稳定的 dict/JSON 序列化。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


class ParseMethod(StrEnum):
    """页面最终文本的产生方式。

    ``TEXT`` 表示直接使用 PDF 文本层，``OCR`` 表示文本来自 OCR。模型不提供
    ``unknown``，因为 Page 应由已经选定解析路径的 Parser 创建。
    """

    TEXT = "text"
    OCR = "ocr"


class TextStatus(StrEnum):
    """页面文本解析结果的最小状态集合。

    ``EMPTY`` 是成功完成解析但页面没有正文，与发生异常的 ``FAILED`` 不同。
    """

    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Page:
    """表示任意解析路径输出的一页统一业务数据。

    Page 供后续 Clause Parser 使用，不暴露 PyMuPDF 或 OCR 引擎对象。页码采用
    1-based 规则，与人工在 PDF 阅读器中看到的页序一致。``char_count`` 由
    ``len(text)`` 自动计算并包含空白字符，调用者不能传入不一致的计数。

    Attributes:
        document_id: 上游提供的稳定来源文档标识；本模型不负责生成。
        source_category: 来源目录类别，当前通常为“检验规范”或“球罐标准”。
        relative_path: 相对于项目根目录、使用正斜杠的可迁移文件路径。
        file_name: 原始文件名，必须与 ``relative_path`` 的末段一致。
        page_no: 从 1 开始的 PDF 人工页序。
        text: 最终提供给下游的页面正文；失败或空白页使用空字符串。
        parse_method: ``text`` 或 ``ocr``，表示最终文本的产生方式。
        text_status: ``success``、``empty`` 或 ``failed``。
        error: 失败时的简短异常摘要；正常及空白页为 ``None``。
        char_count: 包含空白在内的 ``text`` 字符数，由模型自动计算。
    """

    document_id: str
    source_category: str
    relative_path: str
    file_name: str
    page_no: int
    text: str
    parse_method: ParseMethod | str
    text_status: TextStatus | str
    error: str | None = None
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        """规范枚举、计算字符数并校验字段及跨字段一致性。"""

        _validate_non_empty_string("document_id", self.document_id)
        _validate_non_empty_string("source_category", self.source_category)
        _validate_non_empty_string("file_name", self.file_name)
        _validate_relative_path(self.relative_path, self.file_name)

        if isinstance(self.page_no, bool) or not isinstance(self.page_no, int):
            raise TypeError("page_no 必须是整数")
        if self.page_no < 1:
            raise ValueError("page_no 采用 1-based 规则，必须大于等于 1")
        if not isinstance(self.text, str):
            raise TypeError("text 必须是字符串")

        parse_method = _coerce_enum(ParseMethod, self.parse_method, "parse_method")
        text_status = _coerce_enum(TextStatus, self.text_status, "text_status")
        object.__setattr__(self, "parse_method", parse_method)
        object.__setattr__(self, "text_status", text_status)
        object.__setattr__(self, "char_count", len(self.text))

        self._validate_text_state()

    @property
    def ocr_used(self) -> bool:
        """返回页面最终文本是否来自 OCR，不额外存储重复状态。"""

        return self.parse_method is ParseMethod.OCR

    def _validate_text_state(self) -> None:
        """拒绝正文、状态和异常摘要之间的明显矛盾组合。"""

        if self.text_status is TextStatus.SUCCESS:
            if not self.text.strip():
                raise ValueError("success 页面必须包含非空白 text")
            if self.error is not None:
                raise ValueError("success 页面的 error 必须为 None")
            return

        if self.text_status is TextStatus.EMPTY:
            if self.text != "":
                raise ValueError("empty 页面的 text 必须是空字符串")
            if self.error is not None:
                raise ValueError("empty 页面的 error 必须为 None")
            return

        if self.text != "":
            raise ValueError("failed 页面的 text 必须是空字符串")
        if not isinstance(self.error, str) or not self.error.strip():
            raise ValueError("failed 页面必须提供非空 error 异常摘要")

    def to_dict(self) -> dict[str, Any]:
        """返回字段完整且只含 JSON 兼容基础类型的稳定字典。"""

        return {
            "document_id": self.document_id,
            "source_category": self.source_category,
            "relative_path": self.relative_path,
            "file_name": self.file_name,
            "page_no": self.page_no,
            "text": self.text,
            "parse_method": self.parse_method.value,
            "text_status": self.text_status.value,
            "char_count": self.char_count,
            "error": self.error,
        }

    def to_json(self) -> str:
        """以 UTF-8 友好的 JSON 字符串序列化全部 Page 字段。"""

        return json.dumps(self.to_dict(), ensure_ascii=False)


def _validate_non_empty_string(field_name: str, value: object) -> None:
    """校验必要标识字段是非空白字符串。"""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} 必须是字符串")
    if not value.strip():
        raise ValueError(f"{field_name} 不能为空")


def _validate_relative_path(relative_path: object, file_name: str) -> None:
    """拒绝绝对、反斜杠、越级或与文件名不一致的来源路径。"""

    _validate_non_empty_string("relative_path", relative_path)
    assert isinstance(relative_path, str)

    if "\\" in relative_path:
        raise ValueError("relative_path 必须使用正斜杠，不能包含 Windows 反斜杠")

    posix_path = PurePosixPath(relative_path)
    if posix_path.is_absolute() or PureWindowsPath(relative_path).is_absolute():
        raise ValueError("relative_path 必须是相对于项目根目录的路径")
    if any(part in {"", ".", ".."} for part in posix_path.parts):
        raise ValueError("relative_path 不能包含空段、当前目录或上级目录")
    if posix_path.name != file_name:
        raise ValueError("file_name 必须与 relative_path 的末段一致")


def _coerce_enum(
    enum_type: type[ParseMethod] | type[TextStatus],
    value: object,
    field_name: str,
) -> ParseMethod | TextStatus:
    """把合法字符串转换为枚举，并为非法值提供明确字段错误。"""

    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed_values = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} 只允许：{allowed_values}") from exc
