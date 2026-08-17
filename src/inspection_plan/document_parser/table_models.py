"""定义独立于 Page 的法规表格结构与来源证据模型。

模型表达 ``PDF Page → Table → Cell`` 的二维结构，保存原始 OCR 文字、人工核验值、
坐标、合并关系和风险提示。它不调用 PP-StructureV3，不解析 HTML，不执行 OCR 纠错，
也不包含压力、材料或条款号等法规语义。Table 通过 document_id、relative_path 和
1-based page_no 与来源页关联，当前不要求 Page 持有 tables 字段。

所有模型使用冻结 dataclass，避免下游在不留痕的情况下覆盖 raw_text；通过 to_dict
和 to_json 输出稳定的 JSON 基础类型。风险标记只是复核信号，不是正确性判断。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, TypeVar


class CellContentType(StrEnum):
    """单元格内容的最小类型，不承担法规语义抽取。"""

    TEXT = "text"
    NUMERIC = "numeric"
    MIXED = "mixed"
    EMPTY = "empty"


class CellRiskFlag(StrEnum):
    """提示下游重点核验的最小风险集合。

    ``NUMERIC_CONTENT`` 和 ``SPECIAL_SYMBOL`` 描述内容敏感性，不表示识别必然错误；
    ``OCR_LOW_CONFIDENCE`` 是模型信号；``MANUAL_REVIEW_REQUIRED`` 是流程要求。
    """

    NUMERIC_CONTENT = "numeric_content"
    SPECIAL_SYMBOL = "special_symbol"
    OCR_LOW_CONFIDENCE = "ocr_low_confidence"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class ReviewStatus(StrEnum):
    """单元格从未核验到人工确认或修正的生命周期。"""

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    CORRECTED = "corrected"


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """表示页面坐标系中的矩形证据区域。

    坐标单位继承上游版面工具，模型不擅自换算像素或 PDF point。只要求四个值有限，
    且右下坐标不小于左上坐标，以便以后在同一来源图像上定位证据。
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        """校验坐标类型、有限性和矩形方向。"""

        for field_name in ("x0", "y0", "x1", "y1"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{field_name} 必须是有限数字")
            if not math.isfinite(value):
                raise ValueError(f"{field_name} 必须是有限数字")
        if self.x1 < self.x0:
            raise ValueError("bbox 必须满足 x1 >= x0")
        if self.y1 < self.y0:
            raise ValueError("bbox 必须满足 y1 >= y0")

    def to_dict(self) -> dict[str, float]:
        """返回JSON兼容的四坐标字典。"""

        return {
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
        }


@dataclass(frozen=True, slots=True)
class TableCell:
    """表示表格中一个原始或合并单元格的结构与证据。

    行列索引采用1-based规则，指向合并单元格左上角。``raw_text`` 永久保存上游
    识别值；人工核验写入 ``verified_text``，不能覆盖raw。OCR confidence可空，
    因为第三方输出不一定能稳定把文字级置信度聚合到每个cell，且confidence不是
    法规数字正确性的证明。
    """

    row_index: int
    column_index: int
    bbox: BoundingBox
    raw_text: str
    content_type: CellContentType | str
    rowspan: int = 1
    colspan: int = 1
    verified_text: str | None = None
    review_status: ReviewStatus | str = ReviewStatus.UNREVIEWED
    risk_flags: tuple[CellRiskFlag | str, ...] = ()
    ocr_confidence: float | None = None

    def __post_init__(self) -> None:
        """规范枚举并拒绝坐标、跨度、置信度和核验状态矛盾。"""

        _validate_one_based_integer("row_index", self.row_index)
        _validate_one_based_integer("column_index", self.column_index)
        _validate_one_based_integer("rowspan", self.rowspan)
        _validate_one_based_integer("colspan", self.colspan)
        if not isinstance(self.bbox, BoundingBox):
            raise TypeError("bbox 必须是 BoundingBox")
        if not isinstance(self.raw_text, str):
            raise TypeError("raw_text 必须是字符串")

        content_type = _coerce_enum(CellContentType, self.content_type, "content_type")
        review_status = _coerce_enum(ReviewStatus, self.review_status, "review_status")
        risk_flags = _coerce_risk_flags(self.risk_flags)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "review_status", review_status)
        object.__setattr__(self, "risk_flags", risk_flags)

        self._validate_review_state()
        self._validate_confidence()

    def _validate_review_state(self) -> None:
        """确保人工状态与verified_text含义一致，保护原始OCR值。"""

        if self.verified_text is not None and not isinstance(self.verified_text, str):
            raise TypeError("verified_text 必须是字符串或 None")
        if self.review_status is ReviewStatus.UNREVIEWED:
            if self.verified_text is not None:
                raise ValueError("unreviewed 单元格的 verified_text 必须为 None")
            return
        if self.verified_text is None:
            raise ValueError("reviewed/corrected 单元格必须提供 verified_text")
        if self.review_status is ReviewStatus.REVIEWED and self.verified_text != self.raw_text:
            raise ValueError("reviewed 表示确认原值，verified_text 必须等于 raw_text")
        if self.review_status is ReviewStatus.CORRECTED and self.verified_text == self.raw_text:
            raise ValueError("corrected 表示发生修正，verified_text 必须区别于 raw_text")

    def _validate_confidence(self) -> None:
        """置信度存在时必须位于0到1之间，但不据此推断正确性。"""

        if self.ocr_confidence is None:
            return
        if isinstance(self.ocr_confidence, bool) or not isinstance(
            self.ocr_confidence, (int, float)
        ):
            raise TypeError("ocr_confidence 必须是0到1之间的数字或 None")
        if not math.isfinite(self.ocr_confidence) or not 0 <= self.ocr_confidence <= 1:
            raise ValueError("ocr_confidence 必须位于0到1之间")

    def to_dict(self) -> dict[str, Any]:
        """序列化全部结构、原值、核验值和风险字段。"""

        return {
            "row_index": self.row_index,
            "column_index": self.column_index,
            "bbox": self.bbox.to_dict(),
            "rowspan": self.rowspan,
            "colspan": self.colspan,
            "raw_text": self.raw_text,
            "verified_text": self.verified_text,
            "content_type": self.content_type.value,
            "review_status": self.review_status.value,
            "risk_flags": [flag.value for flag in self.risk_flags],
            "ocr_confidence": self.ocr_confidence,
        }


@dataclass(frozen=True, slots=True)
class Table:
    """表示来源明确、可回查原页的独立二维表格证据。

    Table不嵌入Page，而以document_id、relative_path和page_no建立来源关联。
    ``raw_html`` 保留上游近原始结构，cells提供工具无关的最小二维表示；两者并存
    可以避免适配过程丢失rowspan/colspan证据。本模型只校验明显边界，不尝试验证
    合并单元格是否完整覆盖矩阵。
    """

    table_id: str
    document_id: str
    source_category: str
    relative_path: str
    page_no: int
    table_index: int
    bbox: BoundingBox
    row_count: int
    column_count: int
    cells: tuple[TableCell, ...]
    raw_html: str | None = None

    def __post_init__(self) -> None:
        """校验来源、表格边界以及所有Cell的显式范围约束。"""

        _validate_non_empty_string("table_id", self.table_id)
        _validate_non_empty_string("document_id", self.document_id)
        _validate_non_empty_string("source_category", self.source_category)
        _validate_relative_path(self.relative_path)
        _validate_one_based_integer("page_no", self.page_no)
        _validate_one_based_integer("table_index", self.table_index)
        _validate_one_based_integer("row_count", self.row_count)
        _validate_one_based_integer("column_count", self.column_count)
        if not isinstance(self.bbox, BoundingBox):
            raise TypeError("bbox 必须是 BoundingBox")
        if not isinstance(self.raw_html, (str, type(None))):
            raise TypeError("raw_html 必须是字符串或 None")

        cells = tuple(self.cells)
        if any(not isinstance(cell, TableCell) for cell in cells):
            raise TypeError("cells 中每一项都必须是 TableCell")
        object.__setattr__(self, "cells", cells)
        self._validate_cells()

    def _validate_cells(self) -> None:
        """校验Cell锚点和跨度不越界，但不实现复杂矩阵覆盖算法。"""

        anchors: set[tuple[int, int]] = set()
        for cell in self.cells:
            if cell.row_index > self.row_count:
                raise ValueError("cell row_index 不能超过 row_count")
            if cell.column_index > self.column_count:
                raise ValueError("cell column_index 不能超过 column_count")
            if cell.row_index + cell.rowspan - 1 > self.row_count:
                raise ValueError("cell rowspan 不能越过表格行边界")
            if cell.column_index + cell.colspan - 1 > self.column_count:
                raise ValueError("cell colspan 不能越过表格列边界")
            anchor = (cell.row_index, cell.column_index)
            if anchor in anchors:
                raise ValueError("cells 不能包含重复的 row_index/column_index 锚点")
            anchors.add(anchor)

    def to_dict(self) -> dict[str, Any]:
        """返回可直接写入JSON且保持Unicode的稳定字典。"""

        return {
            "table_id": self.table_id,
            "document_id": self.document_id,
            "source_category": self.source_category,
            "relative_path": self.relative_path,
            "page_no": self.page_no,
            "table_index": self.table_index,
            "bbox": self.bbox.to_dict(),
            "row_count": self.row_count,
            "column_count": self.column_count,
            "cells": [cell.to_dict() for cell in self.cells],
            "raw_html": self.raw_html,
        }

    def to_json(self) -> str:
        """使用ensure_ascii=False序列化，避免特殊圈号被二次损坏。"""

        return json.dumps(self.to_dict(), ensure_ascii=False)


EnumType = TypeVar("EnumType", bound=StrEnum)


def _coerce_enum(
    enum_type: type[EnumType], value: object, field_name: str
) -> EnumType:
    """把合法字符串转为指定枚举，并输出包含字段名的错误。"""

    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} 只允许：{allowed}") from exc


def _coerce_risk_flags(
    flags: tuple[CellRiskFlag | str, ...],
) -> tuple[CellRiskFlag, ...]:
    """规范风险枚举、拒绝重复项，并保持调用方给定顺序。"""

    if not isinstance(flags, (tuple, list)):
        raise TypeError("risk_flags 必须是tuple或list")
    normalized = tuple(_coerce_enum(CellRiskFlag, flag, "risk_flags") for flag in flags)
    if len(set(normalized)) != len(normalized):
        raise ValueError("risk_flags 不能包含重复项")
    return normalized


def _validate_one_based_integer(field_name: str, value: object) -> None:
    """校验业务可见索引或计数是大于等于1的整数。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} 必须是整数")
    if value < 1:
        raise ValueError(f"{field_name} 采用1-based/正计数规则，必须大于等于1")


def _validate_non_empty_string(field_name: str, value: object) -> None:
    """校验来源标识字段为非空白字符串。"""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} 必须是字符串")
    if not value.strip():
        raise ValueError(f"{field_name} 不能为空")


def _validate_relative_path(relative_path: object) -> None:
    """保证来源路径可迁移，不接受绝对路径、反斜杠或越级段。"""

    _validate_non_empty_string("relative_path", relative_path)
    assert isinstance(relative_path, str)
    if "\\" in relative_path:
        raise ValueError("relative_path 必须使用正斜杠")
    path = PurePosixPath(relative_path)
    if path.is_absolute() or PureWindowsPath(relative_path).is_absolute():
        raise ValueError("relative_path 必须是项目根目录相对路径")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative_path 不能包含空段、当前目录或上级目录")
