# TASK-002.10.5 过程记录

## 1. 任务背景

项目已具备 PDF→Page 和 PP-StructureV3 raw→Table→TableCell 两条链路，但物理表格尚不能显式表达条款归属、正文引用或跨页续表关系。本任务建立独立、可解释、可人工修正的关联数据边界。

## 2. 用户关注的问题

“表属于哪个法规”可由 Table 的 `document_id` 与 `relative_path` 回答；“属于哪个章节或 Clause”是另外的语义判断，需要保留判断方式、依据及复核状态，不能混入 Table 原始结构。

## 3. 当前 Document / Page 追溯能力

Table 通过 `document_id + relative_path` 定位文档，通过 `document_id + page_no` 对齐 Page，并用 `table_index + bbox` 定位页内表格。这些均是确定性物理来源信息。

## 4. 为什么 Page 不足以确定 Clause

同一 Page 可能包含多个 Clause 和多个 Table；一个表可能位于上一条款之后，却由下一条款显式引用。因此页号只能缩小候选范围，不能代表 Clause 归属。

## 5. 关联模型

- 新增 `TableClauseLink`，表达 `belongs_to` 与 `referenced_by`。
- 新增 `TableContinuationLink`，表达两个物理 Table 片段的定向 `continuation`。
- 新增独立枚举，区分关系、绑定方法、证据类型和关联复核状态。
- 保持既有 Page、Table 和 Adapter Schema 不变。

## 6. 多对多关系

关联采用独立记录，因此一个 Clause 可对应多个 Table，一个 Table 也可对应多个 Clause。同一对端点还可分别保留版面归属和正文引用关系。

## 7. Continuation

续表属于 Table→Table 关系。当前仅记录前后片段和证据，不创建 LogicalTable、不合并行列，也不自动识别“（续）”。

## 8. Binding evidence

`binding_method` 明确区分 deterministic、heuristic 和 manual；`evidence_types` 保存结构化理由，`evidence_texts` 可保存短原文。当前没有可靠标定依据，因此没有添加可能被误解为正确概率的 confidence。

人工修正创建新 Link，以 `supersedes_link_id` 指向旧记录，并要求 `manual + corrected + notes`，为持久化层保留审计链提供基础。

## 9. 新增与修改文件

新增：

- `src/inspection_plan/document_parser/evidence_links.py`
- `tests/test_evidence_links.py`
- `docs/table_evidence_link_design.md`
- `docs/task_logs/TASK-002.10.5.md`

修改：

- `src/inspection_plan/document_parser/__init__.py`：仅导出新增关联模型和枚举。

## 10. 测试

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

专项测试共 12 项，完整测试共 175 项，全部通过。覆盖合法 Table-Clause / continuation、必填 ID、枚举、证据去重、复核与修正约束、JSON 中文、续表端点及对 PP-StructureV3/Clause 类的零依赖。

## 11. 人工复核

1. 打开 `evidence_links.py`，确认 Clause 仅通过字符串 `clause_id` 引用。
2. 对比 Git diff，确认 `models.py`、`table_models.py` 和 `table_adapter.py` 未修改。
3. 打开设计文档，核对多对多、三种绑定方式和三个手工示例。
4. 确认仅空间邻近的 Case B 标记为 `heuristic`。
5. 运行完整 pytest，并检查 `git diff --check`。

## 12. 未实现内容

未实现 Clause Parser 或完整 Clause Schema；未实现自动 Table-Clause 匹配、最近 Clause、表号/显式引用解析、空间计算或续表检测；未接入 Router、PP-StructureV3；未修改 Page/Table Schema；未开展 TASK-003。
