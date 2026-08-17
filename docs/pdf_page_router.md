# PDF Page 级 Text/OCR 路由器

## 为什么按页路由

真实资料包含 `mixed` PDF，同一文件中有些页面具备可用文本层，另一些页面只有
短噪声或没有文本层。整份文档固定使用 Text 会遗漏扫描页；整份文档固定 OCR
则会增加耗时，并可能用 OCR 错字替换本来可直接保留的文本。因此路由粒度必须是
Page。

## 路由规则

第一版沿用 TASK-002.2 baseline：统计页面文本中的中文、英文和数字字符。

```text
有效字符数 >= 20 → text
有效字符数 < 20  → OCR
```

20 只是解析方式选择阈值，不是正文过滤规则。短文本页不会被删除，而是交给 OCR；
文本页内容也不会因为路由判断而被清洗或截断。

## 数据流

```text
打开 PDF 一次
       ↓
按原始页码遍历 Page
       ↓
提取一次文本层并统计有效字符
       ├─ 达到阈值 → 原始文本 → text Page
       └─ 未达阈值 → 当前页渲染 → RapidOCR → ocr Page
       ↓
按原页序输出统一 Page JSONL
```

路由器不调用两个 Parser 的整文档 `parse()`，避免同一 PDF 被打开两次。它复用
`TextPdfParser` 的文本提取规则和 `OcrPdfParser` 的单页处理能力，不建立复杂基类。

## OCR Lazy Initialization

路由器构造时不创建 RapidOCR。第一次遇到未达到阈值的页面时才创建一个
`OcrPdfParser`，后续 OCR 页复用同一实例：

```text
纯文本 PDF → OCR 初始化 0 次
mixed PDF  → OCR 初始化 1 次
扫描 PDF   → OCR 初始化 1 次
```

## Page Range

`start_page` 与 `end_page` 对外均使用 1-based 页码并包含端点。输出 Page 保留原始
PDF 页码，例如解析 121～122 页仍输出 `page_no=121` 和 `page_no=122`。

## JSONL 与统计

同一个 JSONL 可以同时出现 `parse_method=text` 和 `parse_method=ocr`。字段仍完全
来自统一 Page Schema。文档级统计独立保存在 `PdfPageRouter.last_run_stats`：

- `total_pages`
- `text_pages`
- `ocr_pages`
- `success_pages`
- `empty_pages`
- `failed_pages`
- `ocr_initializations`
- `total_seconds`

统计字段不写入 Page。

## 命令行

```powershell
.\.venv\Scripts\python.exe scripts/parse_pdf_auto.py `
  "data\球罐标准\example.pdf" `
  --source-category "球罐标准" `
  --document-id "example"
```

小范围验证可增加 `--start-page` 和 `--end-page`。默认输出为
`data_processed/pages/<document_id>.jsonl`，重复运行会覆盖同名产物。

## 已知限制

- 文本层可能乱码但有效字符数很多，仍会被路由到 Text。
- 页眉、页脚或水印可能达到20字符阈值，导致页面被路由到 Text。
- 20字符是可解释的第一版 baseline，不是最终最优规则。
- OCR 仍可能产生错字、漏字及错误阅读顺序。
- 路由器不清洗文本，不恢复表格、双栏或图示结构。
