"""验证文本质量候选特征的确定性计算，不断言质量标签。"""

from __future__ import annotations

from src.inspection_plan.document_parser.text_quality import (
    extract_text_quality_features,
)


def test_chinese_english_and_digit_counts() -> None:
    features = extract_text_quality_features("中文Ab12")
    assert features.chinese_count == 2
    assert features.latin_count == 2
    assert features.digit_count == 2
    assert features.effective_char_count == 6


def test_empty_text_has_zero_features() -> None:
    features = extract_text_quality_features("")
    assert all(value == 0 for value in features.to_dict().values())


def test_replacement_character_is_suspicious() -> None:
    features = extract_text_quality_features("正文�")
    assert features.suspicious_char_count == 1
    assert features.suspicious_char_ratio > 0


def test_extended_latin_is_suspicious() -> None:
    features = extract_text_quality_features("îïð")
    assert features.latin_count == 3
    assert features.suspicious_char_count == 3
    assert features.readable_char_count == 0


def test_common_chinese_punctuation_is_readable() -> None:
    text = "中文，。；：！？（）《》、—…"
    features = extract_text_quality_features(text)
    assert features.suspicious_char_count == 0
    assert features.readable_char_count == features.non_whitespace_count


def test_line_metrics_and_repeated_ratio() -> None:
    features = extract_text_quality_features("第一行\n\n第二行\n第一行")
    assert features.line_count == 4
    assert features.non_empty_line_count == 3
    assert features.average_line_length == 3
    assert features.max_line_length == 3
    assert features.repeated_line_ratio == 0.333333


def test_all_ratios_stay_between_zero_and_one() -> None:
    features = extract_text_quality_features("中文ABC123î\ufffd\n")
    ratios = [
        value
        for name, value in features.to_dict().items()
        if name.endswith("_ratio")
    ]
    assert all(0.0 <= ratio <= 1.0 for ratio in ratios)


def test_feature_extraction_does_not_modify_text() -> None:
    text = "原始\nText 123"
    original = text
    extract_text_quality_features(text)
    assert text == original
