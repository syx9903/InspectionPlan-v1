# TASK-002.3：建立统一 Page 数据模型

## 为什么建立 Page 模型

真实资料的文本层检测表明，后续页面文字既可能来自 PDF 文本层，也可能来自 OCR。如果两条解析路径输出不同结构，Clause Parser 将被迫了解底层技术细节。统一 Page 模型把解析方式封装为字段，使下游只依赖稳定的页面级数据契约。

## 数据流位置

```text
PDF 页面
   ↓
Text Parser / OCR Parser
   ↓
Page
   ↓
Clause Parser
```

本任务只实现 Page，不实现图中的任何 Parser。

## 采用的实现技术

使用 Python 标准库 `dataclass`，配置 `frozen=True, slots=True`，并通过 `__post_init__` 做字段与跨字段校验。

选择理由：

- 当前字段数量和规则较小，dataclass 足够表达；
- 模型不依赖 PDF、OCR 或第三方验证库；
- 冻结实例能避免创建后修改正文却未同步字符数；
- `slots` 限制任意动态属性，保持 Schema 边界明确；
- 项目虽然通过 `pydantic-settings` 间接安装了 Pydantic 2.13.4，但 `requirements.txt` 没有直接约束 Pydantic 版本，不值得仅为当前模型增加耦合。

## 字段设计

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `document_id` | `str` | 上游提供的稳定来源文档标识 |
| `source_category` | `str` | 来源目录类别 |
| `relative_path` | `str` | 相对于项目根目录的正斜杠路径 |
| `file_name` | `str` | 原始文件名 |
| `page_no` | `int` | 从 1 开始的 PDF 人工页序 |
| `text` | `str` | 提供给下游的最终页面正文 |
| `parse_method` | `text \| ocr` | 最终文字产生方式 |
| `text_status` | `success \| empty \| failed` | 页面文字解析状态 |
| `char_count` | `int` | 自动计算的 `len(text)`，包含空白 |
| `error` | `str \| null` | 失败时的简短异常摘要 |

没有保存独立 `ocr_used` 字段，因为它与 `parse_method=ocr` 完全重复。模型提供派生只读属性 `ocr_used` 方便判断，但序列化结果不重复保存该状态。

## 字段约束

- 必要字符串标识不能为空白。
- `relative_path` 拒绝 Windows/POSIX 绝对路径、反斜杠、`.` 和 `..`，末段必须匹配 `file_name`。
- `page_no` 必须是大于等于 1 的整数，布尔值不视为合法页码。
- `parse_method` 只允许 `text` 和 `ocr`，不增加当前无明确语义的 `unknown`。
- `text_status=success` 时正文必须包含非空白字符且 `error=null`。
- `text_status=empty` 时正文必须为 `""` 且 `error=null`。
- `text_status=failed` 时正文必须为 `""` 且必须提供非空异常摘要。
- `char_count` 由模型计算，不能由调用者输入，从源头避免与 `text` 不一致。

## 页码规则

`Page.page_no` 使用 1-based，表示人工在 PDF 文件中看到的第几页。它不是页面上印刷的页码。未来 PyMuPDF Parser 使用内部 0-based 索引时，必须在构造 Page 前转换。

## 序列化方式

`Page.to_dict()` 显式返回全部 Schema 字段并把枚举转换成字符串；`Page.to_json()` 使用 `ensure_ascii=False` 生成 JSON。结果只包含 JSON 可序列化基础类型，不包含 Enum、Path 或第三方对象。

文本页示例：

```json
{"document_id":"test_standard","source_category":"球罐标准","relative_path":"data/球罐标准/test.pdf","file_name":"test.pdf","page_no":12,"text":"测试法规正文。","parse_method":"text","text_status":"success","char_count":7,"error":null}
```

失败 OCR 页示例：

```json
{"document_id":"test_standard","source_category":"球罐标准","relative_path":"data/球罐标准/test.pdf","file_name":"test.pdf","page_no":13,"text":"","parse_method":"ocr","text_status":"failed","char_count":0,"error":"OCR 未能生成页面文本"}
```

## 新增/修改文件

新增：

- `src/inspection_plan/document_parser/__init__.py`
- `src/inspection_plan/document_parser/models.py`
- `tests/test_document_parser_models.py`
- `docs/page_model.md`
- `docs/task_logs/TASK-002.3.md`

未修改 TASK-002.1 或 TASK-002.2 的盘点逻辑和产物。

## 测试结果

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果为 `28 passed`。其中已有测试 12 个，Page 模型新增收集 16 个测试案例，覆盖正常文本页、OCR 页、1-based 页码、自动字符统计、空白页、失败页、dict/JSON 序列化、非法枚举、矛盾状态和不安全路径。

测试只使用手工构造的 Page 字段，没有打开真实 PDF，也没有导入 PyMuPDF。

## 人工复核方法

1. 打开 `src/inspection_plan/document_parser/models.py`，核对字段、枚举、1-based 页码和状态一致性规则。
2. 打开 `docs/page_model.md`，核对数据流、字段表、序列化与设计边界。
3. 搜索 `src/inspection_plan/document_parser/`，确认没有 `pymupdf`、`fitz`、OCR 引擎或页面读取调用。
4. 运行全套 pytest，确认 28 个案例通过。
5. 手工构造 text、ocr、empty、failed 页面，调用 `to_dict()` 和 `to_json()` 检查字段。
6. 尝试传入 `page_no=0`、绝对路径、非法 parse_method 或 failed/null error，确认模型拒绝。
7. 如果模型包含坐标、表格、图片、Clause、Embedding、数据库对象或 Parser 实现，说明当前设计过度复杂。

## 本任务未实现内容

- 真实 PDF 读取和 Text PDF Parser。
- OCR、PDF 页面渲染和 OCR Parser。
- Page JSONL 批量输出链路。
- Clause Parser、页眉页脚和表格解析。
- DOCX、BM25、Embedding、RAG、LLM、数据库和 FastAPI。
- TASK-002.4 及后续功能。
