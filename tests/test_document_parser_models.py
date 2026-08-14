"""验证统一 Page 模型的字段约束、状态一致性和序列化。"""

from __future__ import annotations

import json

import pytest

from src.inspection_plan.document_parser import Page, ParseMethod, TextStatus


def _valid_page_data() -> dict[str, object]:
    """返回可按测试场景覆盖字段的最小合法文本页数据。"""

    return {
        "document_id": "GB12337_2014",
        "source_category": "球罐标准",
        "relative_path": "data/球罐标准/GB 12337-2014.pdf",
        "file_name": "GB 12337-2014.pdf",
        "page_no": 12,
        "text": "这是测试页面正文。",
        "parse_method": "text",
        "text_status": "success",
    }


def test_normal_text_page_creation() -> None:
    """合法文本层页面应完成枚举规范化和自动字符统计。"""

    page = Page(**_valid_page_data())

    assert page.parse_method is ParseMethod.TEXT
    assert page.text_status is TextStatus.SUCCESS
    assert page.char_count == len(page.text)
    assert page.ocr_used is False


def test_ocr_page_creation() -> None:
    """OCR 页面只由 parse_method 表达来源，派生属性不得产生矛盾。"""

    data = _valid_page_data()
    data["parse_method"] = "ocr"

    page = Page(**data)

    assert page.parse_method is ParseMethod.OCR
    assert page.ocr_used is True


def test_page_number_less_than_one_is_rejected() -> None:
    """业务页码采用 1-based 规则，零和负数必须拒绝。"""

    data = _valid_page_data()
    data["page_no"] = 0

    with pytest.raises(ValueError, match="1-based"):
        Page(**data)


def test_char_count_is_computed_from_text_including_whitespace() -> None:
    """char_count 应自动包含空白字符，调用者不能传入不一致值。"""

    data = _valid_page_data()
    data["text"] = "abc \n"

    page = Page(**data)

    assert page.char_count == 5
    with pytest.raises(TypeError):
        Page(**data, char_count=500)


def test_empty_page_is_valid() -> None:
    """正常空白页应与解析失败页区分，并保持 error 为 None。"""

    data = _valid_page_data()
    data.update(text="", text_status="empty")

    page = Page(**data)

    assert page.text_status is TextStatus.EMPTY
    assert page.char_count == 0
    assert page.error is None


def test_failed_page_keeps_error_summary() -> None:
    """失败页必须能保存简短异常摘要且不向下游暴露部分正文。"""

    data = _valid_page_data()
    data.update(text="", text_status="failed", error="页面文本提取失败")

    page = Page(**data)

    assert page.text_status is TextStatus.FAILED
    assert page.error == "页面文本提取失败"
    assert page.char_count == 0


def test_dict_and_json_serialization_are_complete() -> None:
    """Page 转换为 dict 和 JSON 后应保留全部约定字段及基础类型。"""

    page = Page(**_valid_page_data())

    payload = page.to_dict()
    assert payload == {
        "document_id": "GB12337_2014",
        "source_category": "球罐标准",
        "relative_path": "data/球罐标准/GB 12337-2014.pdf",
        "file_name": "GB 12337-2014.pdf",
        "page_no": 12,
        "text": "这是测试页面正文。",
        "parse_method": "text",
        "text_status": "success",
        "char_count": len("这是测试页面正文。"),
        "error": None,
    }
    assert json.loads(page.to_json()) == payload


def test_invalid_parse_method_is_rejected() -> None:
    """模型不能接受未定义的文本来源。"""

    data = _valid_page_data()
    data["parse_method"] = "unknown"

    with pytest.raises(ValueError, match="parse_method"):
        Page(**data)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"text": "", "text_status": "success"}, "success"),
        ({"text": "仍有正文", "text_status": "empty"}, "empty"),
        ({"text": "", "text_status": "failed", "error": None}, "failed"),
        ({"text_status": "success", "error": "不应存在"}, "error"),
    ],
)
def test_contradictory_text_states_are_rejected(
    changes: dict[str, object],
    message: str,
) -> None:
    """正文、状态和异常摘要之间的明显矛盾组合必须拒绝。"""

    data = _valid_page_data()
    data.update(changes)

    with pytest.raises(ValueError, match=message):
        Page(**data)


@pytest.mark.parametrize(
    "relative_path",
    [
        "G:/standards/test.pdf",
        "G:\\standards\\test.pdf",
        "/data/standards/test.pdf",
        "data/../test.pdf",
    ],
)
def test_absolute_or_unsafe_relative_path_is_rejected(relative_path: str) -> None:
    """Page 不能携带绑定本机或越出项目根目录的来源路径。"""

    data = _valid_page_data()
    data["relative_path"] = relative_path
    data["file_name"] = "test.pdf"

    with pytest.raises(ValueError, match="relative_path"):
        Page(**data)
