# TASK-002.1：原始资料文件盘点

## 任务目标

对三类原始资料进行文件级盘点，记录来源目录、相对路径、文件名、扩展名、大小、PDF 页数和基础可读状态，并生成机器可读 JSON 与人工可读 Markdown 报告。本任务不判断 PDF 类型，也不处理正文。

## 输入数据

- `data/检验规范/`：法律、法规、安全技术规范、国家标准和行业标准等 PDF。
- `data/球罐标准/`：球形储罐相关设计、施工、检验和无损检测标准 PDF。
- `data/检验方案/`：历史检验方案 DOCX。

原始文件仅用于读取基础文件元数据和 PDF 页数，脚本不会修改这些文件。

## 实现方法

`scripts/inventory_data.py` 按固定的三个来源目录递归扫描普通文件，统一将扩展名转换为小写，并记录相对于项目根目录的 POSIX 风格路径。PDF 使用项目虚拟环境中已有的 PyMuPDF 打开文档容器并通过 `len(document)` 获取页数；非 PDF 只打开文件并读取一个字节，用于验证基础可读性，不解释文件内容。

每个文件由独立的异常边界处理。单文件读取失败时，记录 `readable=false` 和异常类型摘要，后续文件仍会继续处理。固定来源目录缺失则视为工程输入结构错误并终止，以免生成看似完整但实际缺少整个分类的报告。

## 为什么只统计页数、不读取正文

TASK-002.1 的目标是建立文件级基线。PDF 正文提取会引入文本层质量、扫描件识别、OCR 和版面结构等不同问题，超出本任务边界，也可能让“基础可读”被误解为“正文可解析”。因此实现中不加载 PDF 页面、不调用正文提取 API，也不读取 DOCX 段落或表格。

## 新增/修改文件

新增：

- `scripts/inventory_data.py`
- `tests/test_inventory_data.py`
- `docs/data_inventory.md`
- `docs/task_logs/TASK-002.1.md`
- `data_processed/inventory/data_inventory.json`（运行产物，受 `.gitignore` 忽略）

本任务未修改既有文件。工作区中 `docs/task_logs/TASK-001.md` 的既有修改在本任务开始前已经存在，本任务未触碰该文件。

## 运行命令

```powershell
.\.venv\Scripts\python.exe scripts\inventory_data.py
```

项目虚拟环境已安装 PyMuPDF，无需新增依赖。脚本也支持在正确环境激活后按任务约定运行：

```text
python scripts/inventory_data.py
```

## 实际盘点结果

| 来源目录 | 文件数 | PDF 数 | DOCX 数 | PDF 总页数 |
| --- | ---: | ---: | ---: | ---: |
| 检验规范 | 45 | 45 | 0 | 4300 |
| 球罐标准 | 41 | 41 | 0 | 3154 |
| 检验方案 | 4 | 0 | 4 | 0 |
| 总计 | 90 | 86 | 4 | 7454 |

其他类型文件为 0 个，90 个文件均成功读取本任务要求的基础元数据。

## 异常情况

未发现基础元数据读取异常文件。

## 测试结果

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果为 `5 passed`，覆盖：

1. PDF 页数统计；
2. 扩展名小写归一化；
3. 损坏 PDF 不会中断批处理；
4. 总体与分类 summary 统计；
5. 输出项目相对路径而非本机绝对路径。

测试使用 pytest 临时目录和临时空白 PDF，不依赖真实 `data/` 完成断言。

## 人工验收方法

1. 打开 `data_processed/inventory/data_inventory.json`，确认顶层包含 `summary` 和 `files`，文件路径均以 `data/` 开头。
2. 打开 `docs/data_inventory.md`，核对总体统计、分类统计、90 条文件明细和异常文件章节。
3. 从两个 PDF 来源目录随机选择 3 至 5 个文件，使用常用 PDF 阅读器显示的总页数与 JSON 中的 `pdf_pages` 对比。
4. 分别在三个来源目录统计普通文件数，与 45、41、4 对比。
5. 搜索实现代码，确认不存在 `get_text`、OCR、DOCX 段落或表格解析调用。
6. 重新运行脚本，确认输出统计稳定且不会修改 `data/` 中的文件。

## 本任务未完成内容

- PDF 正文提取及文本层质量检查。
- 扫描版、文本版或混合型 PDF 判断。
- OCR、Page Schema、Clause Parser 和页眉页脚处理。
- DOCX 正文、段落、表格和方案字段分析。
- BM25、Embedding、RAG、LLM、数据库和 FastAPI。
- TASK-002.2 及后续任务。


## 完成结果

## 1. TASK-002.1 完成情况

已完成三类原始资料的文件级盘点，共记录 90 个文件、7454 个 PDF 页面，未发现基础元数据读取异常。

## 2. 实际资料统计

```text
检验规范：
文件数：45
PDF数：45
DOCX数：0
PDF页数：4300

球罐标准：
文件数：41
PDF数：41
DOCX数：0
PDF页数：3154

检验方案：
文件数：4
PDF数：0
DOCX数：4

总计：
文件数：90
PDF数：86
DOCX数：4
PDF总页数：7454
异常文件数：0
```

其他类型文件：0 个。

## 3. 新增文件

- [inventory_data.py](<G:/AIproject/InspectionPlan‌-v1/scripts/inventory_data.py>)：扫描文件、读取 PDF 页数、隔离异常并生成结果。
- [test_inventory_data.py](<G:/AIproject/InspectionPlan‌-v1/tests/test_inventory_data.py>)：包含 5 项单元测试。
- [data_inventory.md](<G:/AIproject/InspectionPlan‌-v1/docs/data_inventory.md>)：人工可读的完整盘点报告。
- [TASK-002.1.md](<G:/AIproject/InspectionPlan‌-v1/docs/task_logs/TASK-002.1.md>)：任务过程记录。
- `data_processed/inventory/data_inventory.json`：机器可读盘点产物，受 `.gitignore` 忽略。

## 4. 修改文件

本任务未修改既有文件。

`docs/task_logs/TASK-001.md` 在本任务开始前已有用户修改，本任务未触碰或覆盖。

## 5. 核心处理流程

```text
扫描目录
→ 识别并归一化文件扩展名
→ 获取文件大小
→ PDF仅读取页数
→ 单文件异常隔离
→ 汇总总体及分类统计
→ 输出JSON
→ 输出Markdown报告
```

PDF 使用项目 `.venv` 已安装的 PyMuPDF，通过 `len(document)` 获取页数，没有加载页面或提取正文。

## 6. 示例 JSON

真实盘点记录：

```json
{
  "source_category": "检验规范",
  "relative_path": "data/检验规范/1.特种设备安全法.pdf",
  "file_name": "1.特种设备安全法.pdf",
  "extension": ".pdf",
  "size_bytes": 539175,
  "pdf_pages": 21,
  "readable": true,
  "error": null
}
```

其中 `readable: true` 只表示本任务要求的基础元数据读取成功，不代表正文可以解析。

## 7. 测试

测试命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
5 passed in 0.08s
```

- 测试数量：5
- 成功数量：5
- 失败数量：0

覆盖 PDF 页数、扩展名归一化、损坏文件容错、summary 汇总和相对路径输出。

## 8. 实际运行命令

使用项目虚拟环境重新生成：

```powershell
.\.venv\Scripts\python.exe scripts\inventory_data.py
```

激活项目虚拟环境后也可以运行：

```text
python scripts/inventory_data.py
```

输出位置：

```text
data_processed/inventory/data_inventory.json
docs/data_inventory.md
```

## 9. 人工复核清单

- 打开 `data_processed/inventory/data_inventory.json`：
  - 确认顶层包含 `summary` 和 `files`；
  - 确认 `files` 有 90 条记录；
  - 确认路径以 `data/` 开头，没有本机绝对路径。

- 打开 [data_inventory.md](<G:/AIproject/InspectionPlan‌-v1/docs/data_inventory.md>)：
  - 核对总体统计和分类统计；
  - 查看完整文件明细；
  - 确认异常章节写明未发现异常。

- 随机选择 3～5 个 PDF：
  - 在常用 PDF 阅读器中打开；
  - 查看阅读器显示的总页数；
  - 与 JSON 中对应记录的 `pdf_pages` 比较。

- 核对目录文件数：

```powershell
(Get-ChildItem "data\检验规范" -File -Recurse).Count
(Get-ChildItem "data\球罐标准" -File -Recurse).Count
(Get-ChildItem "data\检验方案" -File -Recurse).Count
```

预期分别为 `45`、`41`、`4`。

- 确认没有正文解析：

```powershell
rg "get_text|load_page|OCR|paragraphs|tables" scripts tests
```

预期无匹配。

以下现象说明实现存在问题：

- JSON 中出现绝对路径；
- PDF 页数与阅读器明显不一致；
- 单个损坏文件导致整批退出；
- `readable=true` 被解释为正文可解析；
- 出现正文提取、OCR、扫描类型判断或 DOCX 内容分析；
- 脚本修改了 `data/` 中的原始文件。

## 10. Git 状态

`git status`：

```text
On branch main
Changes not staged for commit:
        modified:   docs/task_logs/TASK-001.md

Untracked files:
        docs/data_inventory.md
        docs/task_logs/TASK-002.1.md
        scripts/
        tests/

no changes added to commit
```

`docs/task_logs/TASK-001.md` 是任务开始前已有修改。

`git diff --check` 执行成功，无空白错误。

以下运行产物因 `.gitignore` 不会提交：

```text
data_processed/inventory/data_inventory.json
```

原始 `data/` 也继续保持忽略状态。

## 11. 本任务没有实现什么

- PDF 正文提取
- 文本层质量检查
- 扫描版、文本版或混合型判断
- OCR
- Page Schema
- Clause Parser
- 页眉页脚处理
- DOCX 正文、段落、表格或字段分析
- BM25、Embedding、RAG 或 LLM
- 数据库或 FastAPI
- TASK-002.2 及后续功能

## 12. 下一步

```text
TASK-002.2：PDF 文本层与扫描类型识别
```

## 完成结果

## 1. TASK-002.1 完成情况

已完成三类原始资料的文件级盘点，共记录 90 个文件、7454 个 PDF 页面，未发现基础元数据读取异常。

## 2. 实际资料统计

```text
检验规范：
文件数：45
PDF数：45
DOCX数：0
PDF页数：4300

球罐标准：
文件数：41
PDF数：41
DOCX数：0
PDF页数：3154

检验方案：
文件数：4
PDF数：0
DOCX数：4

总计：
文件数：90
PDF数：86
DOCX数：4
PDF总页数：7454
异常文件数：0
```

其他类型文件：0 个。

## 3. 新增文件

- [inventory_data.py](<G:/AIproject/InspectionPlan‌-v1/scripts/inventory_data.py>)：扫描文件、读取 PDF 页数、隔离异常并生成结果。
- [test_inventory_data.py](<G:/AIproject/InspectionPlan‌-v1/tests/test_inventory_data.py>)：包含 5 项单元测试。
- [data_inventory.md](<G:/AIproject/InspectionPlan‌-v1/docs/data_inventory.md>)：人工可读的完整盘点报告。
- [TASK-002.1.md](<G:/AIproject/InspectionPlan‌-v1/docs/task_logs/TASK-002.1.md>)：任务过程记录。
- `data_processed/inventory/data_inventory.json`：机器可读盘点产物，受 `.gitignore` 忽略。

## 4. 修改文件

本任务未修改既有文件。

`docs/task_logs/TASK-001.md` 在本任务开始前已有用户修改，本任务未触碰或覆盖。

## 5. 核心处理流程

```text
扫描目录
→ 识别并归一化文件扩展名
→ 获取文件大小
→ PDF仅读取页数
→ 单文件异常隔离
→ 汇总总体及分类统计
→ 输出JSON
→ 输出Markdown报告
```

PDF 使用项目 `.venv` 已安装的 PyMuPDF，通过 `len(document)` 获取页数，没有加载页面或提取正文。

## 6. 示例 JSON

真实盘点记录：

```json
{
  "source_category": "检验规范",
  "relative_path": "data/检验规范/1.特种设备安全法.pdf",
  "file_name": "1.特种设备安全法.pdf",
  "extension": ".pdf",
  "size_bytes": 539175,
  "pdf_pages": 21,
  "readable": true,
  "error": null
}
```

其中 `readable: true` 只表示本任务要求的基础元数据读取成功，不代表正文可以解析。

## 7. 测试

测试命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
5 passed in 0.08s
```

- 测试数量：5
- 成功数量：5
- 失败数量：0

覆盖 PDF 页数、扩展名归一化、损坏文件容错、summary 汇总和相对路径输出。

## 8. 实际运行命令

使用项目虚拟环境重新生成：

```powershell
.\.venv\Scripts\python.exe scripts\inventory_data.py
```

激活项目虚拟环境后也可以运行：

```text
python scripts/inventory_data.py
```

输出位置：

```text
data_processed/inventory/data_inventory.json
docs/data_inventory.md
```

## 9. 人工复核清单

- 打开 `data_processed/inventory/data_inventory.json`：
  - 确认顶层包含 `summary` 和 `files`；
  - 确认 `files` 有 90 条记录；
  - 确认路径以 `data/` 开头，没有本机绝对路径。

- 打开 [data_inventory.md](<G:/AIproject/InspectionPlan‌-v1/docs/data_inventory.md>)：
  - 核对总体统计和分类统计；
  - 查看完整文件明细；
  - 确认异常章节写明未发现异常。

- 随机选择 3～5 个 PDF：
  - 在常用 PDF 阅读器中打开；
  - 查看阅读器显示的总页数；
  - 与 JSON 中对应记录的 `pdf_pages` 比较。

- 核对目录文件数：

```powershell
(Get-ChildItem "data\检验规范" -File -Recurse).Count
(Get-ChildItem "data\球罐标准" -File -Recurse).Count
(Get-ChildItem "data\检验方案" -File -Recurse).Count
```

预期分别为 `45`、`41`、`4`。

- 确认没有正文解析：

```powershell
rg "get_text|load_page|OCR|paragraphs|tables" scripts tests
```

预期无匹配。

以下现象说明实现存在问题：

- JSON 中出现绝对路径；
- PDF 页数与阅读器明显不一致；
- 单个损坏文件导致整批退出；
- `readable=true` 被解释为正文可解析；
- 出现正文提取、OCR、扫描类型判断或 DOCX 内容分析；
- 脚本修改了 `data/` 中的原始文件。

## 10. Git 状态

`git status`：

```text
On branch main
Changes not staged for commit:
        modified:   docs/task_logs/TASK-001.md

Untracked files:
        docs/data_inventory.md
        docs/task_logs/TASK-002.1.md
        scripts/
        tests/

no changes added to commit
```

`docs/task_logs/TASK-001.md` 是任务开始前已有修改。

`git diff --check` 执行成功，无空白错误。

以下运行产物因 `.gitignore` 不会提交：

```text
data_processed/inventory/data_inventory.json
```

原始 `data/` 也继续保持忽略状态。

## 11. 本任务没有实现什么

- PDF 正文提取
- 文本层质量检查
- 扫描版、文本版或混合型判断
- OCR
- Page Schema
- Clause Parser
- 页眉页脚处理
- DOCX 正文、段落、表格或字段分析
- BM25、Embedding、RAG 或 LLM
- 数据库或 FastAPI
- TASK-002.2 及后续功能

## 12. 下一步

```text
TASK-002.2：PDF 文本层与扫描类型识别
```