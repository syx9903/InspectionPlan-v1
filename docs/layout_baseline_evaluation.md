# TASK-002.10.1 复杂版面技术 baseline 实验报告

## 1. 为什么需要复杂版面路线

TASK-002.9.2A 对14个 bad Page 的人工复核表明，表格、流程图、图示和混合版面
共11页，占78.6%；同样有11页的 `linear_text_sufficient=false`。因此提高普通
Text Quality 或重复执行线性 OCR，无法恢复这些页面的二维结构与关系。

## 2. 候选技术

| 技术 | 主要用途 | 表格能力 | 普通 layout | 流程图 / figure | 本次处理 |
|---|---|---|---|---|---|
| PP-StructureV3 | Layout、OCR、表格、阅读顺序 | 可输出表格 HTML 和单元格框 | 强 | 可检测 image，但不恢复箭头或几何语义 | 实际运行 |
| Docling | 文档层级、阅读顺序、表格结构 | TableFormer 可恢复行列 | 强 | Picture 仍不等于流程关系理解 | 仅技术调研 |
| MinerU | PDF 转 Markdown/JSON、Layout、表格 | 可启用表格解析与 HTML 输出 | 强 | 仍以图像区域为主 | 仅技术调研 |

官方资料显示，PP-StructureV3强调 Layout Detection、表格识别、阅读顺序和
Markdown；Docling 的统一文档对象包含 Text、Table、Picture、边界框和 body 阅读
顺序；MinerU提供 Layout、阅读顺序及表格输出。三者的文档都不能证明其能恢复
本项目流程图的箭头、分支和设备连接语义。

参考资料：

- [PP-StructureV3 使用文档](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html)
- [Docling Document 数据结构](https://docling-project.github.io/docling/concepts/docling_document/)
- [Docling Table Structure 配置](https://docling-project.github.io/docling/usage/advanced_options/)
- [MinerU CLI 文档](https://github.com/opendatalab/MinerU/blob/master/docs/en/usage/cli_tools.md)

## 3. 实验样本

| sample_id | layout_type | page_no | 原 PDF |
|---|---|---:|---|
| PQ-015 | table | 119 | `data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf` |
| PQ-018 | flowchart | 122 | `data/检验规范/29.GBT_30579-2022_承压设备损伤模式识别.pdf` |
| PQ-014 | figure | 4 | `data/球罐标准/GBT 17261-2011 钢制球形储罐型式与基本参数.pdf` |
| PQ-012 | mixed_layout | 6 | `data/检验规范/34.NB T 47018.1-2017 承压设备用焊接材料订货技术条件 第1部分：采购通则.pdf` |

输入沿用 TASK-002.8 的120 DPI页面 PNG，四个 sample_id、原 PDF 相对路径及页码
均保持不变。这样可以把本次差异限定在版面技术，而不是 PDF 渲染差异。

## 4. 环境和实际运行

- Python 3.12.10，Windows，CPU 推理。
- 已有：PaddleOCR 3.7.0、PaddlePaddle 3.3.1、PaddleX 3.7.2、RapidOCR、PyMuPDF。
- 未安装：Docling、MinerU。
- 首次默认初始化因模型源连通性探测超过10分钟，0页完成。
- 指定官方 BOS 模型源后模型成功下载，但默认 oneDNN 路径在首样本触发
  `ConvertPirAttribute2RuntimeAttribute` 未实现异常。
- 使用 PaddleOCR 公开参数 `enable_mkldnn=False` 切回标准 Paddle CPU 执行器后，
  4页全部运行成功。该配置没有改变模型、输入或后处理规则。

Docling 和 MinerU 都会增加另一套重型依赖及模型下载。本任务已有一个可运行真实
baseline，且两个对照方案也不会天然恢复流程图语义，因此没有继续安装。

## 5. 实验结果总览

| 样本 | 技术 | 区域检测 | OCR | 表格结构 | 阅读顺序 | 流程关系 | predict_ms |
|---|---|---|---|---|---|---|---:|
| PQ-015 | PP-StructureV3 | 正确检出3个table | raw中文乱码 | 3份HTML，行列正确 | 页面顺序合理 | 不适用 | 184945.379 |
| PQ-018 | PP-StructureV3 | 整体检为image | raw中文乱码 | 不适用 | 仅图片级顺序 | 未恢复 | 118113.026 |
| PQ-014 | PP-StructureV3 | 6个image及6个图题 | raw中文乱码 | 不适用 | 图块顺序合理 | 标签关系未恢复 | 46975.328 |
| PQ-012 | PP-StructureV3 | 正文/table分区正确 | raw中文乱码 | 1份HTML，含合并单元格 | 基本正确 | 不适用 | 101324.852 |

管线初始化为2841.938 ms。保存 raw、summary 和可视化分别约为8954.669、464.803、
367.362、516.166 ms。以上是单次 CPU baseline，不是正式性能基准。

## 6. table 结果：PQ-015

- 3个表格区域全部检出，置信度约0.98～0.99。
- 三张表分别输出12、12、3行，每行4个单元格；与页面可见结构一致。
- 输出含 `pred_html`、`cell_box_list` 和 `table_ocr_pred`，具备二维结构基础。
- 该页没有需要验证的合并单元格。
- 章节号 `7.6`～`9.2` 的列位置基本正确，但最后一列的圈号/标引数字有多处
  OCR错误，不能因为行列正确就认为法规数字可靠。
- raw JSON 的中文为乱码，当前不能直接作为结构化正文使用。

结论：PP-StructureV3适合作为 Table Parser 的首选 baseline，但必须先解决中文
输出编码/识别质量并建立数字列人工核验规则。

## 7. flowchart 结果：PQ-018

- 页面主体只检测为一个大的 `image`，没有独立识别流程节点框。
- 没有输出箭头、设备连接、顺序边或 yes/no 分支。
- 图内部分文字进入 image block OCR，但最终仍是无结构文本。
- `layout_order_res` 只表达页面块顺序，不表达工艺流向。

结论：Layout Detection 成功不等于流程图理解成功。PP-StructureV3不能独立承担
流程关系恢复，流程图应保留原图和人工复核风险标记。

## 8. figure 结果：PQ-014

- 正确分出6个球罐 `image` 区域及对应6个 `figure_title`。
- 图内“上极、赤道带、A/B/C”等文字可以作为 image block 内容被OCR。
- 输出没有标签锚点到球罐部位的关系，也没有球罐结构语义。
- 图示最可靠的产物仍是原始图片区域，而不是自动结构化对象。

结论：适合做 figure 区域保留和图题关联，不适合自动生成设备结构事实。

## 9. mixed_layout 结果：PQ-012

- 正确分出页眉、正文、表题、表格和后续正文。
- 阅读顺序从第6章正文到表2，再到第7章正文，人工观察基本正确。
- 表格输出9个HTML行，包含 `rowspan` 3处、`colspan` 2处，说明合并单元格
  结构得到保留；各行实际 cell 数因合并关系不同，符合复杂表结构特征。
- OCR原始中文仍为乱码，所以布局分区可用不代表内容已可直接使用。

结论：PP-StructureV3适合作为 mixed_layout 的区域分割与表格抽取 baseline，普通
正文仍应优先复用现有 Text/RapidOCR，而不是无条件替换。

## 10. 工程复杂度

| 项目 | PP-StructureV3 | Docling | MinerU |
|---|---|---|---|
| 安装状态 | 已安装并实际运行 | 未安装 | 未安装 |
| 依赖/模型 | PaddleOCR/PaddleX，多模型，重 | Torch及多个文档模型，重 | 多模型/后端，重 |
| Windows | 可运行，但需关闭当前不兼容的oneDNN路径 | 官方支持，未在本机验证 | 支持Windows，GPU配置复杂 |
| CPU | 可运行，单页约47～185秒 | 可CPU，未实测 | 可CPU pipeline，未实测 |
| 表格结构 | 本样本有效 | 官方支持 | 官方支持 |
| 流程关系 | 不支持 | 无证据支持 | 无证据支持 |

PP-StructureV3首次还需要约百MB到数百MB级的多个模型文件；完整管线内存和初始化
成本显著高于现有RapidOCR，不适合对所有普通页面无条件执行。

## 11. 最终 baseline 建议

- 普通正文：继续现有 Text / RapidOCR 路线，合理。
- 表格：优先继续验证 PP-StructureV3 的 Table 路线；重点补充中文输出、合并单元格、
  数字列错位和精度评价。
- 流程图：当前无可靠自动关系恢复方案；保留图片、OCR辅助文字和人工风险标记。
- 图示：只自动检测/裁剪区域并关联图题，不把图内标签生成结构化事实。
- mixed_layout：使用 Layout Detection 分区；正文复用现有解析，表格交给专用表格链路。

## 12. 是否应该立即开发统一 Layout Parser

**不应该。选择 C：按 table / flowchart / figure 分类处理。**

一个统一 Parser 会掩盖能力差异：表格已经能获得行列结构；普通 mixed layout 能
恢复大致阅读顺序；流程图和图示却仍只有图片级区域，不能恢复业务关系。近期最小
收益路线是只继续 Table baseline，并为 flowchart/figure 保留人工复核风险。

## 13. 产物位置与人工复核

每个样本产物位于：

```text
data_processed/layout_experiments/<sample_id>/paddle/
├── raw.json
├── summary.json
└── visualizations/
```

人工验收时：

1. 对照 `input_metadata.relative_path` 和 `page_no` 打开原PDF。
2. 查看 `layout_det_res.png`，确认区域边界和标签。
3. 查看 `layout_order_res.png`，确认普通正文顺序。
4. 对表格检查 `raw.json` 的 `pred_html`、`rowspan`、`colspan` 和
   `cell_box_list`，不能只看OCR文字。
5. 对流程图检查是否存在箭头边和分支结构；本次不存在，不能称为解析成功。

## 14. 已知限制

- 只有4页，不能推断全库准确率。
- 只实际运行一个候选；Docling和MinerU结论来自官方能力边界，不是本机质量实测。
- raw JSON中文OCR出现乱码，原因和修复不属于本任务。
- 未验证GPU、并发、模型量化或性能优化。
- 人工观察不是正式Gold标注。

