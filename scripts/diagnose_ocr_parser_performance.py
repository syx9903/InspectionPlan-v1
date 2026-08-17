"""诊断 TASK-002.6 OCR Parser 的逐阶段耗时，不改变生产解析逻辑。

脚本针对一份明确指定的 PDF 初始化一次 RapidOCR，随后逐页执行与
``OcrPdfParser`` 相同的 200 DPI、RGB、无 alpha、内存 PNG bytes 链路。
计时仅用于区分初始化、Pixmap 渲染、PNG 编码、OCR 推理和 JSONL 写出成本；
它不修改 Page Schema、不调整 OCR 参数，也不把计时字段写入 Page。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from inspection_plan.document_parser import OcrPdfParser  # noqa: E402
from inspection_plan.document_parser.models import (  # noqa: E402
    Page,
    ParseMethod,
    TextStatus,
)


DEFAULT_PDF = PROJECT_ROOT / (
    "data/检验规范/34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 "
    "第1部分：采购通则.pdf"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data_processed/diagnostics/task_002_6a_pages.jsonl"
)
DEFAULT_DOCUMENT_ID = "NBT_47018_1_2017_ocr_diagnostic"
DEFAULT_SOURCE_CATEGORY = "检验规范"
DEFAULT_DPI = 200


def parse_args() -> argparse.Namespace:
    """读取诊断 PDF、JSONL 输出路径和 DPI 参数。"""

    argument_parser = argparse.ArgumentParser(
        description="诊断单个扫描 PDF 的 OCR Parser 逐阶段耗时"
    )
    argument_parser.add_argument("pdf", nargs="?", type=Path, default=DEFAULT_PDF)
    argument_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    argument_parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    return argument_parser.parse_args()


def _elapsed_ms(started_at: float) -> float:
    """把从 ``perf_counter`` 起点开始的耗时转换为毫秒。"""

    return (perf_counter() - started_at) * 1000


def _make_page(
    *,
    page_no: int,
    file_name: str,
    relative_path: str,
    raw_result: Any,
) -> Page:
    """使用生产 Parser 的文本拼接规则构造诊断 JSONL 所需 Page。"""

    text = OcrPdfParser._join_ocr_lines(raw_result)
    has_text = bool(text.strip())
    return Page(
        document_id=DEFAULT_DOCUMENT_ID,
        source_category=DEFAULT_SOURCE_CATEGORY,
        relative_path=relative_path,
        file_name=file_name,
        page_no=page_no,
        text=text if has_text else "",
        parse_method=ParseMethod.OCR,
        text_status=TextStatus.SUCCESS if has_text else TextStatus.EMPTY,
    )


def run_diagnostic(pdf_path: Path, output_path: Path, dpi: int) -> None:
    """运行一次七页 OCR 诊断并按要求打印各阶段耗时。

    RapidOCR 构造次数由当前函数中的唯一构造语句显式计数。页面循环只复用
    已创建的 ``ocr_engine``。异常会直接结束诊断，以免把不完整计时误当成
    可比较的性能数据；这不改变生产 Parser 的逐页异常隔离策略。
    """

    from rapidocr_onnxruntime import RapidOCR

    resolved_pdf = pdf_path if pdf_path.is_absolute() else PROJECT_ROOT / pdf_path
    resolved_output = (
        output_path if output_path.is_absolute() else PROJECT_ROOT / output_path
    )
    relative_path = resolved_pdf.resolve().relative_to(PROJECT_ROOT).as_posix()
    OcrPdfParser._validate_dpi(dpi)

    overall_started_at = perf_counter()
    init_started_at = perf_counter()
    rapidocr_calls = 0
    ocr_engine = RapidOCR()
    rapidocr_calls += 1
    ocr_init_ms = _elapsed_ms(init_started_at)

    pages: list[Page] = []
    page_timings: list[dict[str, float]] = []
    zoom = dpi / 72.0
    with pymupdf.open(resolved_pdf) as document:
        for page_index in range(len(document)):
            page_started_at = perf_counter()

            render_started_at = perf_counter()
            pixmap = document[page_index].get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom),
                colorspace=pymupdf.csRGB,
                alpha=False,
            )
            render_ms = _elapsed_ms(render_started_at)

            encode_started_at = perf_counter()
            png_bytes = pixmap.tobytes("png")
            encode_ms = _elapsed_ms(encode_started_at)

            ocr_started_at = perf_counter()
            raw_result, _engine_elapsed = ocr_engine(png_bytes)
            ocr_ms = _elapsed_ms(ocr_started_at)

            pages.append(
                _make_page(
                    page_no=page_index + 1,
                    file_name=resolved_pdf.name,
                    relative_path=relative_path,
                    raw_result=raw_result,
                )
            )
            page_timings.append(
                {
                    "render_ms": render_ms,
                    "encode_ms": encode_ms,
                    "ocr_ms": ocr_ms,
                    "total_ms": _elapsed_ms(page_started_at),
                }
            )

    write_started_at = perf_counter()
    OcrPdfParser.write_jsonl(pages, resolved_output)
    jsonl_write_ms = _elapsed_ms(write_started_at)
    total_ms = _elapsed_ms(overall_started_at)

    print(f"ocr_init_ms = {ocr_init_ms:.3f}")
    print(f"RapidOCR() 实际调用次数 = {rapidocr_calls}")
    for page_no, timing in enumerate(page_timings, start=1):
        print(f"\npage {page_no}:")
        for field_name in ("render_ms", "encode_ms", "ocr_ms", "total_ms"):
            print(f"{field_name} = {timing[field_name]:.3f}")
    print(f"\njsonl_write_ms = {jsonl_write_ms:.3f}")
    print(f"total_ms = {total_ms:.3f}")
    # 项目根目录含不可见 Unicode 字符时，Windows GBK 控制台可能无法打印绝对路径。
    # 输出项目相对路径既可复核产物，也避免诊断完成后因终端编码而误报失败。
    printable_output = resolved_output.resolve().relative_to(PROJECT_ROOT).as_posix()
    print(f"output = {printable_output}")


def main() -> int:
    """执行命令行诊断。"""

    args = parse_args()
    run_diagnostic(args.pdf, args.output, args.dpi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
