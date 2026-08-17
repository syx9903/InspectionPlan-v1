# PP-StructureV3 → Table 最小适配器

## 1. Adapter职责

Adapter把已经序列化为普通dict的PP-StructureV3单表结果转换为项目内部冻结的
`Table/TableCell`。它隔离第三方字段格式，保留来源、二维结构、HTML、原始文字和
bbox，但不检测表格、不调用OCR、不纠错，也不宣称内容经过人工验证。

```text
PP-StructureV3 raw dict
→ adapt_ppstructure_table(...)
→ Table
└─ TableCell[]
```

## 2. 输入与真实字段

Adapter直接使用：

| 输入 | 来源 | 用途 |
|---|---|---|
| pred_html | table_res_list项 | HTML文字、行列、rowspan、colspan、raw_html |
| cell_box_list | table_res_list项 | 按HTML cell遍历顺序映射Cell bbox |
| table_bbox | 已确认配对的table block.block_bbox | Table bbox |
| table_id | 调用方显式提供 | 稳定Table标识 |
| document_id | 调用方显式提供 | 来源文档 |
| source_category | 调用方显式提供 | 来源目录类别 |
| relative_path | 调用方显式提供 | 原PDF相对路径 |
| page_no | 调用方显式提供 | 1-based原页码 |
| table_index | 调用方显式提供 | 1-based页内表格号 |

没有从文件名、表题或标准文字猜测document_id及法规信息。

真实raw中，table区域位于 `parsing_res_list`：

```json
{
  "block_label": "table",
  "block_bbox": [103, 220, 873, 618],
  "block_content": "<html>...</html>"
}
```

离线验证脚本先要求table block与table_res数量相等，并逐项要求
`block_content == pred_html`，确认对应关系后才把block_bbox传入Adapter。因此bbox
不是只凭两个列表的位置猜测。

## 3. Table映射

| Table字段 | 映射 |
|---|---|
| table_id | 调用方参数 |
| document_id | 调用方参数 |
| source_category | 调用方参数 |
| relative_path | 调用方参数 |
| page_no | 调用方参数 |
| table_index | 调用方参数 |
| bbox | table block的 `[x0,y0,x1,y1]` |
| row_count | HTML `<tr>` 数量 |
| column_count | rowspan/colspan占位后的最大列号 |
| cells | 每个真实td/th生成一个TableCell |
| raw_html | 原始pred_html，不美化、不覆盖 |

## 4. Cell映射

| TableCell字段 | 映射 |
|---|---|
| row_index | HTML占位算法得出的1-based行锚点 |
| column_index | HTML占位算法得出的1-based列锚点 |
| bbox | 同遍历序号cell_box_list `[x0,y0,x1,y1]` |
| rowspan/colspan | td/th属性；缺省为1 |
| raw_text | HTML cell内部文字原样拼接 |
| verified_text | 固定None |
| review_status | 固定unreviewed |
| content_type | 最小确定性规则 |
| risk_flags | 根据当前raw_text生成风险提示 |
| ocr_confidence | 固定None |

HTMLParser默认把 `&amp;` 等entity解码为对应Unicode，这是唯一允许的文字层转换。
Adapter不strip空白、不做Unicode normalization、不转换圈号、不修正数字。

## 5. rowspan / colspan算法

算法维护被已放置cell跨度占用的 `(row,column)` 集合：

1. 按HTML `<tr>` 和其中td/th的自然顺序遍历。
2. 每行从column=1开始。
3. 若当前位置已被前序rowspan占用，持续右移到第一个空位。
4. 当前cell锚定在该位置。
5. 将其rowspan×colspan覆盖区域登记为占用。
6. 后续cell从当前span之后继续查找。

只为HTML中的真实td/th创建Cell；span覆盖位置不会生成fake empty cell。rowspan越过
总行数、覆盖冲突或无法确定行列时拒绝适配。

## 6. bbox映射证据

5张真实表中，HTML真实cell数与cell_box_list数量完全一致：

```text
PQ-015：48/48、48/48、12/12
PQ-016：36/36
PQ-012：55/55
```

cell_box_list坐标已确认是 `[x0,y0,x1,y1]`，且首格及逐行坐标与HTML遍历一致。
只要数量不一致，Adapter就停止，不按猜测截断、补齐或复用bbox。

## 7. raw_text与人工状态

Adapter遵循：

```text
PP输出是什么
→ raw_text就是什么
```

例如PP把原页 `⑤⑨` 识别成 `9`，Adapter保存：

```json
{
  "raw_text": "9",
  "verified_text": null,
  "review_status": "unreviewed"
}
```

不会偷偷恢复为 `⑤⑨`。即使OCR confidence很高，Adapter也无权设置reviewed。

## 8. content_type与risk_flags

内容分类只使用确定性字符规则：

- 空字符串：empty。
- 数字、比较符号、小数、范围、百分号和常见单位：numeric。
- 普通文字：text。
- 中文+数字或标准号等明显字母数字组合：mixed。

风险规则：

- 有数字或圈号数字：numeric_content。
- 当前字符串含圈号数字或问号占位：special_symbol。
- 出现上述风险：manual_review_required。
- 不生成 `ocr_wrong` 等已知错误标签，因为Adapter没有Gold。

Unicode范围明确覆盖⓪、①～⑳、㉑～㉟、㊱～㊿，但不把它们转换成阿拉伯数字。

## 9. confidence限制

`table_ocr_pred`不能稳定和HTML Cell一一对应：

```text
PQ-016：37条OCR文字 / 36个Cell
PQ-012：91条OCR文字 / 55个Cell
```

因此不能按顺序映射，也不对文字级score做无依据平均。所有Cell：

```text
ocr_confidence = null
```

同时不生成 `ocr_low_confidence`。未来如第三方提供稳定cell级confidence，可另行设计。

## 10. 失败策略

以下情况抛出 `TableAdapterError`：

- table_result不是dict；
- 缺失或空pred_html；
- 缺失cell_box_list；
- HTML不是恰好一个完整table；
- td/th不在合法tr内；
- 无法确定行列；
- rowspan/colspan非法或冲突；
- cell_box_list数量与HTML cell数不一致；
- Table/Cell bbox不是合法四坐标；
- 来源字段违反Table模型约束。

可选confidence无法映射不会导致失败，而是保留null。

## 11. 真实5表验证

| table_id | rows | columns | cells | rowspan cells | colspan cells |
|---|---:|---:|---:|---:|---:|
| GBT_30579_2022_p119_t01 | 12 | 4 | 48 | 0 | 0 |
| GBT_30579_2022_p119_t02 | 12 | 4 | 48 | 0 | 0 |
| GBT_30579_2022_p119_t03 | 3 | 4 | 12 | 0 | 0 |
| GBT_30579_2022_p120_t01 | 9 | 4 | 36 | 0 | 0 |
| NBT_47018_1_2017_p6_t01 | 9 | 8 | 55 | 3 | 2 |

199个Cell全部unreviewed，verified_text全部为null。转换只读取已有raw，没有重新运行
PP-StructureV3。

## 12. PQ-012合并单元格

人工核对的关键锚点：

| row,column | rowspan | colspan | raw_text |
|---|---:|---:|---|
| 1,1 | 2 | 1 | 焊接材料类型 |
| 1,2 | 1 | 7 | 材料类别及检验项目 |
| 4,1 | 3 | 1 | GTAW、GMAW、PAW 用焊丝和填充丝 |
| 7,1 | 2 | 1 | SAW、dESW用焊丝 -焊剂、焊带-焊剂 |
| 9,1 | 1 | 8 | 表下注释原始文字 |

结果与HTML的3处rowspan、2处colspan一致，且后续行的column_index正确跳过被占位置。

## 13. 输出与存储边界

真实实验每张Table写为一个JSON：

```text
data_processed/tables/<document_id>_p<page_no>_t<table_index>.json
```

这是便于人工查看的实验产物，不是正式全库存储方案。

## 14. 与Page和Clause的关系

当前只通过：

```text
document_id + relative_path + page_no
```

关联原PDF页面。Page没有新增 `tables[]`；Table没有owner_clause_id、chapter_no或
clause_no。Clause-Table绑定等待Clause Schema建立后单独设计。

## 15. 设计边界

Adapter不实现表格检测、模型推理、OCR纠错、人工修正、Page/Router接入、Clause
绑定、法规语义、Numeric Requirement或正式Table Parser。

