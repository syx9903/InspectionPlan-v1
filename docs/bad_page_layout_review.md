# bad Page 版面类型人工复核

## 1. 任务目的

TASK-002.9.1 证明纯文本特征能发现部分乱码，却无法判断原页正文覆盖率。本次在
建立文本质量判定前，逐页确认14个 bad Page 究竟是普通文本提取失败，还是表格、
流程图、图示等二维结构无法由单一 `Page.text` 表达。复核只分类和统计，不实现
自动 Layout Detection，不修改已有质量标签或解析链。

## 2. bad Page 样本

| parse_method | bad Page 数 |
| --- | ---: |
| text | 7 |
| ocr | 7 |
| 合计 | 14 |

所有标签均逐一对照 TASK-002.8 生成的120 DPI原 PDF 页面图像及 Page JSONL。
标注属于人工工程判断，`annotations_are_user_confirmed=false`，不是正式 Gold。

## 3. 版面类型定义

- `plain_text`：连续正文或普通条款，核心内容可以线性阅读。
- `table`：主体依赖行、列、单元格对应关系。
- `flowchart`：主体依赖设备/流程节点、箭头、分支和连接关系。
- `figure`：设备结构图、工程图或带位置标签的示意图。
- `mixed_layout`：正文与表格/图形等多种重要区域并存。
- `cover`：标准号、名称、机构和日期等元数据为主要价值的封面/首页。
- `other`：无法归类时使用并必须说明；本次没有使用。

失败类别：

- `text_quality`：原页适合线性文本，失败来自乱码、错字或缺失。
- `layout_structure`：文字识别基本可用，但二维结构必然丢失。
- `both`：文字质量和二维结构同时失败。
- `metadata_only`：主要影响封面元数据，而非 Clause 正文。
- `other`：无法归类；本次没有使用。

## 4. 逐页复核结果

| sample_id | parse_method | layout_type | failure_category | linear text sufficient | notes |
| --- | --- | --- | --- | --- | --- |
| PQ-005 | text | cover | metadata_only | true | 标准封面，只提取到收藏水印；完整文字可线性保存元数据。 |
| PQ-012 | ocr | mixed_layout | layout_structure | false | 正文与大表格并存，材料类型和检验项目关系丢失。 |
| PQ-014 | ocr | figure | both | false | 六个球罐示意图，标签错字且位置对应关系丢失。 |
| PQ-015 | text | table | both | false | 表A.3～A.5，文本乱码且行列关联丢失。 |
| PQ-016 | text | table | both | false | 表A.5续表，乱码且单元格关系丢失。 |
| PQ-017 | text | plain_text | text_quality | true | 附录B标题和说明段落，失败来自文本层乱码。 |
| PQ-018 | ocr | flowchart | both | false | 常减压蒸馏流程图，数字错误且管线关系丢失。 |
| PQ-019 | ocr | flowchart | both | false | 乙烯裂解流程图，标签错字且设备连接丢失。 |
| PQ-020 | text | flowchart | both | false | Shell煤气化流程图，只提取到伪文本、页码和水印。 |
| PQ-021 | text | flowchart | both | false | Texaco煤气化流程图，主体文本和连接关系缺失。 |
| PQ-022 | ocr | flowchart | both | false | CO变换流程图，标签/编号错误且二维关系丢失。 |
| PQ-023 | ocr | flowchart | both | false | 变换气净化流程图，文字失真且流程连接丢失。 |
| PQ-024 | ocr | flowchart | both | false | 减粘装置流程图，标引序号和设备关系丢失。 |
| PQ-025 | text | plain_text | text_quality | true | 附录C连续正文，原版面可线性表达但文本层乱码。 |

## 5. 版面类型统计

| layout_type | 数量 | 比例 |
| --- | ---: | ---: |
| flowchart | 7 | 50.0% |
| table | 2 | 14.3% |
| plain_text | 2 | 14.3% |
| figure | 1 | 7.1% |
| mixed_layout | 1 | 7.1% |
| cover | 1 | 7.1% |
| other | 0 | 0.0% |

`table + flowchart + figure + mixed_layout` 共11页，占78.6%，统一称为本报告中的
structured layout pages。该名称只用于统计，没有修改 Page 模型。

## 6. 文本问题 vs 版面问题

| failure_category | 数量 | 比例 |
| --- | ---: | ---: |
| both | 10 | 71.4% |
| text_quality | 2 | 14.3% |
| layout_structure | 1 | 7.1% |
| metadata_only | 1 | 7.1% |
| other | 0 | 0.0% |

按解析方式：

| parse_method | text_quality | layout_structure | both | metadata_only |
| --- | ---: | ---: | ---: | ---: |
| text | 2 | 0 | 4 | 1 |
| ocr | 0 | 1 | 6 | 0 |

OCR bad 页全部涉及结构问题；Text bad 页既有2个普通正文乱码，也有4个复杂版面
同时伴随文本提取失败。

## 7. 表格问题

严格 `table` 为2页，占14.3%。若把正文与表格并重的 PQ-012 `mixed_layout` 计入
表格相关页，则为3页，占21.4%。

- PQ-015、PQ-016 来自 mixed PDF 的表格页，已有文本层发生乱码，且行列关系丢失。
- PQ-012 走 OCR，普通条款文字基本可读，但表2的材料类别与检验项目对应关系无法
  保存在一段线性文本中。

主要失败不仅是字符识别；即使单元格文字100%正确，也需要显式行列结构。

## 8. 流程图和图示问题

流程图7页，占50.0%，是最大单一版面类型。它们依赖设备、管线、箭头、标引数字
之间的空间关系。当前 Text/OCR 可以零散得到标签，却不能恢复连接关系。

球罐示意图1页，占7.1%。其核心是“上极/温带/赤道带”等标签与六个球罐图形位置
的对应；线性 OCR 文本无法区分标签属于哪一幅图。

另有1个 mixed_layout 页面同时包含普通条款和主体表格，两部分都影响理解。

## 9. linear_text_sufficient 分析

```text
true：3
false：11
```

false 占78.6%，表示即使文字全部正确识别，单一从上到下的 `Page.text` 仍不足以
表达页面核心信息。true 的3页是2个普通正文乱码页和1个封面元数据页。

## 10. 是否需要 Table/Layout Parser

有足够证据支持后续研究独立的复杂版面处理路线，但证据更支持**通用 Layout
路线**，而不是只增加 Table Parser：

- 严格表格仅14.3%，表格相关页最多21.4%；
- 流程图单独占50.0%；
- 加上图示和 mixed_layout，结构化版面占78.6%；
- 11页即使字符完全正确也无法由线性文本充分表达。

该结论基于刻意选择的14个 bad 样本，用于确认失败类型存在和确定实验优先级，
不能外推为7454页的版面比例。普通 Text 乱码仍需后续处理，但当前失败样本中复杂
版面问题更突出。

## 11. 人工复核方法

1. 打开 `data_processed/evaluation/bad_page_layout_review.json` 查看14条复核记录。
2. 用 `sample_id` 对应 `data_processed/evaluation/page_quality_images/` 中的 PNG。
3. 用 `relative_path/page_no` 打开原 PDF 同页。
4. table 看信息是否依赖行列；flowchart 看是否依赖箭头/连接；figure 看标签是否依赖
   图形位置；mixed_layout 看两种结构是否都影响理解。
5. 对 `linear_text_sufficient=false` 假设所有字符均正确，再判断删除坐标和连接后是否
   仍能表达核心信息。
6. JSON 元数据明确记录人工评审依据及 `automatic_layout_detection_used=false`。
