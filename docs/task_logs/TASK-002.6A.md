# TASK-002.6A：OCR Parser 性能差异诊断

## 任务目标

只诊断 TASK-002.6 整文档 OCR 平均耗时高于 TASK-002.5 单页实验的原因，
不优化生产 Parser、不改变 OCR 结果、不修改 Page Schema，也不实现自动路由。

## 诊断对象

使用 TASK-002.6 的同一份 7 页 PDF：

```text
data/检验规范/34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf
```

环境和参数保持不变：RapidOCR、200 DPI、RGB、`alpha=False`、内存 PNG bytes。

## 实现方法

新增独立脚本 `scripts/diagnose_ocr_parser_performance.py`，复刻生产 Parser 的页面
图像输入链路，并用 `perf_counter` 分别测量：

```text
RapidOCR 初始化
→ PyMuPDF get_pixmap
→ Pixmap PNG 编码
→ RapidOCR 推理
→ Page 构造
→ JSONL 写出
```

诊断计时未进入 Page，也没有修改 `OcrPdfParser`。脚本中的 RapidOCR 构造语句
位于页面循环外，并显式记录构造次数。

## 实测结果

运行日期：2026-08-17。

```text
ocr_init_ms = 360.218
RapidOCR() 实际调用次数 = 1

page 1:
render_ms = 26.705
encode_ms = 53.683
ocr_ms = 2246.563
total_ms = 2327.022

page 2:
render_ms = 37.769
encode_ms = 55.892
ocr_ms = 993.618
total_ms = 1087.369

page 3:
render_ms = 45.539
encode_ms = 94.803
ocr_ms = 6663.187
total_ms = 6803.602

page 4:
render_ms = 39.747
encode_ms = 145.572
ocr_ms = 6185.606
total_ms = 6370.998

page 5:
render_ms = 49.134
encode_ms = 114.762
ocr_ms = 6335.707
total_ms = 6499.678

page 6:
render_ms = 44.049
encode_ms = 92.374
ocr_ms = 3786.310
total_ms = 3922.817

page 7:
render_ms = 49.766
encode_ms = 56.499
ocr_ms = 1981.240
total_ms = 2087.576

jsonl_write_ms = 0.790
total_ms = 29461.093
```

各页 OCR 合计约 28192.231 ms，占整个诊断运行约 95.7%。渲染合计约
292.709 ms，PNG 编码合计约 613.585 ms；JSONL 写出不足 1 ms。

## RapidOCR 初始化与 warm-up

`OcrPdfParser.__init__()` 在页面循环前调用一次 `_create_ocr_engine()`，把结果保存
为 `self._ocr_engine`。`_parse_page()` 只调用该实例，所以生产代码不存在逐页重复
初始化。独立诊断也实际确认 `RapidOCR()` 调用次数为 1。

初始化耗时 360.218 ms，相对于 29.461 秒总耗时较小。第 1 页 OCR 为
2246.563 ms，第 2 页仅 993.618 ms，而第 3～5 页为 6 秒以上。第一次 OCR 并非
最慢，当前数据不支持“首次推理 warm-up 是明显差异来源”的判断。

## TASK-002.5 与 TASK-002.6 输入路径比较

相同点：

```text
zoom = dpi / 72
page.get_pixmap(matrix=Matrix(zoom, zoom), colorspace=csRGB, alpha=False)
→ pixmap.tobytes("png")
→ RapidOCR(png_bytes)
```

因此在同一 PDF、同一页和同一 DPI 下，两者交给 RapidOCR 的图像形式一致，均为
内存 PNG bytes，不存在 TASK-002.5 直接输入 Pixmap、TASK-002.6 先落盘再读取等
路径差异。

不同点：

- TASK-002.5 每次调用 `render_pdf_page` 都重新打开 PDF，并把打开、渲染和 PNG
  编码统一计入 `render_ms`；TASK-002.6 整份文档只打开一次 PDF。
- TASK-002.5 的统计来自 3 份 PDF 的 3 个抽样页、每页 150/200/300 DPI，共 9 次
  OCR，不是当前 7 页文件的全页均值。
- TASK-002.5 初始化一次 OCR 后复用 9 次；TASK-002.6 同样初始化一次后逐页复用。
- 本诊断把 get_pixmap 和 PNG 编码分别统计，因此 `render_ms` 不能直接与
  TASK-002.5 包含编码和 PDF 打开的旧 `render_ms` 数值逐项等同。

## 原因判断

当前同一份 7 页 PDF 复跑总耗时为 29.461 秒，页面阶段平均约 4.157 秒，明显低于
TASK-002.6 首次记录的 71.992 秒。这说明 10.285 秒/页不是该实现稳定必现的基线。

可排除的主要原因：

- 不是每页重复初始化 RapidOCR；
- 不是 JSONL 写出；
- 不是 TASK-002.5 与 TASK-002.6 使用不同的图像格式或输入方式；
- 没有证据表明首次 OCR warm-up 主导差异。

现有证据支持的原因是：OCR 推理本身占绝对多数，并且随页面文字密度、检测框数量
和版面复杂度发生明显波动；TASK-002.5 的少量跨文档抽样均值不能代表这份 7 页
文档。TASK-002.6 首次 71.992 秒还叠加了当时运行环境负载或 ONNX Runtime
运行状态等一次性波动，因为同代码、同文件、同参数的本次复跑未重现该耗时。
在不做更多重复运行和系统级采样的前提下，不能把该波动进一步归因到某个确定的
操作系统因素。

## 运行命令

```powershell
.\.venv\Scripts\python.exe scripts/diagnose_ocr_parser_performance.py
```

运行产物 `data_processed/diagnostics/task_002_6a_pages.jsonl` 受 `.gitignore` 忽略。

## 本任务未实现

- 未修改或优化 `OcrPdfParser`；
- 未改变 DPI、图片格式、OCR 参数或结果拼接；
- 未修改 Page Schema；
- 未引入依赖；
- 未实现并行、缓存、批处理、GPU 或其他性能优化；
- 未实现 TASK-002.7 路由器。
