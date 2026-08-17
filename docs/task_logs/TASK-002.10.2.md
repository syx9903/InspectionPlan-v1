# TASK-002.10.2 过程记录

## 1. 任务目标

定位TASK-002.10.1中中文显示异常的层次，并评价少量真实法规表格的结构、中文和
关键数字质量，不接入生产链路。

## 2. 上一任务发现

PP-StructureV3能检测表格、输出HTML和cell box，并恢复rowspan/colspan；同时曾在
终端观察到中文乱码，圈号和标引数字存在识别错误。

## 3. 表格样本

- PQ-015，第119页，3张规则型4列表。
- PQ-016，第120页，1张带水印的续表。
- PQ-012，第6页，1张含rowspan/colspan的mixed-layout表。

## 4. 编码诊断

Python对象、`table_ocr_pred`、`pred_html`均含正确Unicode；JSON明确使用UTF-8和
`ensure_ascii=False`。此前 `±í` 等显示来自Windows默认GBK控制台与外部捕获链的
转码，不是raw文件损坏。没有执行GBK反解或任何OCR自动纠错。

## 5. UTF-8 round-trip

3个样本全部满足：写前对象等于UTF-8重新读取后的对象；文件均无BOM。

## 6. 表格结构

5/5表格检出，5/5行列正确，5/5合并结构正确。PQ-012正确保留3处rowspan和2处
colspan。

## 7. 中文结果

抽检21个中文cell，18个exact，3个minor/wrong，exact rate 85.71%。错误包括水印
混入、多字符和括号缺失。

## 8. 数字结果

抽检26个数字cell，15个exact、11个wrong，exact rate 57.69%。普通条款号较好，
双圈号标引经常缺字符、退化成普通数字或问号。

## 9. 性能

PQ-016本次初始化3046.011 ms、预测42293.715 ms。PQ-015和PQ-012复用上一任务
结果，预测分别为184945.379 ms和101324.852 ms。

## 10. 工程结论

选择B：结构可靠，但文本/数字仍需额外质量层。可以进入独立Table Schema设计，
但必须保留原始值、坐标、页码、图片证据及风险标记，不能直接信任法规数字。

## 11. 新增与修改

新增：

- `scripts/evaluate_table_output_quality.py`
- `tests/test_table_output_quality_evaluation.py`
- `docs/table_output_quality_evaluation.md`
- `docs/task_logs/TASK-002.10.2.md`

运行产物及人工实验标签位于 `data_processed/table_experiments/`，受Git忽略。
没有修改业务Parser、Router、Page Schema或requirements。

## 12. 人工复核方法

打开实验HTML并按 `summary.json` 的原PDF路径和页码逐cell核对；使用
`normalized.json`检查结构，使用 `round_trip.json`检查编码等值。

## 13. 未实现内容

未实现正式Table Parser/Table Schema、自动表格路由、OCR纠错、全库处理、Page或
Router接入、流程图/figure解析及TASK-002.10.3。
