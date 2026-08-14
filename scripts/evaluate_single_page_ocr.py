"""对少量真实 PDF 页面执行 RapidOCR 单页实验并保存可复核结果。

脚本使用 PyMuPDF 按指定 DPI 把 1-based PDF 页码渲染为内存 PNG，再交给
RapidOCR 1.4.4。每个 DPI 单独保存 JSON，包含图像尺寸、耗时、OCR 行结果、
置信度和按返回顺序换行拼接的 baseline 正文。可选保存实验 PNG，但不会修改
原始 PDF。脚本不批量处理整份资料，不创建 Page，也不执行文本纠错或结构恢复。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "data_processed" / "ocr_experiments"
DEFAULT_DPI_VALUES = (150, 200, 300)
MIN_DPI = 72
MAX_DPI = 600
SAFE_SAMPLE_ID_PATTERN = re.compile(r"^[^/\\]+$")


class OcrEngine(Protocol):
    """描述实验所需的最小 OCR 调用接口，便于使用 mock 做稳定测试。"""

    def __call__(self, image: bytes) -> tuple[Any, Any]:
        """接收图片字节并返回 OCR 结果及引擎阶段耗时。"""


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """保存一次页面渲染的内存图片、尺寸和耗时。

    PNG 字节只在当前进程中传给 OCR；除非 CLI 显式指定 ``--save-images``，
    不会写入磁盘。
    """

    png_bytes: bytes
    width: int
    height: int
    render_ms: float


def validate_dpi(dpi: int) -> int:
    """校验 DPI 是 72～600 的整数并返回原值。

    该范围覆盖本任务的 150/200/300 DPI 小实验，同时避免零值、负值或异常高
    分辨率造成无意义图片及过大内存消耗。
    """

    if isinstance(dpi, bool) or not isinstance(dpi, int):
        raise TypeError("DPI 必须是整数")
    if not MIN_DPI <= dpi <= MAX_DPI:
        raise ValueError(f"DPI 必须位于 {MIN_DPI}～{MAX_DPI} 之间")
    return dpi


def render_pdf_page(pdf_path: Path, page_no: int, dpi: int) -> RenderedPage:
    """把一个 1-based PDF 页面渲染为内存 RGB PNG。

    Args:
        pdf_path: 待实验 PDF 路径。
        page_no: 与 PDF 阅读器一致、从 1 开始的页面序号。
        dpi: 目标渲染分辨率，通过 ``dpi / 72`` 转换为 PyMuPDF zoom。

    Raises:
        FileNotFoundError: 输入不是现有普通文件。
        ValueError: 页码或 DPI 不合法。
    """

    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在或不是普通文件：{path}")
    validate_dpi(dpi)
    if isinstance(page_no, bool) or not isinstance(page_no, int) or page_no < 1:
        raise ValueError("page_no 必须是大于等于 1 的整数")

    started_at = perf_counter()
    with pymupdf.open(path) as document:
        if page_no > len(document):
            raise ValueError(f"page_no={page_no} 超出 PDF 总页数 {len(document)}")
        page = document[page_no - 1]
        zoom = dpi / 72.0
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(zoom, zoom),
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        png_bytes = pixmap.tobytes("png")
        width = pixmap.width
        height = pixmap.height
    render_ms = (perf_counter() - started_at) * 1000

    return RenderedPage(
        png_bytes=png_bytes,
        width=width,
        height=height,
        render_ms=render_ms,
    )


def normalize_ocr_result(raw_result: Any) -> list[dict[str, Any]]:
    """把 RapidOCR 行结果转换成稳定的 JSON 兼容结构。

    RapidOCR 1.4.4 的完整检测识别结果按行返回
    ``[bounding_box, text, confidence]``。本函数保留引擎顺序，不重排版面，
    并把 NumPy 标量或数组转换成普通 list/float。
    """

    if raw_result is None:
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_result):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            raise ValueError(f"OCR 第 {index + 1} 条结果不是 [box, text, confidence]")
        box, text, confidence = item[:3]
        if hasattr(box, "tolist"):
            box = box.tolist()
        normalized.append(
            {
                "box": box,
                "text": str(text),
                "confidence": float(confidence),
            }
        )
    return normalized


def join_ocr_text(lines: list[dict[str, Any]]) -> str:
    """按 OCR 原始返回顺序用换行拼接文本，不做阅读顺序恢复。"""

    return "\n".join(str(line["text"]) for line in lines)


def evaluate_page(
    pdf_path: Path,
    *,
    page_no: int,
    dpi: int,
    sample_id: str,
    relative_path: str,
    ocr_engine: OcrEngine,
) -> tuple[dict[str, Any], RenderedPage]:
    """完成一次单页渲染与 OCR，并返回可序列化记录及内存图片。

    ``ocr_ms`` 只计算引擎调用，不包括 RapidOCR 对象初始化；``total_ms`` 是
    本次渲染与 OCR 的耗时之和。性能数据用于建立量级感知，不作为严格基准。
    """

    rendered = render_pdf_page(pdf_path, page_no, dpi)
    ocr_started_at = perf_counter()
    raw_result, engine_elapsed = ocr_engine(rendered.png_bytes)
    ocr_ms = (perf_counter() - ocr_started_at) * 1000

    lines = normalize_ocr_result(raw_result)
    text = join_ocr_text(lines)
    result = {
        "sample_id": sample_id,
        "relative_path": relative_path,
        "page_no": page_no,
        "dpi": dpi,
        "image_width": rendered.width,
        "image_height": rendered.height,
        "render_ms": round(rendered.render_ms, 3),
        "ocr_ms": round(ocr_ms, 3),
        "total_ms": round(rendered.render_ms + ocr_ms, 3),
        "recognized_lines": len(lines),
        "recognized_characters": len(text),
        "engine_elapsed_seconds": _to_json_compatible(engine_elapsed),
        "raw_ocr": lines,
        "text": text,
    }
    return result, rendered


def _to_json_compatible(value: Any) -> Any:
    """递归转换 NumPy 等对象，保证实验元数据可以写入 JSON。"""

    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_compatible(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def create_ocr_engine() -> OcrEngine:
    """延迟创建项目已配置的 RapidOCR baseline 引擎。

    延迟导入避免纯渲染和 mock 单元测试加载 ONNX Runtime。当前受控执行环境
    可能限制原生 ONNX DLL，遇到导入错误时应报告环境问题，而不是静默切换引擎。
    """

    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def write_experiment_json(output_path: Path, result: dict[str, Any]) -> None:
    """以 UTF-8 写入单次 DPI 实验结果，中文保持原样。"""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    """解析单 PDF、单页、DPI 列表、样本标识和输出选项。"""

    parser = argparse.ArgumentParser(description="执行 RapidOCR 单页最小实验")
    parser.add_argument("pdf", type=Path, help="项目内待实验 PDF")
    parser.add_argument("--page-no", type=int, required=True, help="1-based PDF 页码")
    parser.add_argument(
        "--dpi",
        type=int,
        nargs="+",
        default=list(DEFAULT_DPI_VALUES),
        help="一个或多个 DPI；默认 150 200 300",
    )
    parser.add_argument("--sample-id", required=True, help="安全、简短的实验样本标识")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="实验 JSON 输出目录",
    )
    parser.add_argument(
        "--save-images",
        action="store_true",
        help="同时保存实验 PNG，默认只在内存中传递图片",
    )
    return parser.parse_args()


def main() -> int:
    """创建一次 OCR 引擎，对指定页面运行有限 DPI 实验并保存结果。"""

    args = parse_args()
    if not SAFE_SAMPLE_ID_PATTERN.fullmatch(args.sample_id) or args.sample_id in {".", ".."}:
        raise ValueError("sample_id 不能包含路径分隔符")
    for dpi in args.dpi:
        validate_dpi(dpi)

    pdf_path = args.pdf if args.pdf.is_absolute() else PROJECT_ROOT / args.pdf
    try:
        relative_path = pdf_path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("OCR 实验输入必须位于项目根目录内") from exc

    output_directory = (
        args.output_dir
        if args.output_dir.is_absolute()
        else PROJECT_ROOT / args.output_dir
    )
    ocr_engine = create_ocr_engine()

    for dpi in args.dpi:
        result, rendered = evaluate_page(
            pdf_path,
            page_no=args.page_no,
            dpi=dpi,
            sample_id=args.sample_id,
            relative_path=relative_path,
            ocr_engine=ocr_engine,
        )
        result_path = output_directory / f"{args.sample_id}_{dpi}dpi_raw_ocr.json"
        write_experiment_json(result_path, result)
        if args.save_images:
            image_path = output_directory / f"{args.sample_id}_{dpi}dpi.png"
            image_path.write_bytes(rendered.png_bytes)
        print(
            f"{args.sample_id}：{dpi} DPI，{rendered.width}x{rendered.height}，"
            f"OCR {result['ocr_ms']:.1f} ms，字符 {result['recognized_characters']}，"
            f"输出 {result_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
