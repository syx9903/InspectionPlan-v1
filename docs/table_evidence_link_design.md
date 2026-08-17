# Table 与 Page / Clause 证据关联设计

## 1. 为什么 Table 不能直接挂 `owner_clause_id`

`Table` 描述从某个 PDF 物理页面识别出的表格证据；“属于某条款”或“被某条款引用”则是可变化、可复核的语义判断。两者不能混为同一原始对象字段。

此外，关联不是一对一：一个 Clause 可以引用多个 Table，一个 Table 也可能被多个 Clause 引用。单值 `owner_clause_id` 无法表达显式引用与版面归属的差别，也无法同时保留多个判断及其证据。因此本设计不修改 Table Schema，而将关系保存为独立记录。

## 2. 物理来源关联

Table 已有 `document_id`、`relative_path`、`page_no`、`table_index` 和 `bbox`：

- `document_id` 与 `relative_path` 定位来源法规；
- `Table.document_id == Page.document_id` 且 `Table.page_no == Page.page_no` 时，确定性定位来源 Page；
- `relative_path` 应同时一致，用于防止不同路径的数据被误接；
- `table_index` 和 `bbox` 定位页内表格及其证据区域。

这是物理来源关系，不是 Clause 语义推断，不需要额外 Page Link 模型。

## 3. 为什么 Page 不能确定 Clause

同一物理页可以同时出现多个条款和多个表格，例如：

```text
7.3.1 正文
表7-2
7.3.2 正文：“检测比例按表7-2执行”
```

仅知道 `page_no = 35`，无法判断表7-2在版面上属于7.3.1，还是在语义上被7.3.2引用。表题、显式引用和空间位置可能给出不同关系，因此 Page 只是检索候选范围，不能代替 Clause 绑定。

## 4. Clause 语义关联：`TableClauseLink`

每条 `TableClauseLink` 表示一个 Table 与一个外部 Clause ID 的一种关系：

| 字段 | 含义 |
| --- | --- |
| `link_id` | 关联记录的稳定标识 |
| `table_id` | 已存在 Table 的稳定标识 |
| `clause_id` | 未来 Clause 系统提供的外部稳定标识 |
| `relation_type` | `belongs_to`（版面/标题归属）或 `referenced_by`（正文引用） |
| `binding_method` | `deterministic`、`heuristic` 或 `manual` |
| `evidence_types` | 结构化、可筛选的绑定依据枚举，至少一项且不得重复 |
| `review_status` | `unreviewed`、`reviewed` 或 `corrected` |
| `evidence_texts` | 可选的短文本证据，不保存完整 Clause 正文 |
| `notes` | 可选审核说明；修正时必填 |
| `supersedes_link_id` | 修正时指向被替代的旧关联；其他状态不得填写 |

`corrected` 记录必须由人工产生，并同时提供 `supersedes_link_id` 和 `notes`。旧记录应由持久化层保留，这样修正不会抹掉历史判断。

## 5. 多对多关系

多对多不需要在 Table 或 Clause 内嵌列表，而由多条 Link 自然表达：

```text
Clause A ── Link 1 ── Table 1
Clause A ── Link 2 ── Table 2
Clause B ── Link 3 ── Table 1
```

同一 Table 与同一 Clause 也可能分别存在 `belongs_to` 和 `referenced_by` 两条关系，因为二者回答的问题不同。

## 6. 跨页续表：`TableContinuationLink`

跨页时，每页产出独立物理 Table，例如 `doc_p35_t01` 与 `doc_p36_t01`。它们是否属于同一逻辑表，是 Table→Table 的连续性，而不是 Table→Clause 关系。

`TableContinuationLink` 保存 `from_table_id`、`to_table_id`、固定的 `continuation` 关系，以及与 TableClauseLink 相同的绑定方法、证据、复核和修正追踪字段。方向必须从前一片段指向后一片段，两个端点不得相同。本任务不引入 `LogicalTable`，也不合并单元格；待实际消费场景明确后再评估逻辑表实体。

## 7. `binding_method`

- `deterministic`：存在可直接核对的明确绑定，例如正文明确引用表7-2且表题编号匹配。
- `heuristic`：基于空间邻近或最近上文等弱证据形成候选。`nearest clause ≠ always correct`，必须保留待复核状态。
- `manual`：由人工直接建立或修正。人工修正还必须链接旧记录并说明原因。

本模型不设置 `confidence`。当前没有稳定、经过评估的计算方法，凭空给出的数值容易被误解为正确概率；`binding_method + evidence_types` 更透明。

## 8. `evidence`

`evidence_types` 当前支持 `same_document`、`same_page`、`caption_match`、`explicit_reference`、`spatial_proximity`、`nearest_preceding_clause`、`same_table_number`、`continuation_marker` 和 `adjacent_page`。

证据类型说明“为什么认为关系成立”，`evidence_texts` 可补充诸如“检测比例按表7-2执行”或“表7-2（续）”的短原文。证据不证明表格文字、数字、Clause 内容或法规语义正确。

## 9. 三个手工示例

### Case A：同页显式引用

```json
{
  "link_id": "link_case_a",
  "table_id": "GBT_demo_p35_t01",
  "clause_id": "GBT_demo_7.3.1",
  "relation_type": "referenced_by",
  "binding_method": "deterministic",
  "evidence_types": ["same_document", "same_page", "explicit_reference", "caption_match"],
  "review_status": "unreviewed",
  "evidence_texts": ["检测比例按表7-2执行", "表7-2 检测比例"],
  "notes": null,
  "supersedes_link_id": null
}
```

### Case B：同页仅空间邻近

```json
{
  "link_id": "link_case_b",
  "table_id": "GBT_demo_p35_t02",
  "clause_id": "GBT_demo_7.3.2",
  "relation_type": "belongs_to",
  "binding_method": "heuristic",
  "evidence_types": ["same_document", "same_page", "spatial_proximity", "nearest_preceding_clause"],
  "review_status": "unreviewed",
  "evidence_texts": [],
  "notes": "仅因表格紧随该条款，尚无显式引用。",
  "supersedes_link_id": null
}
```

该场景只能标为 `heuristic`，因为下一条款可能才是实际引用方。

### Case C：跨页续表

```json
{
  "link_id": "continuation_case_c",
  "from_table_id": "GBT_demo_p35_t01",
  "to_table_id": "GBT_demo_p36_t01",
  "relation_type": "continuation",
  "binding_method": "deterministic",
  "evidence_types": ["same_table_number", "continuation_marker", "adjacent_page"],
  "review_status": "unreviewed",
  "evidence_texts": ["表7-2（续）"],
  "notes": null,
  "supersedes_link_id": null
}
```

## 10. 与未来 Clause Schema 的边界

关联层只把 `clause_id` 当作外部稳定字符串，不定义 `Clause` 类，也不预设 `clause_no`、正文、标题或层级字段。`clause_id` 的生成规则和最终格式由 TASK-003 决定。

## 11. 关联层解决与不解决的问题

关联层可以回答：Table 来源于哪份法规、哪一页和页内哪个位置；它属于或被哪个 Clause 引用；它是否是前一物理表格的续表。

关联层不判断表格文字和数字是否正确，不验证 Clause 内容或法规语义，不做 OCR 纠错，也不替代内容质量层。

## 12. 当前不实现绑定算法

本任务只定义绑定结果如何表达，不实现自动最近 Clause、表号解析、“见表x”解析、空间排序或跨页续表检测，也不接入 Router、PP-StructureV3 或 Clause Parser。
