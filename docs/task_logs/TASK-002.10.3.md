# TASK-002.10.3 过程记录

## 1. 任务背景

TASK-002.10.2得到5/5正确表格结构，但中文cell exact rate为85.71%，数字cell仅
57.69%。二维结构值得保留，OCR原值和人工核验风险也必须成为正式模型的一部分。

## 2. 为什么需要独立 Table

`Page.text`不能表达数字所属行列、二维表头和合并单元格。Table通过document_id、
relative_path、page_no独立关联Page，不修改Page Schema。

## 3. Schema设计

新增 `BoundingBox`、`Table`、`TableCell`、`CellContentType`、`CellRiskFlag` 和
`ReviewStatus`。未增加Row模型；Cell使用1-based行列索引及rowspan/colspan。

## 4. raw / verified 双值

`raw_text`冻结保存上游值；`verified_text`仅保存人工确认结果。不设置自动
normalized_text，避免未经核验的法规数字被下游当成事实。

## 5. 风险设计

内容类型与质量风险分开。最小风险集合为numeric_content、special_symbol、
ocr_low_confidence和manual_review_required。风险只触发关注，不表示一定错误。

## 6. 人工核验状态

- unreviewed：verified_text必须为空。
- reviewed：verified_text必须等于raw_text。
- corrected：verified_text必须存在且不同于raw_text。

## 7. 来源追溯

Table保存文档、相对路径、页码、页内序号和bbox；Cell保存行列、跨度和bbox。路径
拒绝绝对地址，bbox验证方向和有限性。

## 8. 一致性约束

页码、表格序号、行列和跨度均至少为1；Cell锚点与跨度不能越界；重复锚点被拒绝；
OCR confidence若存在必须位于0～1。未实现完整矩阵覆盖校验。

## 9. 新增与修改

新增：

- `src/inspection_plan/document_parser/table_models.py`
- `tests/test_table_models.py`
- `docs/table_model.md`
- `docs/task_logs/TASK-002.10.3.md`

修改公共入口 `src/inspection_plan/document_parser/__init__.py`，只导出新类型。
现有 `models.py` 和Page定义未修改。

## 10. 测试

新增测试覆盖正常创建、1-based索引、span、bbox、raw/verified、人工状态、Cell越界、
confidence、JSON、中文与 `⑤⑨` round-trip，以及不依赖PaddleOCR。

## 11. 人工复核

打开模型文件检查字段与Docstring；运行新增测试；检查Page和三类Parser/Router无diff；
搜索table_models确保不存在paddleocr或PPStructureV3导入。

## 12. 未实现内容

未实现正式Table Parser、PP-Structure适配器、Page接入、自动路由、OCR纠错、Clause
引用、法规语义、Numeric Requirement及TASK-002.10.4。
