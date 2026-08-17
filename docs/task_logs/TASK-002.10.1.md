# TASK-002.10.1 过程记录

## 1. 任务背景

TASK-002.9.2A确认14个bad Page中11页（78.6%）属于广义复杂版面，且11页无法由
线性文本充分表达。本任务通过4页最小实验区分Layout Detection、表格结构恢复、
流程关系理解和图示理解，不实现正式Parser。

## 2. 复杂版面统计

- flowchart：7
- table：2
- figure：1
- mixed_layout：1
- 广义复杂版面：11/14
- `linear_text_sufficient=false`：11/14

## 3. 候选技术与选型

比较PP-StructureV3、Docling和MinerU。仅实际运行已有的PP-StructureV3；Docling和
MinerU作为官方能力及工程成本对照，没有继续安装新的重型依赖。

## 4. 环境检查

- Python 3.12.10，Windows。
- `pyproject.toml`不存在。
- 已安装PaddleOCR 3.7.0、PaddlePaddle 3.3.1、PaddleX 3.7.2、RapidOCR、PyMuPDF。
- Docling、MinerU未安装。

## 5. 样本

- PQ-015：table，原PDF第119页。
- PQ-018：flowchart，原PDF第122页。
- PQ-014：figure，原PDF第4页。
- PQ-012：mixed_layout，原PDF第6页。

输入使用TASK-002.8已有120 DPI页面PNG，避免引入新的渲染差异。

## 6. 实验方法

`scripts/evaluate_layout_baselines.py`只完成：固定样本定位、初始化一次
PP-StructureV3、逐页推理、保存raw JSON/可视化/summary、记录耗时。自动摘要只
统计可观察的block标签和table数量，模型质量由人工对照原页判断。

运行命令：

```powershell
$env:PADDLE_PDX_MODEL_SOURCE='bos'
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True'
.\.venv\Scripts\python.exe scripts\evaluate_layout_baselines.py
```

## 7. 实际结果

- PQ-015：正确检测3张4列表，HTML行为12、12、3；数字标引存在OCR错误。
- PQ-018：只检测为整体image，没有箭头、节点边或分支关系。
- PQ-014：检测6个image和6个图题，不保留标签到部位的关系。
- PQ-012：正文/表格分区及阅读顺序基本正确；HTML保留rowspan/colspan。
- 4页raw JSON的中文OCR均出现乱码，不能直接作为生产文本。

## 8. 安装与运行问题

没有安装新Python包。首次默认运行在模型源探测阶段超过10分钟；指定BOS后完成
模型下载，但默认oneDNN在PP-DocLayout推理触发PIR Attribute未实现异常。使用
PaddleOCR公开参数 `enable_mkldnn=False` 后4页成功。成功运行的预测耗时约47～185秒/页。

## 9. 工程结论

不开发统一Layout Parser。表格优先继续PP-StructureV3 Table路线；mixed_layout
按区域分工；流程图和figure保留原图及人工风险标记。检测到image不等于理解结构。

## 10. 新增与修改

新增：

- `scripts/evaluate_layout_baselines.py`
- `tests/test_layout_baseline_evaluation.py`
- `docs/layout_baseline_evaluation.md`
- `docs/task_logs/TASK-002.10.1.md`

运行产物位于被Git忽略的 `data_processed/layout_experiments/`。没有修改Page
Schema、PdfPageRouter或现有Parser。`requirements.txt`在任务开始前已有未提交修改，
本任务没有改动它。

## 11. 测试与人工复核方法

自动测试验证固定样本类型、sample_id、页码、缺失文件、耗时结构、原始输出摘要和
UTF-8 JSON写出，不固定外部模型文字。人工复核详见主报告第13节。

## 12. 未实现内容

未实现正式Layout/Table Parser、流程关系恢复、figure语义、Schema/Router接入、
生产JSONL、OCR乱码修复、全库批处理、Docling/MinerU实测或TASK-002.10.2。
