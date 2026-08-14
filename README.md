# InspectionPlan

InspectionPlan 旨在为压力容器检验方案的资料整理、知识构建与方案生成建立可追溯的工程基础。当前仓库仅完成最小项目骨架，尚未实现任何业务算法。

## 原始资料

原始文件统一保存在 `data/`，程序不得直接修改这些文件。

- `data/检验规范/`：存放法律、法规、安全技术规范、国家标准、行业标准等检验依据 PDF，属于“法规知识源”。
- `data/球罐标准/`：存放球形储罐设计、施工、检验、无损检测等相关标准 PDF，同样属于“法规知识源”；未来与“检验规范”共同进入统一法规知识库。
- `data/检验方案/`：存放历史检验方案 DOCX，用于分析方案结构、固定字段和表格布局，建立未来 InspectionPlan Schema，并为 DOCX 输出模板提供参考。它不是主要法规依据。

## 数据边界

- `data/` 保存原始资料，原文件保持不变。
- `data_processed/` 未来保存程序生成且可重建的数据，例如 PDF Page JSONL、OCR 输出、Clause JSONL、检索索引、Evaluation 输出、InspectionPlan JSON 和实验轨迹。本阶段不创建这些具体数据。

## 当前目录结构

```text
InspectionPlan/
├── AGENTS.md
├── .git/
├── .venv/
├── data/
│   ├── 检验规范/
│   ├── 球罐标准/
│   └── 检验方案/
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
├── compose.yaml
├── README.md
└── requirements.txt
```

## 当前开发阶段

当前处于项目初始化阶段（TASK-001），仅建立目录职责、Python 包入口、基础说明和任务过程记录。仓库中任务开始前已经存在的配置或依赖声明，不代表对应能力已经实现。

## 尚未实现

当前尚未实现 PDF 解析、OCR、Clause 切分、BM25、Embedding、RAG、LLM 调用、DOCX 生成、FastAPI 服务和数据库功能，也未对法规或历史检验方案进行自动分析。
