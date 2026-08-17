# TASK-002.9.2A：bad Page 版面类型复核

## 任务背景与待验证假设

纯文本质量特征无法判断正文覆盖率，用户提出“多数无法识别或乱码页面可能是表格”
的假设。本任务先对 TASK-002.8 的14个 bad Page 逐页看原图分类，避免在没有统计
依据时直接引入 Table Parser。

## bad Page 与标签定义

实际 bad Page 为14个，Text 7、OCR 7。版面标签为 plain_text、table、flowchart、
figure、mixed_layout、cover、other；失败类别为 text_quality、layout_structure、
both、metadata_only、other。`linear_text_sufficient` 判断文字100%正确时线性文本
能否表达核心信息。

## 人工复核过程

逐一查看 TASK-002.8 的120 DPI原 PDF 页面图片，并结合 Page JSONL 与已有错误类型。
标签由 Codex 人工视觉判断，不是用户确认 Gold，也没有运行自动 Layout Detection。
TASK-002.8 的 good/acceptable/bad 标签保持不变。

## 实际统计

- 版面：flowchart 7、table 2、plain_text 2、figure 1、mixed_layout 1、cover 1。
- 失败：both 10、text_quality 2、layout_structure 1、metadata_only 1。
- linear text：true 3、false 11。
- structured layout：11/14，78.6%。

## 表格与流程图/图示占比

严格 table 2/14（14.3%）；包含 mixed_layout 的表格相关页3/14（21.4%）。流程图
7/14（50.0%），图示1/14（7.1%）。因此“多数失败页是表格”不成立，主要结构问题
是流程图和更广义的复杂版面。

## 是否支持引入 Table/Layout Parser

支持后续进行通用 Layout/Table 技术 baseline 实验，因为78.6%的 bad 样本即使文字
完全识别也无法由线性 Page.text 充分表达。但不支持只针对表格设计整个路线；流程图
占比更高，应评估更通用的版面表示。该小样本不能外推全库版面比例。

## 新增文件与运行产物

新增 Git 跟踪文件：

- `scripts/review_bad_page_layouts.py`
- `tests/test_bad_page_layout_review.py`
- `docs/bad_page_layout_review.md`
- `docs/task_logs/TASK-002.9.2A.md`

被忽略产物：

- `data_processed/evaluation/bad_page_layout_manual_labels.json`
- `data_processed/evaluation/bad_page_layout_review.json`

没有修改已有质量标签、Page、Parser、Router 或 text_quality 模块。

## 自动测试

新增11个测试，只验证 bad 筛选、good/acceptable 排除、sample/page_no 保持、枚举、
bool、统计和输入不变，不测试某个 sample 必然属于某类版面。

## 人工复核方法

打开报告与复核 JSON，按 sample_id 对照评估图片，再用 relative_path/page_no 定位
原 PDF。人工判断依赖页面视觉结构，不依赖程序自动分类。Git diff 应确认全部解析
和模型文件无修改。

## 未实现内容

未实现自动版面检测、表格/流程图结构恢复、OCR/Text纠错、Router或Schema修改、
Clause、检索、服务、数据库、DOCX、TASK-002.9.2 或 TASK-002.10。
