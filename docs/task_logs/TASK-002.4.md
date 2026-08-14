# TASK-002.4：实现文本型 PDF → Page JSONL 的最小解析链路

## 任务目标

实现一个最小、可测试的文本型 PDF Parser，将单个具备文本层的 PDF 通过 PyMuPDF 按页转换成统一 Page，并支持写出 UTF-8 Page JSONL。本任务不执行 OCR，也不批量解析全部资料。

## 设计思路

`TextPdfParser` 位于 PyMuPDF 与 Page 模型之间，只承担技术格式转换：

```text
文本型 PDF
→ PyMuPDF 默认文本提取
→ Page
→ JSONL
```

Parser 不猜测业务元数据。`document_id`、`source_category` 和 `relative_path` 均由调用方显式传入，从而避免把标准号识别和目录规则隐藏在底层解析器中。

## 输入输出

输入：

- 一个 PDF 的本机路径；
- 调用方提供的稳定 `document_id`；
- 调用方提供的 `source_category`；
- 项目相对 `relative_path`。

输出：

- 按 PDF 页序排列的 `list[Page]`；
- 可选的一页一行 UTF-8 Page JSONL。

默认 CLI 输出到 `data_processed/pages/<document_id>.jsonl`，重复执行覆盖同名文件。

## 新增/修改文件

新增：

- `src/inspection_plan/document_parser/text_pdf_parser.py`
- `scripts/parse_text_pdf.py`
- `tests/test_text_pdf_parser.py`
- `docs/text_pdf_parser.md`
- `docs/task_logs/TASK-002.4.md`
- `data_processed/pages/TSG_R0005_2011_amendment_1.jsonl`（真实验证运行产物，受 `.gitignore` 忽略）

修改：

- `src/inspection_plan/document_parser/__init__.py`：公开 `TextPdfParser` 和 `PdfOpenError`，同步更新包职责说明。

没有修改 TASK-002.1/002.2 的盘点逻辑或 Page 模型字段。

## 解析流程

```text
检查输入文件
→ PyMuPDF 打开 PDF
→ 按 0-based 内部索引遍历
→ get_text("text")
→ 转换为 1-based Page.page_no
→ 映射 success / empty / failed
→ 继续下一页
→ 按页序写 JSONL
```

正式 Parser 不使用 TASK-002.2 的 20 字符阈值。任何 `strip()` 后非空的文本都完整保留，包括很短的标题或附录标记。

## 异常处理

- 文件不存在或不是普通文件：抛出明确 `FileNotFoundError`。
- 文件扩展名不是 PDF：抛出 `ValueError`。
- PDF 存在但无法打开或遍历：抛出 `PdfOpenError`，不伪造页面。
- 单页提取失败：生成 `text_status=failed` 的 Page，保存异常类型与简短消息，并继续后续页面。
- 提取成功但只有空白：生成正文为 `""` 的 `empty` Page，不视为失败。

## 测试

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果为 `37 passed`：原有 28 个测试案例，TASK-002.4 新增 9 个。覆盖单页、多页顺序、1-based 页码、success、empty、字符数、JSONL 行数/反序列化、UTF-8 中文、不存在输入和单页失败后继续。

测试 PDF 均由代码在 pytest 临时目录动态创建，没有复制真实法规文件。

## 真实 PDF 验证

只解析一份 TASK-002.2 已分类为 `text`、页数较少的真实 PDF：

```text
文件名：4.TSG_R0005-2011_移动式压力容器安全技术监察规程 第1号修改单.pdf
总页数：4
success：4
empty：0
failed：0
输出：data_processed/pages/TSG_R0005_2011_amendment_1.jsonl
```

运行命令：

```powershell
.\.venv\Scripts\python.exe scripts\parse_text_pdf.py `
  "data\检验规范\4.TSG_R0005-2011_移动式压力容器安全技术监察规程 第1号修改单.pdf" `
  --source-category "检验规范" `
  --document-id "TSG_R0005_2011_amendment_1"
```

核对结果：

- JSONL 共 4 行，页码依次为 1、2、3、4；
- 4 行状态均为 `success`；
- 每行 `char_count == len(text)`；
- 第 1、2、4 页重新从 PDF 提取的字符串与对应 JSONL `text` 逐字一致；
- 三页字符数分别为 1017、1178、615；只查看了极短预览，没有在文档中复制法规正文。

## TASK-002.2 与 TASK-002.4 的区别

- TASK-002.2：通过字符阈值检测文本层是否可能可用，为后续路由提供依据，不保存正文。
- TASK-002.4：正式提取 Page 正文，不使用 20 字符阈值过滤或修改内容。

## 人工复核方法

1. 打开 `src/inspection_plan/document_parser/text_pdf_parser.py`，确认只调用 `get_text("text")`，不渲染页面、不 OCR。
2. 打开 `data_processed/pages/TSG_R0005_2011_amendment_1.jsonl`，确认 4 行、页码连续且每行可单独解析为 JSON。
3. 使用 PDF 阅读器打开真实样本，分别核对第 1、2、4 页与 JSONL 中同页 `text`。
4. 确认 PDF 阅读器的第一页对应 `page_no=1`，而不是 PyMuPDF 内部索引 0。
5. 运行 pytest，确认动态 PDF、空白页和单页异常测试通过。
6. 如果短文本被丢弃、页码错位、单页异常中止整个 PDF、JSONL 行数与页数不一致或出现 OCR 调用，说明 Parser 存在问题。

## 未实现内容

- OCR、页面图像渲染和 OCR 输出评估。
- mixed PDF 自动补 OCR 或批量解析全部 86 份 PDF。
- 文本清洗、页眉页脚、表格和 Clause Parser。
- 标准号识别、法规语义分析和 Document Metadata。
- DOCX、BM25、Embedding、RAG、LLM、FastAPI 和数据库。
- TASK-002.5 及后续功能。
