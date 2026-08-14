# Text PDF Parser

## 职责

`TextPdfParser` 将一个具备文本层的 PDF 按页转换成统一 `Page`，并可将结果写成一页一行的 Page JSONL。它只负责打开文件、顺序遍历页面、提取默认文本和映射状态。

它不负责 OCR、页面路由、文本清洗、页眉页脚过滤、表格解析、Clause 切分、标准号识别或语义分析。

## 输入

- 本机 PDF 文件路径；
- 调用方提供的 `document_id`；
- 调用方提供的 `source_category`；
- 相对于项目根目录的 `relative_path`。

Parser 不从目录或文件名猜测业务元数据，也不识别 GB、TSG 等标准号。

## 输出

```text
文本型 PDF
→ PyMuPDF 默认文本提取
→ list[Page]
→ Page JSONL
```

`parse()` 返回按 PDF 页序排列的 Page 列表；`parse_to_jsonl()` 在返回列表的同时覆盖写入指定 JSONL；`write_jsonl()` 也可以单独序列化已有 Page。

## 与 Page 模型的关系

Parser 负责把 PyMuPDF 的提取结果转换成 Page 字段；Page 模型继续负责路径、页码、状态、错误和字符数的一致性校验。Parser 不在 JSONL 中写入 PyMuPDF 对象。

## 页码映射

PyMuPDF 内部页面索引从 0 开始；`Page.page_no` 从 1 开始。Parser 使用：

```text
Page.page_no = page_index + 1
```

因此 JSONL 第一行对应 PDF 文件第一页，不代表页面正文印刷页码一定为 1。

## 状态规则

- `success`：`get_text("text")` 成功，并且结果 `strip()` 后非空。原始提取字符串完整保留，不应用长度阈值。
- `empty`：提取成功，但结果 `strip()` 后为空。为满足统一模型约束，Page 正文写成空字符串。
- `failed`：当前页调用文本提取时发生异常。Page 正文为空，`error` 保存异常类型和简短消息，并继续后续页面。

## JSONL 格式

输出使用 UTF-8 和 `ensure_ascii=False`，每行是一个完整 Page JSON，顺序与 PDF 页序一致。例如：

```json
{"document_id":"example","source_category":"检验规范","relative_path":"data/检验规范/example.pdf","file_name":"example.pdf","page_no":1,"text":"页面正文。","parse_method":"text","text_status":"success","char_count":5,"error":null}
```

重复写入同一路径会覆盖旧文件。默认 CLI 输出目录是被 Git 忽略的 `data_processed/pages/`。

## 错误处理

- 输入路径不存在或不是普通文件：抛出 `FileNotFoundError`。
- 输入不是 `.pdf`：抛出 `ValueError`。
- 文件存在但 PyMuPDF 无法打开或遍历：抛出 `PdfOpenError`，不生成伪造页面。
- 单页提取异常：生成 `failed` Page，继续处理后续页面。

文档级失败与页面级失败分开处理，因为前者无法确定完整页序，后者仍可保留其他页面结果。

## 为什么不使用 OCR

TASK-002.4 只验证文本型 PDF 的最小正式解析链路。OCR 需要页面渲染、引擎选择、图像参数、置信度和质量评估，属于 TASK-002.5。当前 Parser 不导入或调用任何 OCR 引擎。

## 与 TASK-002.2 的区别

TASK-002.2 是检测和路由依据：通过 20 个有效字符的 baseline 判断页面文本层是否可能可用，不保存正文。

TASK-002.4 是正式正文提取：任何非空白文本都原样保留，即使只有“附录A”等少量字符，也不会因低于 20 字符而丢弃。

```text
TASK-002.2：文本层检测 → 路由辅助
TASK-002.4：文本层解析 → Page 正文
```

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\parse_text_pdf.py `
  "data/检验规范/example.pdf" `
  --source-category "检验规范" `
  --document-id "example"
```

可选参数：

- `--relative-path`：输入位于项目外时必须显式提供；
- `--output`：指定 JSONL 路径，否则写入 `data_processed/pages/<document_id>.jsonl`。
