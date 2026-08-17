"""定义 Table、Clause 与跨页物理表格之间的独立证据关联模型。

本模块只保存已经由规则、人工或未来算法给出的绑定结果，不执行条款解析、
表号匹配、空间邻近计算或续表识别。Table 与 Page 继续描述原始物理对象；
Clause 仅以外部稳定 ``clause_id`` 被引用，从而避免提前约束未来 Clause Schema。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar


class TableClauseRelation(StrEnum):
    """描述表格与条款之间最小且明确的语义关系。"""

    BELONGS_TO = "belongs_to"
    REFERENCED_BY = "referenced_by"


class TableContinuationRelation(StrEnum):
    """描述两个物理 Table 片段之间的跨页续接关系。"""

    CONTINUATION = "continuation"


class BindingMethod(StrEnum):
    """标明关联结论的产生方式，防止启发式结果伪装成确定事实。"""

    DETERMINISTIC = "deterministic"
    HEURISTIC = "heuristic"
    MANUAL = "manual"


class LinkReviewStatus(StrEnum):
    """表示关联关系从待复核到确认或人工修正的状态。"""

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    CORRECTED = "corrected"


class EvidenceType(StrEnum):
    """枚举关联层当前需要保存的最小可解释证据类型。"""

    SAME_DOCUMENT = "same_document"
    SAME_PAGE = "same_page"
    CAPTION_MATCH = "caption_match"
    EXPLICIT_REFERENCE = "explicit_reference"
    SPATIAL_PROXIMITY = "spatial_proximity"
    NEAREST_PRECEDING_CLAUSE = "nearest_preceding_clause"
    SAME_TABLE_NUMBER = "same_table_number"
    CONTINUATION_MARKER = "continuation_marker"
    ADJACENT_PAGE = "adjacent_page"


@dataclass(frozen=True, slots=True)
class TableClauseLink:
    """保存一个 Table 与一个外部 Clause ID 之间的可审计语义绑定。

    多条独立记录自然表达多对多关系。``evidence_texts`` 仅保存支持结论的
    短文本证据，不承载 Clause 正文；修正关系时应创建新记录并通过
    ``supersedes_link_id`` 指向旧记录，避免原绑定无痕消失。
    """

    link_id: str
    table_id: str
    clause_id: str
    relation_type: TableClauseRelation | str
    binding_method: BindingMethod | str
    evidence_types: tuple[EvidenceType | str, ...]
    review_status: LinkReviewStatus | str = LinkReviewStatus.UNREVIEWED
    evidence_texts: tuple[str, ...] = ()
    notes: str | None = None
    supersedes_link_id: str | None = None

    def __post_init__(self) -> None:
        """规范枚举和序列，并校验标识、证据以及人工修正状态。"""

        _validate_non_empty_string("link_id", self.link_id)
        _validate_non_empty_string("table_id", self.table_id)
        _validate_non_empty_string("clause_id", self.clause_id)
        object.__setattr__(
            self,
            "relation_type",
            _coerce_enum(TableClauseRelation, self.relation_type, "relation_type"),
        )
        _normalize_common_fields(self)

    def to_dict(self) -> dict[str, Any]:
        """返回保留中文证据且可直接写入 JSON 的稳定字典。"""

        return _link_to_dict(self, {"table_id": self.table_id, "clause_id": self.clause_id})

    def to_json(self) -> str:
        """以不转义中文的方式序列化关联记录。"""

        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class TableContinuationLink:
    """保存前后两个物理 Table 片段之间的可审计续表关系。

    续表是 Table 到 Table 的物理/逻辑连续性，不表示任一片段属于某个 Clause，
    因此与 ``TableClauseLink`` 分开保存。本模型只表达结果，不检测续表。
    """

    link_id: str
    from_table_id: str
    to_table_id: str
    binding_method: BindingMethod | str
    evidence_types: tuple[EvidenceType | str, ...]
    relation_type: TableContinuationRelation | str = TableContinuationRelation.CONTINUATION
    review_status: LinkReviewStatus | str = LinkReviewStatus.UNREVIEWED
    evidence_texts: tuple[str, ...] = ()
    notes: str | None = None
    supersedes_link_id: str | None = None

    def __post_init__(self) -> None:
        """校验续表端点不同，并规范共同的证据与复核字段。"""

        _validate_non_empty_string("link_id", self.link_id)
        _validate_non_empty_string("from_table_id", self.from_table_id)
        _validate_non_empty_string("to_table_id", self.to_table_id)
        if self.from_table_id == self.to_table_id:
            raise ValueError("from_table_id 与 to_table_id 不能相同")
        object.__setattr__(
            self,
            "relation_type",
            _coerce_enum(
                TableContinuationRelation, self.relation_type, "relation_type"
            ),
        )
        _normalize_common_fields(self)

    def to_dict(self) -> dict[str, Any]:
        """返回包含续表方向和全部审核信息的 JSON 兼容字典。"""

        return _link_to_dict(
            self,
            {
                "from_table_id": self.from_table_id,
                "to_table_id": self.to_table_id,
            },
        )

    def to_json(self) -> str:
        """以不转义中文的方式序列化续表关联。"""

        return json.dumps(self.to_dict(), ensure_ascii=False)


EnumType = TypeVar("EnumType", bound=StrEnum)


def _normalize_common_fields(link: TableClauseLink | TableContinuationLink) -> None:
    """统一校验两类关联共享的绑定、证据、复核与修正追踪约束。"""

    binding_method = _coerce_enum(BindingMethod, link.binding_method, "binding_method")
    review_status = _coerce_enum(LinkReviewStatus, link.review_status, "review_status")
    evidence_types = _coerce_evidence_types(link.evidence_types)
    evidence_texts = _coerce_evidence_texts(link.evidence_texts)
    _validate_optional_text("notes", link.notes)
    _validate_optional_text("supersedes_link_id", link.supersedes_link_id)

    object.__setattr__(link, "binding_method", binding_method)
    object.__setattr__(link, "review_status", review_status)
    object.__setattr__(link, "evidence_types", evidence_types)
    object.__setattr__(link, "evidence_texts", evidence_texts)

    if link.supersedes_link_id == link.link_id:
        raise ValueError("supersedes_link_id 不能指向当前 link_id")
    if review_status is LinkReviewStatus.CORRECTED:
        if binding_method is not BindingMethod.MANUAL:
            raise ValueError("corrected 关联必须使用 manual binding_method")
        if link.supersedes_link_id is None or link.notes is None:
            raise ValueError("corrected 关联必须记录 supersedes_link_id 和 notes")
    elif link.supersedes_link_id is not None:
        raise ValueError("只有 corrected 关联可以设置 supersedes_link_id")


def _link_to_dict(
    link: TableClauseLink | TableContinuationLink, endpoints: dict[str, str]
) -> dict[str, Any]:
    """按统一顺序组合关联端点、判定依据和人工审核字段。"""

    return {
        "link_id": link.link_id,
        **endpoints,
        "relation_type": link.relation_type.value,
        "binding_method": link.binding_method.value,
        "evidence_types": [item.value for item in link.evidence_types],
        "review_status": link.review_status.value,
        "evidence_texts": list(link.evidence_texts),
        "notes": link.notes,
        "supersedes_link_id": link.supersedes_link_id,
    }


def _coerce_enum(
    enum_type: type[EnumType], value: object, field_name: str
) -> EnumType:
    """把合法字符串转换为指定枚举，并为非法值列出允许范围。"""

    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} 只允许：{allowed}") from exc


def _coerce_evidence_types(
    values: tuple[EvidenceType | str, ...],
) -> tuple[EvidenceType, ...]:
    """规范证据枚举并拒绝空集合或重复项，保证每条绑定可解释。"""

    if not isinstance(values, (tuple, list)):
        raise TypeError("evidence_types 必须是 tuple 或 list")
    normalized = tuple(_coerce_enum(EvidenceType, value, "evidence_types") for value in values)
    if not normalized:
        raise ValueError("evidence_types 至少包含一项")
    if len(set(normalized)) != len(normalized):
        raise ValueError("evidence_types 不能包含重复项")
    return normalized


def _coerce_evidence_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    """规范短文本证据并拒绝空白或重复文本。"""

    if not isinstance(values, (tuple, list)):
        raise TypeError("evidence_texts 必须是 tuple 或 list")
    normalized = tuple(values)
    for value in normalized:
        _validate_non_empty_string("evidence_texts item", value)
    if len(set(normalized)) != len(normalized):
        raise ValueError("evidence_texts 不能包含重复项")
    return normalized


def _validate_non_empty_string(field_name: str, value: object) -> None:
    """校验关联标识或文本证据为非空白字符串。"""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} 必须是字符串")
    if not value.strip():
        raise ValueError(f"{field_name} 不能为空")


def _validate_optional_text(field_name: str, value: object) -> None:
    """校验可选审计文本在出现时不为空白。"""

    if value is None:
        return
    _validate_non_empty_string(field_name, value)
