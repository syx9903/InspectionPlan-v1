"""把单个文本型 PDF 忠实转换为统一 Page 列表和 Page JSONL。

Parser 使用 PyMuPDF 按文件顺序读取每一页的默认文本字符串。非空白文本映射为
``success``，空白文本映射为 ``empty``，单页提取异常映射为 ``failed`` 并继续。
整个 PDF 无法打开时则抛出文档级异常。模块不执行 OCR、页面渲染、文本清洗、
页眉页脚过滤、表格解析或 Clause 切分。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pymupdf

from .models import Page, ParseMethod, TextStatus


class PdfOpenError(RuntimeError):
    """表示 PDF 文件存在，但 PyMuPDF 无法打开或遍历其文档容器。"""


class TextPdfParser:
    """将一个具备文本层的 PDF 按页转换为 Page。

    调用方必须显式提供 ``document_id``、``source_category`` 和项目相对路径，
    Parser 不猜测业务分类或从文件名识别标准号。Page 文本保持 PyMuPDF 的原始
    提取结果；唯一规范化是把纯空白结果转换为空字符串，以符合 EMPTY 状态约束。
    """

    def parse(
        self,
        pdf_path: Path,
        *,
        document_id: str,
        source_category: str,
        relative_path: str,
    ) -> list[Page]:
        """解析单个 PDF 并按原始页序返回 Page 列表。

        Args:
            pdf_path: 本机上待解析 PDF 的实际路径。
            document_id: 调用方确定的稳定文档标识，不在此处识别法规编号。
            source_category: 调用方明确指定的资料来源类别。
            relative_path: 相对于项目根目录、用于 Page 追溯的正斜杠路径。

        Returns:
            顺序与 PDF 一致、页码从 1 开始的 Page 列表。

        Raises:
            FileNotFoundError: 输入路径不存在或不是普通文件。
            ValueError: 输入不是 PDF 文件。
            PdfOpenError: 文件存在但文档容器无法打开或遍历。
        """

        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF 文件不存在或不是普通文件：{path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"TextPdfParser 只接受 PDF 文件：{path.name}")

        pages: list[Page] = []
        try:
            with pymupdf.open(path) as document:
                for page_index in range(len(document)):
                    pages.append(
                        self._parse_page(
                            document[page_index],
                            page_no=page_index + 1,
                            document_id=document_id,
                            source_category=source_category,
                            relative_path=relative_path,
                            file_name=path.name,
                        )
                    )
        except (FileNotFoundError, ValueError):
            raise
        except Exception as exc:  # noqa: BLE001 - 转换为明确的文档级打开异常。
            raise PdfOpenError(
                f"无法打开或遍历 PDF {path.name}：{type(exc).__name__}: {exc}"
            ) from exc

        return pages

    def _parse_page(
        self,
        pdf_page: Any,
        *,
        page_no: int,
        document_id: str,
        source_category: str,
        relative_path: str,
        file_name: str,
    ) -> Page:
        """提取单页文本，并把成功、空白或异常统一映射为 Page。"""

        try:
            text = self._extract_text(pdf_page)
        except Exception as exc:  # noqa: BLE001 - 单页失败必须记录后继续后续页面。
            return Page(
                document_id=document_id,
                source_category=source_category,
                relative_path=relative_path,
                file_name=file_name,
                page_no=page_no,
                text="",
                parse_method=ParseMethod.TEXT,
                text_status=TextStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )

        if text.strip():
            text_status = TextStatus.SUCCESS
            page_text = text
        else:
            text_status = TextStatus.EMPTY
            page_text = ""

        return Page(
            document_id=document_id,
            source_category=source_category,
            relative_path=relative_path,
            file_name=file_name,
            page_no=page_no,
            text=page_text,
            parse_method=ParseMethod.TEXT,
            text_status=text_status,
        )

    @staticmethod
    def _extract_text(pdf_page: Any) -> str:
        """调用 PyMuPDF 默认文本提取，不读取坐标块、图片或版面对象。"""

        return pdf_page.get_text("text")

    @staticmethod
    def write_jsonl(pages: Iterable[Page], output_path: Path) -> int:
        """按输入顺序写出 UTF-8 Page JSONL，并返回写入行数。

        输出文件会被覆盖，父目录会自动创建。每个 Page 使用自身稳定序列化，
        因而中文保持原样且一行只包含一个完整 JSON 对象。
        """

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        page_count = 0
        with path.open("w", encoding="utf-8", newline="\n") as output_file:
            for page in pages:
                output_file.write(page.to_json())
                output_file.write("\n")
                page_count += 1
        return page_count

    def parse_to_jsonl(
        self,
        pdf_path: Path,
        output_path: Path,
        *,
        document_id: str,
        source_category: str,
        relative_path: str,
    ) -> list[Page]:
        """解析单个 PDF、写出对应 JSONL，并返回生成的 Page 列表。"""

        pages = self.parse(
            pdf_path,
            document_id=document_id,
            source_category=source_category,
            relative_path=relative_path,
        )
        self.write_jsonl(pages, output_path)
        return pages
