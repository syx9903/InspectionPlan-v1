"""提取简单、可解释的 PDF 文本层质量特征。

模块输入原始页面文本，输出长度、字符组成、可疑字符、可读字符、行结构与简单
重复特征。它不使用词典、模型或 OCR，也不判断文本是 good/bad，更不会决定
Text/OCR 路由。特征仅供 TASK-002.9.1 离线分析和后续 baseline 研究使用，且不
修改统一 Page Schema。
"""

from __future__ import annotations

import re
import string
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any


BASELINE_EFFECTIVE_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fffA-Za-z0-9]")
COMMON_CJK_PUNCTUATION = frozenset(
    "，。；：！？（）【】《》“”‘’、—…·～％＋－＝／＼＃＆＠＊℃"
)
ALLOWED_CONTROL_WHITESPACE = frozenset("\n\r\t")


@dataclass(frozen=True, slots=True)
class TextQualityFeatures:
    """保存一段文本的确定性描述特征，不包含质量结论。

    比例字段均限制在0～1。组成比例以中文、Latin 和十进制数字总数为分母；
    suspicious/readable 比例以非空白字符数为分母。空分母统一返回0。
    """

    char_count: int
    non_whitespace_count: int
    effective_char_count: int
    chinese_count: int
    latin_count: int
    digit_count: int
    chinese_ratio: float
    latin_ratio: float
    digit_ratio: float
    suspicious_char_count: int
    suspicious_char_ratio: float
    readable_char_count: int
    readable_char_ratio: float
    line_count: int
    non_empty_line_count: int
    average_line_length: float
    max_line_length: int
    repeated_line_ratio: float

    def to_dict(self) -> dict[str, Any]:
        """返回便于离线 JSON 分析的基础类型字典。"""

        return asdict(self)


def extract_text_quality_features(text: str) -> TextQualityFeatures:
    """从原始文本计算候选质量特征，不修改输入或给出质量标签。

    suspicious 的透明定义包括：Unicode replacement character、除换行/回车/制表
    外的控制或格式字符、私用/未分配字符、不可打印非空白字符，以及非 ASCII 的
    Latin 字母。最后一类用于捕捉中文法规乱码中常见的 ``î/ï/ð``，不是字符黑名单。

    readable 包括中文、ASCII 字母数字、Unicode 十进制数字、ASCII 标点和一组
    明确的常用中文/全角标点。该集合故意保持简单；合法但罕见的符号可能被计为
    不可读，而形似乱码的 CJK 字符仍可能被计为可读，这是已知限制。
    """

    if not isinstance(text, str):
        raise TypeError("text 必须是字符串")

    char_count = len(text)
    non_whitespace_count = sum(not character.isspace() for character in text)
    effective_char_count = len(BASELINE_EFFECTIVE_PATTERN.findall(text))
    chinese_count = sum(_is_chinese(character) for character in text)
    latin_count = sum(_is_latin_letter(character) for character in text)
    digit_count = sum(character.isdecimal() for character in text)
    composition_count = chinese_count + latin_count + digit_count

    suspicious_char_count = sum(_is_suspicious(character) for character in text)
    readable_char_count = sum(_is_readable(character) for character in text)

    lines = text.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    line_lengths = [sum(not character.isspace() for character in line) for line in non_empty_lines]
    repeated_line_count = len(non_empty_lines) - len(set(line.strip() for line in non_empty_lines))

    return TextQualityFeatures(
        char_count=char_count,
        non_whitespace_count=non_whitespace_count,
        effective_char_count=effective_char_count,
        chinese_count=chinese_count,
        latin_count=latin_count,
        digit_count=digit_count,
        chinese_ratio=_safe_ratio(chinese_count, composition_count),
        latin_ratio=_safe_ratio(latin_count, composition_count),
        digit_ratio=_safe_ratio(digit_count, composition_count),
        suspicious_char_count=suspicious_char_count,
        suspicious_char_ratio=_safe_ratio(suspicious_char_count, non_whitespace_count),
        readable_char_count=readable_char_count,
        readable_char_ratio=_safe_ratio(readable_char_count, non_whitespace_count),
        line_count=len(lines),
        non_empty_line_count=len(non_empty_lines),
        average_line_length=(round(sum(line_lengths) / len(line_lengths), 6) if line_lengths else 0.0),
        max_line_length=max(line_lengths, default=0),
        repeated_line_ratio=_safe_ratio(repeated_line_count, len(non_empty_lines)),
    )


def _is_chinese(character: str) -> bool:
    """判断字符是否位于 CJK 扩展 A 或基本统一汉字区。"""

    return "\u3400" <= character <= "\u4dbf" or "\u4e00" <= character <= "\u9fff"


def _is_latin_letter(character: str) -> bool:
    """按 Unicode 名称识别 ASCII 及扩展 Latin 字母。"""

    return unicodedata.category(character).startswith("L") and "LATIN" in unicodedata.name(
        character, ""
    )


def _is_suspicious(character: str) -> bool:
    """按透明 Unicode 类别规则识别疑似乱码字符。"""

    if character == "\ufffd":
        return True
    if character in ALLOWED_CONTROL_WHITESPACE:
        return False
    category = unicodedata.category(character)
    if category in {"Cc", "Cf", "Co", "Cn"}:
        return True
    if not character.isspace() and not character.isprintable():
        return True
    return _is_latin_letter(character) and not character.isascii()


def _is_readable(character: str) -> bool:
    """判断非空白字符是否属于当前法规 baseline 的常用可读集合。"""

    if character.isspace() or _is_suspicious(character):
        return False
    return (
        _is_chinese(character)
        or (character.isascii() and character.isalnum())
        or character.isdecimal()
        or character in string.punctuation
        or character in COMMON_CJK_PUNCTUATION
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    """计算六位小数比例，空分母返回0。"""

    return round(numerator / denominator, 6) if denominator else 0.0
