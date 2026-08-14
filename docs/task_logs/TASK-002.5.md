# TASK-002.5：OCR 单页最小实验与 OCR 输出评估

## 任务目标

从 TASK-002.2 的 `no_usable_text` PDF 中选取少量真实页面，验证 PyMuPDF 渲染到 RapidOCR 的最小链路，比较 150/200/300 DPI，记录原始输出结构、性能和人工质量问题，为后续 OCR Parser 选择初始参数。

本任务不实现整份 PDF OCR、Page JSONL 或自动路由。

## OCR 引擎

使用项目已有 `rapidocr-onnxruntime 1.4.4`，底层为 `onnxruntime 1.28.0`。没有新增 PaddleOCR、Tesseract 或其他 OCR 引擎。

当前受控沙箱会拒绝加载 ONNX Runtime 原生 PYD；在沙箱外使用相同 `.venv` 可以正常导入和推理。因此真实实验经授权在沙箱外执行，自动测试通过 mock 避免依赖原生推理结果。

## 样本选择

| 样本 | 来源文件 | 页码 | 类型 |
| --- | --- | ---: | --- |
| A | 34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf | 3 | 普通连续中文正文 |
| B | 23.GB／T25198-2023-压力容器封头.pdf | 20 | 条款编号、列表、印章和水印 |
| C | GBT 17261-2011 钢制球形储罐型式与基本参数.pdf | 4 | 多图、多标签复杂页面 |

三份 PDF 在 TASK-002.2 中均为 `no_usable_text`。只处理上述 3 页，没有 OCR 其他页面。

## 页面渲染

使用 PyMuPDF：

```text
1-based page_no → page_no - 1
zoom = dpi / 72
RGB Pixmap，alpha=false
PNG bytes 内存传递给 RapidOCR
```

对每页测试 150、200、300 DPI。实验图片不写入 `data/`；仅保存三个样本的 200 DPI 预览到被忽略的 `data_processed/ocr_experiments/` 供人工核对。

## 分辨率实验

共运行 9 次 OCR。完整逐项结果见 `docs/ocr_single_page_evaluation.md`。

| DPI | 平均 render_ms | 平均 OCR_ms | 平均 total_ms | 平均字符数 |
| ---: | ---: | ---: | ---: | ---: |
| 150 | 104.8 | 2892.5 | 2997.3 | 452.0 |
| 200 | 160.0 | 2944.9 | 3104.9 | 448.7 |
| 300 | 246.1 | 2855.1 | 3101.2 | 433.3 |

200 DPI 被选为当前 baseline。300 DPI 没有稳定质量提升，样本 B 反而漏掉 `9.2` 主体行；150 DPI 已具备可读性，但 200 DPI 为小字号留出适度余量，同时显著低于 300 DPI 像素规模。

## OCR 输出结构

RapidOCR 返回 `(result, elapse_list)`：

- `result`：按引擎顺序的 `[bounding_box, text, confidence]`；
- `elapse_list`：检测、方向分类和识别阶段耗时。

脚本将每行转换为 JSON 兼容的：

```json
{"box": [[0, 0], [10, 0], [10, 5], [0, 5]], "text": "示例", "confidence": 0.98}
```

每次实验的完整行结果、拼接正文、尺寸和性能保存在 `data_processed/ocr_experiments/*_raw_ocr.json`。

## 文本拼接 baseline

只保持 OCR 返回顺序并使用换行连接 `text`。没有阅读顺序恢复、双栏重排、表格恢复、页眉页脚删除或 Clause 拼接。

## 性能数据

9 次实验总体平均：

```text
render_ms = 170.3
ocr_ms    = 2897.5
total_ms  = 3067.8
```

数据不含 RapidOCR 模型初始化，仅用于当前机器的量级判断。连续正文页约 5 秒，复杂图示但文字较少的页面约 1.5 秒。

## 人工质量观察

- 普通中文正文整体可读，但低频字和姓名仍可能错误。
- 条款号 `8.2/9.1/9.2` 在 150/200 DPI 较稳定；300 DPI 在样本 B 漏掉 `9.2` 主体内容。
- 标准号中的破折号、短横线和汉字“一”容易混淆。
- 列表的英文/中文括号可能混用或与正文拆行。
- 页码、印章和公众号水印会进入结果。
- 图示中存在“桔瓣→桔舞”“上温带→上湿带”“下温带→F温带”等错误。
- 图示标签的返回顺序无法恢复其与具体图形的二维关系。

## 新增/修改文件

新增：

- `scripts/evaluate_single_page_ocr.py`
- `tests/test_single_page_ocr_evaluation.py`
- `docs/ocr_single_page_evaluation.md`
- `docs/task_logs/TASK-002.5.md`
- `data_processed/ocr_experiments/` 下 9 个 OCR JSON、3 个 200 DPI 样本图及候选预览（均受 `.gitignore` 忽略）

本任务未修改 Page Schema、TextPdfParser 或其他既有源码。

## 自动测试

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果为 `49 passed`：原有 37 个案例，本任务新增收集 12 个案例。覆盖非空渲染、非法页码、DPI 校验、OCR 结果 JSON 化、顺序拼接、空结果和 mock 完整实验。

## 已知问题

- 小样本没有人工逐字 Gold，无法计算准确率。
- OCR 置信度不能保证法规数字、标准号和条款编号正确。
- 200 DPI 只是当前 baseline，不保证适合所有页面。
- 大面积印章、图示、表格和二维标签关系仍不可靠。
- 沙箱内无法加载当前 ONNX Runtime 原生模块，真实推理需要允许在沙箱外运行。

## 人工复核方法

1. 打开 `docs/ocr_single_page_evaluation.md`，核对样本、9 行 DPI 对比、典型错误和 baseline 决定。
2. 查看 `data_processed/ocr_experiments/*_raw_ocr.json`，重点检查 `raw_ocr`、`text`、置信度与耗时字段。
3. 打开三个 200 DPI PNG 与原 PDF 对应页，对照正文、条款编号、标准号、列表标点及图示标签。
4. 对样本 B 检查 `8.2/9.1/9.2`，对样本 A 检查 `47018.1/2017/2009/2011`，对样本 C 检查图号和 A～G 标签。
5. 如果更高 DPI 稳定补回遗漏内容且没有明显增加错识别，才有理由提高 baseline；本次数据不支持选择 300 DPI。
6. 运行 pytest，确认无需真实模型推理的辅助逻辑稳定。

## 未实现内容

- 批量 OCR 3772 页或整份 PDF OCR Parser。
- OCR Page、Page JSONL 和 mixed PDF 自动路由。
- 表格/双栏/图示结构恢复、页眉页脚过滤和自动纠错。
- Clause Parser、LLM 纠错、BM25、Embedding、RAG。
- 数据库、FastAPI、DOCX 和 TASK-002.6。
