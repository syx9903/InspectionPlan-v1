# TASK-002.7：实现 Page 级 Text/OCR 路由器

## 任务目标

在单次打开 PDF 的前提下，逐页判断文本层是否达到 baseline，并分别产生 Text
或 OCR Page，使 mixed PDF 能按原始页序输出统一 JSONL。

## Page 路由设计与阈值

路由器使用 TASK-002.2 的透明规则：中文、英文和数字有效字符数达到20时直接保留
PyMuPDF 文本层，否则对当前页执行 OCR。20字符只选择解析方式，不过滤页面内容，
也不表示文本质量、语义或排版可靠。

## 单次 PDF 遍历

`PdfPageRouter` 自己打开 PDF 一次，并递增遍历选定 page range。它不依次调用
`TextPdfParser.parse()` 和 `OcrPdfParser.parse()`，因此不会重复打开文档或重复
处理同一页。达到阈值的页面直接构造 Text Page；其余页面仅调用 OCR 单页能力。

## OCR Lazy Init

构造路由器时不创建 OCR。首次遇到 OCR 页时调用一次 Parser 工厂，后续页面复用。
真实验证确认纯文本文件为0次，mixed 和扫描文件均为1次。

## Page 输出与统计

未修改 Page Schema。文本层页面为 `parse_method=text`；OCR 非空、空结果和异常
分别为 `success`、`empty`、`failed`，单页 OCR 失败后继续。文档级统计独立保存在
`last_run_stats`，不进入 Page。

## Page Range

`start_page`、`end_page` 使用 1-based、包含端点的规则，并校验类型、顺序和文档
边界。范围输出保留原始 `page_no`，不从1重新编号。

## 新增与修改文件

新增：

- `src/inspection_plan/document_parser/pdf_page_router.py`
- `scripts/parse_pdf_auto.py`
- `tests/test_pdf_page_router.py`
- `docs/pdf_page_router.md`
- `docs/task_logs/TASK-002.7.md`

修改：

- `src/inspection_plan/document_parser/__init__.py`：导出路由器与默认字符阈值。

## 自动测试

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：82个测试通过、0个失败；本任务新增18个测试。覆盖文本、空白、短噪声、
阈值、mixed、页序、PDF单次打开、lazy init、纯文本零初始化、OCR异常继续、
JSONL、page range、非法范围、文档异常与统计。

## 三类真实 PDF 验证

### text PDF

```text
文件：data/检验规范/4.TSG_R0005-2011_移动式压力容器安全技术监察规程 第1号修改单.pdf
范围：1～4
text_pages：4
ocr_pages：0
failed_pages：0
OCR初始化次数：0
总耗时：0.154秒
```

### no_usable_text PDF

```text
文件：data/检验规范/34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf
范围：1～7
text_pages：0
ocr_pages：7
failed_pages：0
OCR初始化次数：1
总耗时：26.906秒
```

### mixed PDF

```text
文件：data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf
范围：121～122
text_pages：1
ocr_pages：1
failed_pages：0
OCR初始化次数：1
总耗时：3.470秒

page 121 → text
page 122 → ocr
```

TASK-002.2 中第121页有效字符51个，第122页17个，实际路由与20字符规则一致。
性能只做记录；未进行优化，OCR inference 仍是主要耗时来源。

## 人工复核

1. 阅读 `docs/pdf_page_router.md`，核对阈值、单次打开和 lazy init 设计。
2. 打开三个 `data_processed/pages/*_auto.jsonl` 运行产物，核对页数和方法。
3. 对 mixed 产物确认页码为121、122，而不是1、2。
4. 对照原 PDF 第121～122页，确认一页使用文本、一页执行 OCR。
5. 查看 `models.py` 的 Git diff，应为空，证明 Page Schema 未修改。
6. 运行 pytest，确认 mock OCR 测试不执行真实大量 OCR。

## 已知限制

- 乱码文本层或长水印可能达到阈值并进入 Text。
- 20字符不是最终最优规则。
- OCR 可能产生错字、漏字或错误阅读顺序。
- 不处理页眉页脚、水印、表格、双栏和图示结构。

## 未实现内容

未实现 OCR/LLM 纠错、文本清洗、版面恢复、Clause、法规语义、标准号识别、全库
批处理、BM25、Embedding、RAG、FastAPI、数据库、DOCX、Page Schema 修改或
TASK-002.8。
