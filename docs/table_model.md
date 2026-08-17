# 独立 Table 数据模型

## 1. Table 的职责

Table保存法规PDF表格的二维结构和原始证据，包括来源页、表格/单元格坐标、行列、
合并关系、原始OCR文字和人工核验状态。它不是法规语义模型，不判断某列是不是压力、
温度、材料或检验比例。

如果只把表格塞进 `Page.text`，会丢失数字所属行列、单位所属表头以及rowspan/
colspan关系。TASK-002.10.2虽然得到5/5结构正确，但数字cell exact rate只有57.69%，
因此模型还必须保留原值、风险和人工证据。

## 2. 数据关系

```text
PDF Page
   │ document_id + relative_path + page_no
   ▼
Table
   │ table_index + bbox
   ▼
TableCell[]
     row_index + column_index + bbox
```

当前Page不持有 `tables[]`。Table通过来源字段独立关联原页，未来Clause可以引用
table_id或具体cell，但本任务不定义引用逻辑。

## 3. 为什么没有 Row 模型

TableCell已经保存1-based `row_index`、`column_index`、`rowspan`和`colspan`。
单独Row不会增加证据，只会重复索引并使合并单元格表达更复杂，因此当前保持
`Table → cells[]` 两层结构。

## 4. BoundingBox 字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| x0 | float | 是 | 左边界，单位继承上游 |
| y0 | float | 是 | 上边界，单位继承上游 |
| x1 | float | 是 | 右边界，必须 `>= x0` |
| y1 | float | 是 | 下边界，必须 `>= y0` |

坐标必须是有限数值。模型不擅自把像素换算成PDF point；回查时必须使用与上游相同
的页面坐标系。

## 5. Table 字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| table_id | str | 是 | 上游给出的稳定表格标识 |
| document_id | str | 是 | 来源文档标识 |
| source_category | str | 是 | 检验规范、球罐标准等来源类别 |
| relative_path | str | 是 | 项目根目录相对PDF路径，只使用 `/` |
| page_no | int | 是 | 1-based原PDF页码 |
| table_index | int | 是 | 1-based页内表格序号 |
| bbox | BoundingBox | 是 | 表格在来源页中的区域 |
| row_count | int | 是 | 表格总行数，至少1 |
| column_count | int | 是 | 表格总列数，至少1 |
| cells | tuple[TableCell] | 是 | 结构化单元格；可以为空但通常应有内容 |
| raw_html | str/null | 否 | 上游近原始HTML结构证据 |

保留raw HTML是为了在适配器遗漏某些结构时仍能回查rowspan、colspan和上游原始
输出。它会带来第三方格式耦合，但当前真实样本体积可接受，证据保真优先。

## 6. TableCell 字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| row_index | int | 是 | 1-based行索引；合并单元格取左上锚点 |
| column_index | int | 是 | 1-based列索引；合并单元格取左上锚点 |
| bbox | BoundingBox | 是 | 单元格在来源页中的区域 |
| rowspan | int | 是 | 跨行数，默认1 |
| colspan | int | 是 | 跨列数，默认1 |
| raw_text | str | 是 | 上游原始识别值，永远不被覆盖 |
| verified_text | str/null | 否 | 人工确认或修正后的值 |
| content_type | enum | 是 | `text/numeric/mixed/empty` |
| review_status | enum | 是 | `unreviewed/reviewed/corrected` |
| risk_flags | enum列表 | 是 | 最小内容/质量风险集合，默认空 |
| ocr_confidence | float/null | 否 | 0～1模型信号，不是正确性证明 |

Cell锚点及跨度不能越过Table行列边界，同一Table不能有重复锚点。模型不自动验证
合并单元格是否完整覆盖整个矩阵，避免过早实现复杂布局验证器。

## 7. raw_text / verified_text

```text
raw_text = 上游模型原始值，冻结保留
verified_text = 人工核验结果，未核验时为 null
```

例如上游把 `⑤⑨` 识别为 `9`：

```json
{
  "raw_text": "9",
  "verified_text": "⑤⑨",
  "review_status": "corrected"
}
```

不设置 `normalized_text`。当前没有可靠自动纠错规则，若直接保存normalized值，容易
让下游误以为该值已被证实。raw/verified双值能保留识别历史和人工责任边界。

## 8. review_status

| 状态 | verified_text约束 | 含义 |
|---|---|---|
| unreviewed | 必须为null | 尚未人工核验 |
| reviewed | 必须等于raw_text | 人工确认原始值正确 |
| corrected | 必须存在且区别于raw_text | 人工确认并修正 |

状态约束防止出现“标为corrected却没有修正值”或“未核验却携带貌似已确认值”的
矛盾记录。本任务不实现核验界面或操作者审计字段。

## 9. 内容类型与风险字段

`content_type`：

- `text`
- `numeric`
- `mixed`
- `empty`

`risk_flags`：

- `numeric_content`：包含需重点核验的数字；不表示数字一定错误。
- `special_symbol`：圈号、特殊标引等高风险字符。
- `ocr_low_confidence`：上游给出低置信度信号。
- `manual_review_required`：流程明确要求人工复核。

内容属性和质量风险分开。一个正确的 `70%` 仍可以同时是 `numeric` 并携带
`numeric_content`，表示下游不能无证据直接用于检验方案。

## 10. 来源追溯

```text
table.document_id + relative_path
→ 原PDF
table.page_no
→ 原页
table.table_index + table.bbox
→ 原表格区域
cell.row_index + column_index + cell.bbox
→ 原单元格区域
```

未来适配器必须确保bbox坐标系与来源页面图像一致。模型不接受绝对路径，避免换电脑
后证据链接失效。

## 11. 2×3示例 JSON

```json
{
  "table_id": "test_t1",
  "document_id": "test",
  "source_category": "检验规范",
  "relative_path": "data/检验规范/test.pdf",
  "page_no": 6,
  "table_index": 1,
  "bbox": {"x0": 0, "y0": 0, "x1": 300, "y1": 200},
  "row_count": 2,
  "column_count": 3,
  "cells": [
    {
      "row_index": 1,
      "column_index": 1,
      "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 50},
      "rowspan": 1,
      "colspan": 1,
      "raw_text": "检验项目",
      "verified_text": null,
      "content_type": "text",
      "review_status": "unreviewed",
      "risk_flags": [],
      "ocr_confidence": null
    },
    {
      "row_index": 2,
      "column_index": 3,
      "bbox": {"x0": 200, "y0": 50, "x1": 300, "y1": 100},
      "rowspan": 1,
      "colspan": 1,
      "raw_text": "9",
      "verified_text": "⑤⑨",
      "content_type": "numeric",
      "review_status": "corrected",
      "risk_flags": ["numeric_content", "special_symbol"],
      "ocr_confidence": 0.93
    }
  ],
  "raw_html": "<table>...</table>"
}
```

示例声明为2×3表，但只列出两个有代表性的Cell；模型不强制完整矩阵覆盖。

## 12. 特殊字符序列化

模型使用 `json.dumps(..., ensure_ascii=False)`。测试已确认：

```text
raw_text = "⑤⑨"
→ to_json()
→ json.loads()
→ raw_text == "⑤⑨"
```

模型不会对圈号进行规范化、拆分或自动纠错，只保证上游提供的Unicode不被二次损坏。

## 13. 设计边界

本模型不包含：

- Page的 `tables[]`
- Table Parser或PP-StructureV3适配逻辑
- Clause及Clause到Table/Cell的引用
- 压力、温度、材料、检验比例等法规语义字段
- Numeric Requirement Parser
- OCR自动纠错、LLM或VLM
- Embedding、检索或数据库结构

