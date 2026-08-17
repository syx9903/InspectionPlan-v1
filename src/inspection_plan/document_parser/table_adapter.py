"""将普通dict形式的PP-StructureV3单表结果适配为内部Table模型。

Adapter只接收已序列化数据和调用方显式提供的来源信息，不导入PaddleOCR。结构以
``pred_html`` 为准，单元格bbox按 ``cell_box_list`` 与HTML cell遍历顺序一一映射；
两者数量不一致时拒绝转换。``table_ocr_pred`` 的文字框/置信度无法稳定聚合到cell，
因此当前不参与映射，所有 ``ocr_confidence`` 均为None。

HTML entity由标准库解析器解码成对应Unicode字符，这是结构解析所需的最小转换；
除此之外raw_text不trim、不规范化、不纠错。所有新Cell均为unreviewed，verified_text
为None。Adapter不调用模型、不检测表格，也不负责Page或Clause关联。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from .table_models import (
    BoundingBox,
    CellContentType,
    CellRiskFlag,
    ReviewStatus,
    Table,
    TableCell,
)


class TableAdapterError(ValueError):
    """表示第三方表格输出无法安全、确定地映射到内部模型。"""


@dataclass(frozen=True, slots=True)
class _HtmlCell:
    """保存HTML遍历阶段尚未分配行列坐标的真实单元格。"""

    raw_text: str
    rowspan: int
    colspan: int


class _TableHTMLParser(HTMLParser):
    """严格提取单个table中的tr/td/th，不尝试修复破损HTML。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_HtmlCell]] = []
        self.table_count = 0
        self._inside_table = False
        self._current_row: list[_HtmlCell] | None = None
        self._current_cell_text: list[str] | None = None
        self._current_span: tuple[int, int] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """开始table、row或cell，并校验不允许的嵌套状态。"""

        if tag == "table":
            if self._inside_table:
                raise TableAdapterError("pred_html 不允许嵌套 table")
            self.table_count += 1
            self._inside_table = True
            return
        if not self._inside_table:
            return
        if tag == "tr":
            if self._current_row is not None:
                raise TableAdapterError("pred_html 存在嵌套或未闭合 tr")
            self._current_row = []
            return
        if tag in {"td", "th"}:
            if self._current_row is None or self._current_cell_text is not None:
                raise TableAdapterError("td/th 必须位于已打开的 tr 内")
            attributes = dict(attrs)
            rowspan = _parse_span(attributes.get("rowspan"), "rowspan")
            colspan = _parse_span(attributes.get("colspan"), "colspan")
            self._current_cell_text = []
            self._current_span = (rowspan, colspan)

    def handle_data(self, data: str) -> None:
        """原样收集cell文字，包括空白；不做strip或Unicode规范化。"""

        if self._current_cell_text is not None:
            self._current_cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        """完成cell/row/table，并拒绝结束标签错位。"""

        if tag in {"td", "th"} and self._inside_table:
            if (
                self._current_row is None
                or self._current_cell_text is None
                or self._current_span is None
            ):
                raise TableAdapterError("pred_html 的td/th结束标签状态非法")
            rowspan, colspan = self._current_span
            self._current_row.append(
                _HtmlCell("".join(self._current_cell_text), rowspan, colspan)
            )
            self._current_cell_text = None
            self._current_span = None
            return
        if tag == "tr" and self._inside_table:
            if self._current_row is None or self._current_cell_text is not None:
                raise TableAdapterError("pred_html 的tr结束标签状态非法")
            self.rows.append(self._current_row)
            self._current_row = None
            return
        if tag == "table":
            if not self._inside_table:
                raise TableAdapterError("pred_html 的table结束标签状态非法")
            if self._current_row is not None or self._current_cell_text is not None:
                raise TableAdapterError("pred_html 在table结束前存在未闭合结构")
            self._inside_table = False

    def validate_complete(self) -> None:
        """HTMLParser本身会容忍缺失结束标签，因此结束后显式检查完整性。"""

        if self.table_count != 1:
            raise TableAdapterError("pred_html 必须包含且只包含一个 table")
        if self._inside_table or self._current_row is not None:
            raise TableAdapterError("pred_html 存在未闭合的table或tr")
        if not self.rows or all(not row for row in self.rows):
            raise TableAdapterError("pred_html 无法确定有效行列")


@dataclass(frozen=True, slots=True)
class _PlacedCell:
    """保存HTML cell计算后的1-based左上锚点。"""

    row_index: int
    column_index: int
    raw_text: str
    rowspan: int
    colspan: int


def adapt_ppstructure_table(
    table_result: dict[str, Any],
    *,
    table_bbox: list[float] | tuple[float, ...],
    table_id: str,
    document_id: str,
    source_category: str,
    relative_path: str,
    page_no: int,
    table_index: int,
) -> Table:
    """把单个PP-StructureV3表格dict转换为内部Table。

    Args:
        table_result: 包含pred_html和cell_box_list的普通dict。
        table_bbox: 已由调用方确认配对的table block ``[x0,y0,x1,y1]``。
        table_id/document_id/source_category/relative_path/page_no/table_index:
            上游显式提供的来源字段；Adapter不从文件名或标准文字猜测。

    Returns:
        保留raw HTML、真实cell、坐标和风险信号的冻结Table。

    Raises:
        TableAdapterError: 必需字段、HTML结构、span占位、bbox或数量无法安全映射。
    """

    if not isinstance(table_result, dict):
        raise TableAdapterError("table_result 必须是普通dict")
    pred_html = table_result.get("pred_html")
    if not isinstance(pred_html, str) or not pred_html:
        raise TableAdapterError("缺少非空 pred_html")
    cell_box_list = table_result.get("cell_box_list")
    if not isinstance(cell_box_list, list):
        raise TableAdapterError("缺少 cell_box_list")

    parsed_rows = _parse_html(pred_html)
    placed_cells, row_count, column_count = _place_cells(parsed_rows)
    if len(cell_box_list) != len(placed_cells):
        raise TableAdapterError(
            "cell_box_list 数量必须与HTML真实cell数量一致："
            f"{len(cell_box_list)} != {len(placed_cells)}"
        )

    try:
        table_box = _to_bbox(table_bbox, "table_bbox")
        cells = tuple(
            _build_cell(placed, cell_box_list[index], index + 1)
            for index, placed in enumerate(placed_cells)
        )
        return Table(
            table_id=table_id,
            document_id=document_id,
            source_category=source_category,
            relative_path=relative_path,
            page_no=page_no,
            table_index=table_index,
            bbox=table_box,
            row_count=row_count,
            column_count=column_count,
            cells=cells,
            raw_html=pred_html,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, TableAdapterError):
            raise
        raise TableAdapterError(f"PP-Structure表格字段非法：{exc}") from exc


def classify_cell_content_type(text: str) -> CellContentType:
    """用最小确定性规则区分empty/text/numeric/mixed，不执行NLP。

    数字加常见比较符号、百分号或单位视为numeric；标准号等字母数字混合内容视为
    mixed。任何中文与数字共存也视为mixed。规则只服务风险路由，不代表法规语义。
    """

    if text == "":
        return CellContentType.EMPTY
    has_digit = any(character.isdigit() for character in text) or bool(
        _CIRCLED_NUMERIC_PATTERN.search(text)
    )
    has_cjk = bool(re.search(r"[\u3400-\u9fff]", text))
    if has_digit and has_cjk:
        return CellContentType.MIXED
    if has_digit:
        compact = re.sub(r"\s+", "", text)
        if re.fullmatch(
            r"[+\-−]?([<>≤≥]=?)?\d+(\.\d+)?([~～\-−]\d+(\.\d+)?)?"
            r"(%|％|mm|cm|m|MPa|kPa|Pa|℃|°C)?",
            compact,
            flags=re.IGNORECASE,
        ) or all(character.isdigit() or character.isspace() for character in text):
            return CellContentType.NUMERIC
        return CellContentType.MIXED
    return CellContentType.TEXT


def build_risk_flags(text: str, content_type: CellContentType) -> tuple[CellRiskFlag, ...]:
    """为数字和圈号生成复核信号，不宣称该cell已知错误。"""

    flags: list[CellRiskFlag] = []
    contains_circled_numeric = bool(_CIRCLED_NUMERIC_PATTERN.search(text))
    contains_numeric = (
        any(character.isdigit() for character in text) or contains_circled_numeric
    )
    contains_special = contains_circled_numeric or "?" in text or "？" in text
    if content_type is CellContentType.NUMERIC or contains_numeric:
        flags.append(CellRiskFlag.NUMERIC_CONTENT)
    if contains_special:
        flags.append(CellRiskFlag.SPECIAL_SYMBOL)
    if flags:
        flags.append(CellRiskFlag.MANUAL_REVIEW_REQUIRED)
    return tuple(flags)


# 明确枚举Unicode圈号数字范围，避免依赖不同字符的isdigit实现差异。
# 范围覆盖⓪、①～⑳、㉑～㉟、㊱～㊿，不做字符到数值的转换。
_CIRCLED_NUMERIC_PATTERN = re.compile(
    r"[\u2460-\u2473\u24ea\u3251-\u325f\u32b1-\u32bf]"
)


def _parse_html(pred_html: str) -> list[list[_HtmlCell]]:
    """解析单个完整table；标准库会执行HTML entity到Unicode的最小解码。"""

    parser = _TableHTMLParser()
    try:
        parser.feed(pred_html)
        parser.close()
        parser.validate_complete()
    except TableAdapterError:
        raise
    except Exception as exc:
        raise TableAdapterError(f"pred_html 无法解析：{exc}") from exc
    return parser.rows


def _place_cells(rows: list[list[_HtmlCell]]) -> tuple[list[_PlacedCell], int, int]:
    """按rowspan/colspan占位计算1-based锚点，不创建被span覆盖的假cell。"""

    row_count = len(rows)
    occupied: set[tuple[int, int]] = set()
    placed: list[_PlacedCell] = []
    max_column = 0
    for row_index, row in enumerate(rows, start=1):
        column_index = 1
        for cell in row:
            while (row_index, column_index) in occupied:
                column_index += 1
            if row_index + cell.rowspan - 1 > row_count:
                raise TableAdapterError("rowspan 越过HTML总行数")
            covered = {
                (covered_row, covered_column)
                for covered_row in range(row_index, row_index + cell.rowspan)
                for covered_column in range(column_index, column_index + cell.colspan)
            }
            if occupied.intersection(covered):
                raise TableAdapterError("rowspan/colspan 导致cell覆盖冲突")
            occupied.update(covered)
            placed.append(
                _PlacedCell(
                    row_index,
                    column_index,
                    cell.raw_text,
                    cell.rowspan,
                    cell.colspan,
                )
            )
            max_column = max(max_column, column_index + cell.colspan - 1)
            column_index += cell.colspan
    if not placed or max_column < 1:
        raise TableAdapterError("无法从pred_html确定Table行列")
    return placed, row_count, max_column


def _build_cell(placed: _PlacedCell, box: object, box_index: int) -> TableCell:
    """组合HTML结构和同序cell bbox；confidence因无法聚合而保持None。"""

    content_type = classify_cell_content_type(placed.raw_text)
    return TableCell(
        row_index=placed.row_index,
        column_index=placed.column_index,
        bbox=_to_bbox(box, f"cell_box_list[{box_index}]"),
        raw_text=placed.raw_text,
        content_type=content_type,
        rowspan=placed.rowspan,
        colspan=placed.colspan,
        verified_text=None,
        review_status=ReviewStatus.UNREVIEWED,
        risk_flags=build_risk_flags(placed.raw_text, content_type),
        ocr_confidence=None,
    )


def _to_bbox(value: object, field_name: str) -> BoundingBox:
    """把已确认的四元素[x0,y0,x1,y1]转换为BoundingBox。"""

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise TableAdapterError(f"{field_name} 必须是四元素 [x0,y0,x1,y1]")
    try:
        return BoundingBox(value[0], value[1], value[2], value[3])
    except (TypeError, ValueError) as exc:
        raise TableAdapterError(f"{field_name} 非法：{exc}") from exc


def _parse_span(value: str | None, field_name: str) -> int:
    """解析HTML span属性；缺省为1，零、负数和非整数均拒绝。"""

    if value is None:
        return 1
    try:
        span = int(value)
    except (TypeError, ValueError) as exc:
        raise TableAdapterError(f"{field_name} 必须是正整数") from exc
    if span < 1:
        raise TableAdapterError(f"{field_name} 必须大于等于1")
    return span
