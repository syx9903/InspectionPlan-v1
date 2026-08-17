# TASK-002.9.1：文本层质量特征分析

## 任务目标与已知问题

使用 TASK-002.8 的12个 Text Page 和人工工程抽检标签，研究简单确定性特征能否
区分正常正文、乱码和伪文本。现有20字符规则会接受乱码、水印及流程图伪文本。
本任务不建立正式判定器，也不修改路由。

## 特征选择依据与定义

实现长度、中文/Latin/数字组成、Unicode 类别驱动的 suspicious、常用字符集合
readable、行数/行长和重复行比例。suspicious 捕捉 replacement、异常控制/格式、
私用/未分配、不可打印和扩展 Latin；没有使用乱码黑名单、词典或模型。全部公式与
限制见 `docs/text_quality_feature_analysis.md`。

## 实际分析

样本为 good 4、acceptable 1、bad 7。suspicious>0 和 readable<0.9 各命中4/7
bad 且本样本无非 bad 误报；中文比例<0.7命中6/7 bad。effective<200 或平均行长
<20 在当前样本恰好分开7/7 bad 与5/5非 bad，但样本过小，可能误报合法短页。

## 有区分能力的特征

- suspicious/readable 对扩展 Latin 和控制字符型乱码最直接；
- 中文与 Latin 组成能识别多数大面积乱码；
- 长度与平均行长能提示只有水印/伪文本的风险。

## 无区分能力或不能单独使用的特征

- 中文比例：bad 可为1.0；
- readable：合法水印可为1.0；
- suspicious：纯中文伪文本为0；
- 行数：表格乱码可能产生大量短行；
- 重复行：本样本覆盖很弱；
- 长度：缺少足够合法短文本对照，不能直接定阈值。

## 无法仅靠文本解决的问题

纯文本无法知道原页面主体面积及未提取内容。PQ-005 的“内部收藏”是完全合法中文，
但原封面的标准标题大量缺失；流程图标题同样可能合法。正文覆盖率需要图像或版面
证据，不能由文本特征可靠证明。

## 候选规则

只提出 suspicious>0、readable<0.9、中文比例<0.7，以及“低有效字符且平均行短”
的组合候选。它们未实现质量结论、未重新路由，需在 TASK-002.9.2 扩样并离线评估。

## 新增文件与产物

新增 Git 跟踪文件：

- `src/inspection_plan/document_parser/text_quality.py`
- `scripts/analyze_text_quality_features.py`
- `tests/test_text_quality.py`
- `docs/text_quality_feature_analysis.md`
- `docs/task_logs/TASK-002.9.1.md`

运行产物：`data_processed/evaluation/text_quality_features.json`，受 `.gitignore`
忽略。没有修改已有模块。

## 测试

新增8个测试，只验证计数、空文本、replacement、扩展 Latin、常用中文标点、行结构、
ratio 范围和输入不变，不测试某文本一定 good。

## 人工复核方法

打开特征报告和运行产物，按 sample_id 对照 TASK-002.8 抽检标签与 Page JSONL。
重点复核 PQ-005、PQ-015～017、PQ-020、PQ-021、PQ-025。执行 Git diff 确认
Page、两个 Parser、路由器及20字符阈值没有修改。

## 未实现内容

未实现正式 Text/OCR 判定、Router 接入、OCR fallback/纠错、正文覆盖率检测、
NLP/LLM、Clause、表格/图像分析、检索、服务、数据库、DOCX 或 TASK-002.9.2。
