# TASK-002.8：统一 PDF → Page 链路小规模质量抽检

## 任务目标

用可人工复核的真实小样本判断当前 Page 数据是否足以进入 Clause Parser，重点
评估20字符 Text 路由 baseline、OCR 正文、数字、标准号、条款号及复杂版面。

## 样本选择方法

共选择25页：6页 text PDF、8页 no_usable_text PDF、11页 mixed PDF；按最终
parse_method 为12个 Text、13个 OCR。样本覆盖3份 Text PDF、2份扫描 PDF 和1份
mixed PDF，包含正文、首页、目录、短页、密集条款、表格、球罐图示及流程图。
抽样有意覆盖风险边界，不能作为全库坏页比例估计。

## 人工质量标签与错误类型

使用 `good / acceptable / bad`。错误类型固定为任务定义的11类，没有增加自动质量
分数。Codex 逐页对照120 DPI原页图像、完整 JSONL 和 preview 后填写标签，并明确
标记为“非用户确认 Gold”。

## 实际抽检结果

| 方法 | good | acceptable | bad |
| --- | ---: | ---: | ---: |
| text | 4 | 1 | 7 |
| ocr | 2 | 4 | 7 |

按来源：text PDF 为4/1/1，no_usable_text PDF 为2/4/2，mixed PDF 的11个风险
样本全部为 bad。主要错误次数：ocr_typo 9，figure_label_error 8，
reading_order_error 8，garbled_text 7，missing_text 7，number_error 5，
watermark_noise 5，table_layout_loss 4。

## Text 问题

发现字符数足够但正文不可用：mixed 第119、120、121、149页大面积乱码；第144、
145页刚超过阈值但只有伪文本，流程图主体缺失；GB/T 3274封面只提取到收藏水印。
这证明20字符不能独立判断正文质量。

## OCR 问题

连续正文中文总体可读，`70%`、`7.2.3`、`7.3`、`NB/T 47018.1—2017` 等关键内容
多数可识别；连接符仍可能与“一”混淆。表格、球罐图示和流程图的二维关系无法由
当前 OCR 行文本可靠恢复，标引序号与标签也容易错位。

## 是否适合进入 Clause Parser

不适合无条件直接进入。good/acceptable 正文可供后续使用，但 bad 页面没有质量
信号，下游会把乱码或伪文本误当法规。应先建立文本层质量判定 baseline，再改进
Text/OCR 路由依据。

## 新增文件与产物

新增 Git 跟踪文件：

- `scripts/sample_page_quality.py`
- `tests/test_sample_page_quality.py`
- `docs/page_quality_evaluation.md`
- `docs/task_logs/TASK-002.8.md`

运行产物位于被忽略的：

- `data_processed/evaluation/page_quality_sample.json`
- `data_processed/evaluation/page_quality_manual_labels.json`
- `data_processed/evaluation/page_quality_images/`
- 本次少量补充 Page JSONL。

未修改任何 Parser、路由规则、阈值或 Page Schema。

## 自动测试

辅助脚本新增8个测试，覆盖 JSONL 读取、方法筛选、数量、原始页码、preview、字符
统计、空人工标签和不修改原记录。人工质量标签本身没有伪造自动测试结论。

## 人工复核方法

打开评估 JSON，按 sample_id 对照评估图片、原 PDF 的 `relative_path/page_no` 和
完整 Page JSONL。优先复核 bad Text 以及 OCR 的数字、条款号、表格和流程图。标签
元数据会说明评审者与依据，允许用户独立修订。

## 未实现与后续建议

未修改20字符规则，未实现自动质量分数、乱码修复、OCR纠错、Clause、页眉页脚或
水印过滤、表格恢复、检索、RAG、服务、数据库或 TASK-002.9。

后续建议：`TASK-002.9：建立文本层质量判定 baseline，改进 Text/OCR 路由依据`。
