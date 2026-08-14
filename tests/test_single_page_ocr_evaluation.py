"""验证 OCR 单页实验的渲染、参数、结果转换和文本拼接。"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from scripts.evaluate_single_page_ocr import (
    evaluate_page,
    join_ocr_text,
    normalize_ocr_result,
    render_pdf_page,
    validate_dpi,
)


def _create_one_page_pdf(path: Path) -> None:
    """创建只含一页简单矢量文本的临时 PDF。"""

    with pymupdf.open() as document:
        page = document.new_page(width=300, height=400)
        page.insert_text((40, 60), "Render fixture")
        document.save(path)


def test_page_renders_to_non_empty_png(tmp_path: Path) -> None:
    """合法页面应渲染为具有尺寸和 PNG 签名的非空图片。"""

    pdf_path = tmp_path / "render.pdf"
    _create_one_page_pdf(pdf_path)

    rendered = render_pdf_page(pdf_path, page_no=1, dpi=150)

    assert rendered.width > 0
    assert rendered.height > 0
    assert rendered.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert rendered.render_ms >= 0


@pytest.mark.parametrize("page_no", [0, -1, 2])
def test_invalid_page_number_is_rejected(tmp_path: Path, page_no: int) -> None:
    """零、负数和超出文档范围的 1-based 页码必须拒绝。"""

    pdf_path = tmp_path / "one-page.pdf"
    _create_one_page_pdf(pdf_path)

    with pytest.raises(ValueError, match="page_no"):
        render_pdf_page(pdf_path, page_no=page_no, dpi=150)


@pytest.mark.parametrize("dpi", [0, 71, 601, 1000])
def test_invalid_dpi_is_rejected(dpi: int) -> None:
    """异常低或高的 DPI 不应进入渲染阶段。"""

    with pytest.raises(ValueError, match="DPI"):
        validate_dpi(dpi)


def test_ocr_result_becomes_json_serializable_structure() -> None:
    """RapidOCR 三元组应转换为含 box、text、confidence 的基础结构。"""

    raw_result = [
        [[[0, 0], [10, 0], [10, 5], [0, 5]], "第一行", 0.98],
        [[[0, 10], [10, 10], [10, 15], [0, 15]], "第二行", 0.91],
    ]

    normalized = normalize_ocr_result(raw_result)

    assert normalized[0]["text"] == "第一行"
    assert normalized[0]["confidence"] == pytest.approx(0.98)
    json.dumps(normalized, ensure_ascii=False)


def test_join_ocr_text_preserves_return_order() -> None:
    """baseline 拼接必须保持 OCR 返回顺序并用换行分隔。"""

    lines = [
        {"text": "第一行"},
        {"text": "第二行"},
        {"text": "第三行"},
    ]

    assert join_ocr_text(lines) == "第一行\n第二行\n第三行"


def test_empty_ocr_result_is_supported() -> None:
    """没有检测到文字时应得到空列表和空正文，而不是异常。"""

    assert normalize_ocr_result(None) == []
    assert join_ocr_text([]) == ""


def test_evaluate_page_uses_mock_engine_and_records_metrics(tmp_path: Path) -> None:
    """完整实验函数应接受 mock 引擎并生成可序列化的性能与 OCR 记录。"""

    pdf_path = tmp_path / "mock.pdf"
    _create_one_page_pdf(pdf_path)

    class MockOcrEngine:
        """返回固定 RapidOCR 兼容结构，避免测试依赖模型推理。"""

        def __call__(self, image: bytes) -> tuple[list[list[object]], list[float]]:
            """确认收到 PNG 后返回一条固定中文识别结果。"""

            assert image.startswith(b"\x89PNG")
            return [
                [[[0, 0], [10, 0], [10, 5], [0, 5]], "模拟正文", 0.99]
            ], [0.01, 0.0, 0.02]

    result, rendered = evaluate_page(
        pdf_path,
        page_no=1,
        dpi=200,
        sample_id="mock_sample",
        relative_path="tests/mock.pdf",
        ocr_engine=MockOcrEngine(),
    )

    assert rendered.width > 0
    assert result["text"] == "模拟正文"
    assert result["recognized_lines"] == 1
    assert result["engine_elapsed_seconds"] == [0.01, 0.0, 0.02]
    json.dumps(result, ensure_ascii=False)
