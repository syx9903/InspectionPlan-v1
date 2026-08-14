# Page 数据模型

## Page 的职责

`Page` 是文档解析阶段统一的页面级数据契约。无论最终文字来自 PDF 文本层还是 OCR，上游 Parser 都必须生成同一种 `Page`，下游 Clause Parser 因而不需要依赖具体解析技术。

`Page` 只保存页面最终正文、来源、解析方式、状态和必要追溯信息。它不是 PDF Parser、OCR 结果明细、版面模型或法规条款模型。

## 数据流位置

```text
Text Parser ─┐
             ├→ Page → Clause Parser
OCR Parser ──┘
```

当前 TASK-002.3 只实现中间的 Page Schema；图中的 Parser 和 Clause Parser 尚未实现。

## 字段说明

| 字段 | 类型 | 必填 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `document_id` | `str` | 是 | 上游提供的稳定文档标识；模型不负责生成 | `GB12337_2014` |
| `source_category` | `str` | 是 | 来源资料目录类别 | `球罐标准` |
| `relative_path` | `str` | 是 | 相对项目根目录、使用正斜杠的来源路径 | `data/球罐标准/test.pdf` |
| `file_name` | `str` | 是 | 原始文件名，必须匹配相对路径末段 | `test.pdf` |
| `page_no` | `int` | 是 | 从 1 开始的 PDF 人工页序 | `12` |
| `text` | `str` | 是 | 最终提供给 Clause Parser 的正文；空白或失败页为 `""` | `测试法规正文。` |
| `parse_method` | `text \| ocr` | 是 | 最终文字来自直接文本层还是 OCR | `text` |
| `text_status` | `success \| empty \| failed` | 是 | 成功、正常空白或解析失败 | `success` |
| `char_count` | `int` | 自动 | `len(text)`，包含空格和换行，不能由调用者传入 | `7` |
| `error` | `str \| null` | 否 | 失败时的简短异常摘要；其他状态必须为 `null` | `null` |

## 页码约定

`Page.page_no` 表示 PDF 文件中按人工阅读顺序看到的第几页，采用 1-based：第一页为 `1`。后续 PyMuPDF Parser 如果使用从 0 开始的内部索引，必须在创建 Page 时加 1。模型拒绝 `0`、负数、布尔值和非整数。

这里的页码是 PDF 文件页序，不是页面正文印刷的页码，也不是法规章节页码。

## parse_method

- `text`：最终 `text` 直接来自 PDF 文本层。
- `ocr`：最终 `text` 来自 OCR。

不提供 `unknown`，因为 Page 应由已经选择解析路径的 Parser 创建。模型不存储独立 `ocr_used` 字段；`page.parse_method == ParseMethod.OCR` 已能表达相同事实，`page.ocr_used` 只作为派生只读属性提供，避免两份数据不一致。序列化结果也不重复保存 `ocr_used`。

## text_status

- `success`：解析完成且 `text` 至少包含一个非空白字符，`error` 必须为 `null`。
- `empty`：解析正常完成，但页面没有正文；`text` 必须为 `""`，`error` 必须为 `null`。
- `failed`：页面解析失败；`text` 必须为 `""`，并提供非空的简短 `error`。

空白页面是合法数据，与异常失败不同。为避免下游误用部分结果，当前 baseline 不允许 `failed` 页面同时携带正文。

## 路径约束

`relative_path` 必须使用正斜杠并相对于项目根目录。模型拒绝 POSIX/Windows 绝对路径、反斜杠、`.` 和 `..` 路径段，并要求路径末段与 `file_name` 相同，从而避免数据绑定某台电脑或来源字段互相矛盾。

## 序列化

`Page.to_dict()` 返回只含字符串、整数和 `null` 的 JSON 兼容字典；枚举会转换为其字符串值。`Page.to_json()` 使用 UTF-8 友好的 `ensure_ascii=False` 输出 JSON 字符串。字段顺序固定，且不会包含派生的重复字段 `ocr_used`。

示例：

```python
from src.inspection_plan.document_parser import Page

page = Page(
    document_id="GB12337_2014",
    source_category="球罐标准",
    relative_path="data/球罐标准/test.pdf",
    file_name="test.pdf",
    page_no=12,
    text="测试法规正文。",
    parse_method="text",
    text_status="success",
)

payload = page.to_dict()
json_text = page.to_json()
```

## 设计边界

当前 Page 不保存：

- Clause、章节或条款编号；
- Embedding、检索分数或法规适用性；
- blocks、bbox、OCR boxes、confidence；
- 表格二维结构、图片或页面渲染结果；
- 页眉页脚处理结果；
- width、height 等版面坐标信息。

只有后续任务证明下游确实需要某个字段时，才应扩展模型。
