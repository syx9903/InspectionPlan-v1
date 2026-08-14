# OcrPdfParser

## 数据流

```text
明确选择 OCR 的扫描 PDF
→ PyMuPDF 页面渲染
→ RapidOCR
→ OCR 行
→ 按返回顺序拼接文本
→ Page
→ UTF-8 JSONL
```

OcrPdfParser 只处理调用方已经明确选择 OCR 路径的单个 PDF，不判断页面是否需要 OCR，也不自动回退 TextPdfParser。

## baseline

```text
默认 DPI = 200
颜色空间 = RGB
alpha = false
图片传递 = 内存 PNG bytes
```

`DEFAULT_OCR_DPI` 定义在 `ocr_pdf_parser.py`，构造时可以用 `OcrPdfParser(dpi=300)` 做简单覆盖。DPI 必须是 72～600 的整数。200 DPI 来自 TASK-002.5 的 3 页、9 次小样本实验，是当前 baseline，不是最终最优参数。

## OCR 初始化

默认构造 `OcrPdfParser()` 时创建一次 RapidOCR，并存入 Parser 实例。同一 Parser 解析一份 PDF 的全部页面时复用该引擎，不会每页重新初始化模型。

测试可以注入 RapidOCR 兼容 mock：

```python
parser = OcrPdfParser(ocr_engine=mock_engine)
```

## Parser API

OcrPdfParser 与 TextPdfParser 使用相同输入：

```python
pages = parser.parse(
    pdf_path,
    document_id="stable_id",
    source_category="检验规范",
    relative_path="data/检验规范/example.pdf",
)
```

两者都返回按 PDF 顺序排列的 `list[Page]`，页码从 1 开始，并提供 `parse_to_jsonl()` 和 `write_jsonl()`。

调用方负责提供 `document_id`、`source_category` 和 `relative_path`。Parser 不识别标准号，也不猜测业务目录。

## Page 状态

### success

RapidOCR 正常返回并拼接出非空白正文：

```text
parse_method = ocr
text_status = success
text = OCR 行按返回顺序换行拼接
error = null
```

### empty

RapidOCR 正常运行，但返回 `None`、空列表或只有空文本：

```text
parse_method = ocr
text_status = empty
text = ""
error = null
```

这可能表示空白页、纯图形页或没有可识别文字，不等于异常。

### failed

单页渲染、OCR 或结果结构适配发生异常：

```text
parse_method = ocr
text_status = failed
text = ""
error = 异常类型和简短消息
```

单页失败不会终止后续页面。整个 PDF 不存在或无法打开则使用文档级 `FileNotFoundError`/`PdfOpenError`，不伪造 Page。

## 与 TextPdfParser 的共同点

- 相同 `parse()` 输入元数据；
- 相同 `list[Page]` 输出；
- 相同 1-based 页码；
- 相同 success、empty、failed 语义；
- 相同文档级/页面级异常边界；
- 相同 UTF-8 Page JSONL 格式与页序。

## 与 TextPdfParser 的不同点

```text
TextPdfParser：page.get_text("text")
OcrPdfParser：page.get_pixmap(...) → RapidOCR
```

TextPdfParser 的 `parse_method=text`；OcrPdfParser 的 `parse_method=ocr`。OcrPdfParser 成本更高，且识别结果存在不确定性。

## OCR 行与 Page.text

RapidOCR 每行包含 bbox、text 和 confidence。当前只按引擎返回顺序提取 text 并以换行拼接，不重新按 bbox 排序。

Page 只保存最终正文。bbox 和 confidence 属于 OCR 中间 trace，本任务不修改 Page Schema；如果后续质量评估确实需要，应单独设计 OCR trace，而不是强行塞入 Page。

## JSONL

每行一个 Page，使用 UTF-8 和 `ensure_ascii=False`，顺序与 PDF 页序一致。默认 CLI 输出：

```text
data_processed/pages/<document_id>.jsonl
```

## 性能统计

`last_run_stats` 保存最近一次解析的：

- `total_pages`；
- `total_seconds`；
- `average_seconds_per_page`。

这些是运行指标，不进入 Page Schema，也不表示 OCR 质量。

## 已知局限

- 中文低频字可能误识别；
- 数字、小数点和百分号需要人工重点核对；
- 条款编号可能漏点、合并或拆分；
- 标准号中的破折号、短横线和汉字“一”容易混淆；
- 页眉、页脚、页码、印章和水印会进入正文；
- 双栏顺序、表格二维关系和图示标签关系不能可靠恢复；
- 不根据 confidence 自动过滤、纠错或重试；
- 不判断 PDF 或页面是否应该走 OCR。

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\parse_ocr_pdf.py `
  "data/检验规范/example.pdf" `
  --source-category "检验规范" `
  --document-id "example"
```

可用 `--dpi` 覆盖默认 200，并可用 `--output` 指定 JSONL 路径。不提供引擎、GPU、语言或自动路由参数。
