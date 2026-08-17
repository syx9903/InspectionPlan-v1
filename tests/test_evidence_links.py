"""验证独立证据关联模型的边界、序列化与人工修正规则。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.inspection_plan.document_parser.evidence_links import (
    BindingMethod,
    EvidenceType,
    LinkReviewStatus,
    TableClauseLink,
    TableClauseRelation,
    TableContinuationLink,
)


def _table_clause_link(**overrides: object) -> TableClauseLink:
    """构造可按字段覆盖的显式引用关联基线。"""

    values: dict[str, object] = {
        "link_id": "link_001",
        "table_id": "doc_p35_t01",
        "clause_id": "doc_7.3.1",
        "relation_type": "referenced_by",
        "binding_method": "deterministic",
        "evidence_types": (
            "same_document",
            "explicit_reference",
            "caption_match",
        ),
        "evidence_texts": ("检测比例按表7-2执行",),
    }
    values.update(overrides)
    return TableClauseLink(**values)  # type: ignore[arg-type]


def test_normal_table_clause_link_supports_string_enums() -> None:
    link = _table_clause_link()

    assert link.relation_type is TableClauseRelation.REFERENCED_BY
    assert link.binding_method is BindingMethod.DETERMINISTIC
    assert link.review_status is LinkReviewStatus.UNREVIEWED


def test_normal_table_continuation_link() -> None:
    link = TableContinuationLink(
        link_id="continuation_001",
        from_table_id="doc_p35_t01",
        to_table_id="doc_p36_t01",
        binding_method="heuristic",
        evidence_types=("same_table_number", "continuation_marker", "adjacent_page"),
    )

    assert link.relation_type.value == "continuation"
    assert link.from_table_id != link.to_table_id


@pytest.mark.parametrize("field_name", ["table_id", "clause_id"])
def test_empty_required_endpoint_is_rejected(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        _table_clause_link(**{field_name: " "})


def test_invalid_relation_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="relation_type"):
        _table_clause_link(relation_type="continues")


def test_invalid_binding_method_is_rejected() -> None:
    with pytest.raises(ValueError, match="binding_method"):
        _table_clause_link(binding_method="automatic")


def test_duplicate_evidence_types_are_rejected() -> None:
    with pytest.raises(ValueError, match="不能包含重复项"):
        _table_clause_link(evidence_types=("same_page", "same_page"))


def test_reviewed_status_is_preserved() -> None:
    link = _table_clause_link(review_status="reviewed")

    assert link.review_status is LinkReviewStatus.REVIEWED


def test_corrected_status_requires_traceable_manual_replacement() -> None:
    link = _table_clause_link(
        link_id="link_002",
        binding_method="manual",
        review_status="corrected",
        supersedes_link_id="link_001",
        notes="人工复核后改绑至7.3.2。",
    )

    assert link.supersedes_link_id == "link_001"


def test_json_serialization_keeps_chinese_evidence() -> None:
    link = _table_clause_link()

    serialized = link.to_json()
    assert "检测比例按表7-2执行" in serialized
    assert json.loads(serialized)["clause_id"] == "doc_7.3.1"


def test_same_continuation_endpoints_are_rejected() -> None:
    with pytest.raises(ValueError, match="不能相同"):
        TableContinuationLink(
            link_id="continuation_001",
            from_table_id="same_table",
            to_table_id="same_table",
            binding_method="manual",
            evidence_types=(EvidenceType.CONTINUATION_MARKER,),
        )


def test_module_has_no_ppstructure_or_clause_model_dependency() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "inspection_plan"
        / "document_parser"
        / "evidence_links.py"
    )
    source = source_path.read_text(encoding="utf-8")

    assert "paddle" not in source.lower()
    assert "ppstructure" not in source.lower()
    assert "from .clause" not in source.lower()
    assert "class Clause" not in source
