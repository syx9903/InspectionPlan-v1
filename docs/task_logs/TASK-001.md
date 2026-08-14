# TASK-001：初始化 InspectionPlan 项目骨架

## 任务目标

本任务用于在不实现业务算法、不修改原始业务资料的前提下，建立最小且职责清晰的 Python 工程骨架，为后续资料盘点、数据处理、检索和方案生成任务提供统一落点与可追溯记录。

## 修改内容

- 新建 `README.md`，说明项目目标、资料分类、目录结构、当前阶段和能力边界。
- 新建 `data_processed/`，作为未来可重建中间数据的存放位置。
- 新建 `docs/task_logs/` 及本任务记录。
- 新建 `scripts/`，作为未来辅助脚本目录。
- 新建 `src/inspection_plan/` 和包初始化文件 `__init__.py`。
- 新建 `tests/`，作为未来测试目录。
- 保留任务开始前已存在的 `data/` 三类资料目录及全部原始文件。
- 保留任务开始前已存在的 `.gitignore`、`requirements.txt`、`compose.yaml`、`AGENTS.md` 和 `docs/coding_standards.md`，不改写用户已有配置。

## 目录职责

- `data/`：保存原始 PDF/DOCX，程序不得修改原文件。
  - `检验规范/`：法律、法规、安全技术规范、国家标准和行业标准等法规知识源。
  - `球罐标准/`：球形储罐相关设计、施工、检验和无损检测标准，也是法规知识源。
  - `检验方案/`：历史方案样本，用于研究结构、字段、表格和输出模板，不作为主要法规依据。
- `data_processed/`：未来保存由程序生成、可以从原始资料重新构建的数据，不保存本阶段产物。
- `docs/`：保存开发规范、设计说明和任务过程记录。
- `scripts/`：未来保存数据处理、检查或维护入口脚本。
- `src/inspection_plan/`：InspectionPlan Python 源码包；当前仅提供空包入口。
- `tests/`：未来保存自动化测试；本任务不编写无业务意义的测试。

## 关键设计决定

### 原始数据与处理数据分离

`data/` 中的资料是事实来源，需要保持原样以便核对和追溯；`data_processed/` 中的内容应当可以由程序重新生成。分离两者可以避免处理过程覆盖原文件，也便于清理和重建中间结果。

### 历史检验方案不是法规知识源

历史检验方案可能包含特定项目背景、既有表达或过时做法，其主要价值是帮助理解文档结构、固定字段和表格布局。法规结论应以“检验规范”和“球罐标准”中的正式依据为准。

### 当前不引入数据库或业务框架

TASK-001 只定义工程边界，不具备足够的数据模型和业务需求来确定数据库、Web 框架或检索技术。提前实现会固化尚未验证的设计。任务开始前仓库已经存在 `compose.yaml` 和非最小 `requirements.txt`；本任务保留这些用户文件，但不启动数据库、不安装依赖，也不将其视为已实现能力。

### Git 数据策略保持保守

现有 `.gitignore` 已忽略 `data/` 与 `data_processed/`，本任务不擅自改变。原始 PDF/DOCX 往往体积较大，并可能受版权、授权或保密要求约束，通常不宜直接进入普通 Git 历史；中间数据可重建，也通常无需提交。未来 Demo 如需少量 fixture，建议仅提交经过授权、体积受控且脱敏的样本，并通过精确的 `.gitignore` 例外规则纳入，而不是提交完整资料库。

## 未完成内容

- 原始资料盘点与 PDF 类型识别。
- PDF 解析、OCR 和 Clause 结构化。
- BM25、Embedding、混合检索、RAG 和 LLM 调用。
- Evaluation 数据与指标实现。
- InspectionPlan Schema 和 JSON 生成。
- DOCX 模板分析与文档生成。
- FastAPI 服务、数据库及向量数据库。
- 任何法规内容或历史检验方案内容的自动分析。

## 人工验收方法

1. 查看根目录，确认已有文件和三类原始资料均保留。
2. 确认存在 `data_processed/`、`docs/task_logs/`、`scripts/`、`src/inspection_plan/` 和 `tests/`。
3. 打开 `README.md`，核对三类资料职责、数据边界、当前阶段及尚未实现能力。
4. 打开 `src/inspection_plan/__init__.py`，确认只有包说明，没有业务实现。
5. 打开本文件，确认关键设计决定和未完成内容均有记录。
6. 运行 `git status`，确认仅出现 TASK-001 范围内的新文件；由于 Git 不跟踪空目录且 `data_processed/` 已被忽略，部分空目录不会单独出现在状态列表中。
7. 确认没有新增解析器、OCR、检索、API、数据库、DOCX 生成器或无意义测试。


## 完成结果：

## 1. TASK-001 完成情况

已完成最小 Python 工程骨架、基础 README 和任务过程记录，未实现或执行任何业务算法。

## 2. 新增文件

- `README.md`：说明项目目标、资料分类、目录结构、当前阶段和能力边界。
- `docs/task_logs/TASK-001.md`：记录任务目标、修改内容、设计决定、未完成事项和验收方法。
- `src/inspection_plan/__init__.py`：声明 Python 包边界，仅含符合规范的中文模块 Docstring。

同时创建了空目录：

- `data_processed/`
- `scripts/`
- `tests/`
- `docs/task_logs/`
- `src/inspection_plan/`

## 3. 修改文件

无。

以下已有文件均保持不变：

- `AGENTS.md`
- `.gitignore`
- `requirements.txt`
- `compose.yaml`
- `docs/coding_standards.md`
- `data/` 下全部 PDF 和 DOCX

需要注意：现有 `requirements.txt` 在本任务开始前已经包含 FastAPI、数据库、PDF/OCR、Embedding 等依赖。本任务没有新增、安装或使用这些依赖，也不代表对应能力已经实现。

## 4. 当前目录树

未展开 `.git/`、`.venv/` 和大量原始资料文件：

```text
InspectionPlan/
├── .git/
├── .venv/
├── data/
│   ├── 检验规范/
│   │   └── [现有法规、规范及标准 PDF]
│   ├── 球罐标准/
│   │   └── [现有球罐相关标准 PDF]
│   └── 检验方案/
│       └── [现有 4 个历史检验方案 DOCX]
├── data_processed/
├── docs/
│   ├── coding_standards.md
│   └── task_logs/
│       └── TASK-001.md
├── scripts/
├── src/
│   └── inspection_plan/
│       └── __init__.py
├── tests/
├── .gitignore
├── AGENTS.md
├── compose.yaml
├── README.md
└── requirements.txt
```

## 5. 每个目录的职责

- `data`：保存原始 PDF/DOCX，不修改原文件。
- `data_processed`：未来保存可重建的 OCR、JSONL、索引、Evaluation、InspectionPlan JSON 和实验轨迹等。
- `docs`：保存开发规范、设计文档和任务过程记录。
- `scripts`：未来保存可重复执行的处理、检查和维护脚本。
- `src`：保存 InspectionPlan 的 Python 源码。
- `tests`：未来保存自动化测试。

其中：

- `检验规范`和`球罐标准`属于法规知识源。
- `检验方案`用于研究文档结构、固定字段、表格布局和输出模板，不作为主要法规依据。

## 6. 本次关键设计决定

- 原始资料与处理结果分离，防止程序覆盖事实来源。
- 中间数据必须可重建，不与原始文件混放。
- 历史检验方案不能替代正式法规和标准。
- 当前不确定数据模型和业务流程，因此未引入数据库或业务框架。
- 保留现有 Git 策略：`data/` 和 `data_processed/` 均被忽略。
- 原始 PDF/DOCX 通常体积较大，还可能涉及版权或保密要求，不建议直接提交普通 Git。
- 未来如需 Demo fixture，建议仅提交经过授权、脱敏且体积受控的少量样本，并设置精确例外规则。

## 7. 本次没有实现什么

未实现：

- PDF 解析和 PDF 类型识别
- OCR
- Clause 切分
- BM25
- Embedding
- RAG 或 LLM 调用
- Evaluation
- InspectionPlan Schema
- DOCX 生成
- FastAPI
- PostgreSQL 或向量数据库
- 法规及历史方案内容分析
- TASK-002

## 8. 验证结果

目录检查全部通过，Python 文件语法正确且包含模块 Docstring：

```text
syntax=ok
module_docstring=present
```

`.gitignore` 检查：

```text
.gitignore:32:data/             data
.gitignore:38:data_processed/  data_processed
```

`git diff --check` 无输出，未发现空白错误。

当前环境未在 PATH 中发现 pytest，且项目没有测试代码，因此未执行 pytest。

`git status`：

```text
On branch main
Untracked files:
  (use "git add <file>..." to include in what will be committed)
        README.md
        docs/task_logs/
        src/

nothing added to commit but untracked files present
```

`data_processed/`、`scripts/` 和 `tests/` 是空目录；Git 不跟踪空目录，其中 `data_processed/` 还受现有忽略规则约束，因此不会显示在状态列表中。

## 9. 人工复核清单

- 打开 [README.md](<G:/AIproject/InspectionPlan‌-v1/README.md>)，检查资料分类、数据边界和“尚未实现”章节。
- 打开 [TASK-001.md](<G:/AIproject/InspectionPlan‌-v1/docs/task_logs/TASK-001.md>)，检查设计决定、未完成内容和验收方法。
- 打开 [__init__.py](<G:/AIproject/InspectionPlan‌-v1/src/inspection_plan/__init__.py>)，确认只有模块说明，没有业务逻辑。
- 检查 `data/` 下三类资料目录及原文件是否保持不变。
- 检查 `data_processed/`、`scripts/` 和 `tests/` 是否存在。
- 正确结果：只有骨架、文档和空包入口被新增。
- 如果出现 Parser、OCR、检索、API、数据库、DOCX 生成器、业务测试或生成数据，说明本任务做过头了。
- 现有 `requirements.txt` 和 `compose.yaml` 中的提前配置是任务开始前状态，不是本任务新增内容。

## 10. 下一步

`TASK-002：原始资料盘点与 PDF 类型识别`