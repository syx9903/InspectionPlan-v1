# TASK-002.10.4 过程记录

## 1. 任务目标

把PP-StructureV3已序列化的单表dict确定性转换成独立Table/TableCell，不改变内容
含义，也不把Adapter输出包装成已验证事实。

## 2. Adapter边界

Adapter只接收dict/list/str和显式来源字段，不导入PaddleOCR，不运行模型、不检测
页面、不接入Page或Router。

## 3. PP-Structure字段

使用pred_html、cell_box_list和已确认配对的table block_bbox。table_ocr_pred只用于
分析映射限制，不参与Cell文字或confidence映射。

## 4. Table映射

来源字段全部由调用方显式提供；row/column来自HTML；raw_html原样保留pred_html；
table bbox采用table block四坐标。

## 5. Cell映射

每个真实td/th映射一个Cell。HTML自然遍历序号与cell_box_list同序映射；文字仅做
标准HTML entity解码，不strip、不normalize、不纠错。

## 6. rowspan/colspan

占位集合算法计算1-based左上锚点，并跳过前序span覆盖位置。不创建fake empty cell，
越界或冲突明确失败。

## 7. bbox映射

真实5表的HTML cell/cell_box数量分别为48、48、12、36、55，全部一一相等；bbox
格式为 `[x0,y0,x1,y1]`。数量不匹配时抛出TableAdapterError。

## 8. raw_text与risk

raw_text保留上游输出，即使已知原页不同也不修正。数字、圈号和问号只生成风险提示，
不生成已知错误标签。所有Cell均unreviewed且verified_text为null。

## 9. confidence

table_ocr_pred在真实页中与Cell数量不一致，无法安全聚合。ocr_confidence保持null，
不生成ocr_low_confidence。

## 10. 真实5表验证

离线读取PQ-015、PQ-016、PQ-012既有raw，生成5个Table、199个Cell；行列为
12×4、12×4、3×4、9×4、9×8。PQ-012保留3个rowspan和2个colspan cell。

## 11. 新增与修改

新增：

- `src/inspection_plan/document_parser/table_adapter.py`
- `scripts/adapt_ppstructure_tables.py`
- `tests/test_table_adapter.py`
- `tests/fixtures/ppstructure_table/simple_table.json`
- `docs/table_adapter.md`
- `docs/task_logs/TASK-002.10.4.md`

公共入口只新增Adapter与异常导出。运行产物位于被Git忽略的
`data_processed/tables/`。

## 12. 测试

测试覆盖普通表、rowspan/colspan组合、1-based索引、raw中文/圈号、状态、风险、
bbox、confidence留空、缺字段、破损HTML、box数量不匹配和JSON序列化，均不调用模型。

## 13. 人工复核

打开真实Table JSON与原table HTML对照；检查PQ-012合并锚点；检查原上游错误如 `9`
仍为raw_text=9；确认199个Cell均unreviewed且verified_text为null。

## 14. 未实现内容

未实现正式Table Parser、模型推理、表格检测、OCR/数字纠错、Page/Router接入、
Clause绑定、法规语义、Numeric Requirement和TASK-002.10.5。
