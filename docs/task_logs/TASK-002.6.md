# TASK-002.6：实现单个扫描型 PDF → OCR Page → JSONL

## 任务目标

实现正式 OcrPdfParser，将一份调用方明确选择 OCR 路径的扫描型 PDF 按页渲染、通过 RapidOCR 识别、转换成统一 Page，并按页序写出 UTF-8 JSONL。单页异常不得中止后续页面。

本任务不自动判断 Text/OCR 路径，也不批量处理全部扫描页面。

## 当前 OCR baseline

沿用 TASK-002.5 的决定：

```text
OCR 引擎：rapidocr-onnxruntime 1.4.4
DPI：200
颜色空间：RGB
alpha：false
图片传递：内存 PNG bytes
```

构造时允许简单覆盖 DPI，但不提供引擎、GPU、语言或自动路由配置。

## Parser API

OcrPdfParser 与 TextPdfParser 使用一致 API：

```python
pages = parser.parse(
    pdf_path,
    document_id="stable_id",
    source_category="检验规范",
    relative_path="data/检验规范/example.pdf",
)
```

两者都返回按文件页序排列的 `list[Page]`，页码从 1 开始，并提供 `parse_to_jsonl()` 与 `write_jsonl()`。

复用统一 Page、状态枚举和 TextPdfParser 已定义的 `PdfOpenError`。没有为了复用建立复杂基类，也没有让生产源码依赖实验脚本。

## OCR 初始化

`OcrPdfParser.__init__()` 创建一次 RapidOCR，并保存为实例字段。同一个 Parser 处理整份 PDF 时所有页面复用该引擎，不会在页面循环中重复加载模型。

测试可注入 RapidOCR 兼容 mock，既验证初始化次数，也避免把真实模型的细微输出差异变成单元测试失败。

## 页面渲染

每页执行：

```text
zoom = dpi / 72
page.get_pixmap(Matrix(zoom, zoom), RGB, alpha=false)
Pixmap → PNG bytes → RapidOCR
```

图片只在内存中传递，不保存到 Page，也不进入 JSONL。

## OCR 文本拼接

RapidOCR 每行返回 `[box, text, confidence]`。当前只提取 text，保持引擎返回顺序并以换行拼接。bbox 和 confidence 属于 OCR 中间信息，不修改 Page Schema；如果未来质量评估需要，应设计独立 OCR trace。

不进行 bbox 重排、双栏恢复、表格二维恢复、页眉页脚删除或 OCR 纠错。

## Page 映射

- OCR 拼接正文非空：`parse_method=ocr`、`text_status=success`、`error=null`。
- OCR 正常返回 `None`、空列表或空文本：`parse_method=ocr`、`text_status=empty`、正文为空。
- 单页渲染、OCR 或结果适配异常：`parse_method=ocr`、`text_status=failed`、正文为空并保存简短异常摘要；继续后续页面。
- 整份 PDF 不存在或无法打开：抛文档级 `FileNotFoundError` 或 `PdfOpenError`，不伪造 failed Page。

## JSONL

每行使用 Page 的 `to_json()`，UTF-8、`ensure_ascii=False`，顺序与 PDF 页序一致。默认 CLI 输出：

```text
data_processed/pages/<document_id>.jsonl
```

## 新增/修改文件

新增：

- `src/inspection_plan/document_parser/ocr_pdf_parser.py`
- `scripts/parse_ocr_pdf.py`
- `tests/test_ocr_pdf_parser.py`
- `docs/ocr_pdf_parser.md`
- `docs/task_logs/TASK-002.6.md`
- `data_processed/pages/NBT_47018_1_2017_ocr.jsonl`（真实验证产物，受 `.gitignore` 忽略）

修改：

- `src/inspection_plan/document_parser/__init__.py`：公开 `OcrPdfParser` 和 `DEFAULT_OCR_DPI`，同步更新包说明。

Page Schema、TextPdfParser 和 TASK-002.5 实验脚本均未修改。

## 测试

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果为 `64 passed`：原有 49 个案例，本任务新增收集 15 个。覆盖 success、多页页序、`parse_method=ocr`、拼接、empty、failed 后继续、JSONL、UTF-8、默认/非法 DPI、文档级缺失错误、OCR 单次初始化及运行统计。

自动测试动态创建极小 PDF 并使用 mock OCR，不依赖真实法规逐字结果。

## 真实 PDF 验证

选择 TASK-002.2 中最短的有效 `no_usable_text` PDF：

```text
文件：34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf
总页数：7
success：7
empty：0
failed：0
总耗时：71.992 秒
平均耗时：10.285 秒/页
输出：data_processed/pages/NBT_47018_1_2017_ocr.jsonl
```

运行命令：

```powershell
.\.venv\Scripts\python.exe scripts\parse_ocr_pdf.py `
  "data\检验规范\34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf" `
  --source-category "检验规范" `
  --document-id "NBT_47018_1_2017_ocr"
```

JSONL 验证：

- 共 7 行；
- `page_no` 依次为 1～7；
- 全部 `parse_method=ocr`；
- 全部 `char_count == len(text)`；
- 全部状态为 success。

## 性能

OcrPdfParser 的 `last_run_stats` 只保存最近一次：

```text
total_pages
total_seconds
average_seconds_per_page
```

真实样本平均 10.285 秒/页，高于 TASK-002.5 的小样本平均值，说明完整文档不同页面的文字密度和模型运行状态会显著影响耗时。该指标不进入 Page Schema。

## 人工复核

抽查第 1、4、7 页：

- 第 1 页：标准号、标题和发布日期等主要内容可读。
- 第 4 页：范围、引用文件及 `3.1～3.5` 条款顺序基本可读；标准号连接符存在“一/—”混淆，水印可能干扰正文。
- 第 7 页：`70%`、`7.2.3`、`7.3`、`8`、`JB/T 3223` 等关键内容可读。
- 页码、页眉和水印不会自动删除。

人工可打开原 PDF 与 `data_processed/pages/NBT_47018_1_2017_ocr.jsonl` 对照同一 `page_no`。如果页码不连续、JSONL 行数不等于 7、短条款丢失、失败页导致后续页缺失或出现非 `ocr` parse_method，说明实现存在问题。

## OCR 已知问题

- 中文低频字和姓名可能错识别。
- 数字、小数点、百分号需要重点人工核对。
- 条款编号可能漏点、合并或拆分。
- 标准号连接符中的破折号、短横线和“一”容易混淆。
- 页眉、页脚、页码、印章和水印会进入正文。
- 双栏、表格和图示标签的二维关系不能可靠恢复。
- 不根据 confidence 自动过滤、纠错或重试。

## 未实现内容

- Page 级 Text/OCR 自动路由和 mixed PDF fallback。
- 批量 OCR 全部 3772 个不可用文本页。
- OCR bbox/confidence trace、自动纠错或 LLM 修复。
- 表格、双栏、图示、页眉页脚和 Clause Parser。
- BM25、Embedding、RAG、FastAPI、数据库、DOCX。
- TASK-002.7 及后续功能。
