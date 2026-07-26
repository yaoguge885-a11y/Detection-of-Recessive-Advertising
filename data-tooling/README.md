# data-tooling · 数据工具舱

> 从 `implicit-ad-agent` 代码库中拆出的独立数据工具集。
> 包含：数据 Schema 定义、爬虫脚本、标注工具、合成数据。

---

## 目录结构

```
data-tooling/
├── schema/                          # 数据 Schema 定义
│   ├── data_schema_v1.json          # Schema v1.0
│   └── data_schema_v1_1.json        # Schema v1.1（最新）
├── crawler/                         # 爬虫与采集脚本
│   ├── crawl_public_posts.py        # 公开内容采集
│   ├── crawl_wechat_from_article.py # 从文章链接爬微信内容
│   ├── sogou_wechat_crawler.py      # 搜狗微信爬虫
│   ├── run_full_pipeline.py         # 全流程采集入口
│   ├── html_structure_extractor.py  # HTML 结构提取器
│   ├── llm_image_extractor.py       # LLM 图片提取器
│   └── ollama_extractor.py          # Ollama 本地提取器
├── annotation/                      # 标注工具
│   ├── flet_annotator.py            # Flet 桌面标注器
│   ├── manual_review_annotate.py    # 人工复核标注
│   ├── auto_image_annotate.py       # 自动图片标注
│   ├── multimodal_image_analyzer.py # 多模态图片分析
│   ├── image_prefilter.py           # 图片预筛选
│   ├── apply_image_placement_disposition.py  # 图片位置处置
│   ├── review_image_placement.py    # 图片位置复核
│   ├── validate_schema.py           # Schema 校验
│   ├── normalize_and_deduplicate.py # 归一化与去重
│   ├── privacy_scan.py              # 隐私扫描
│   ├── calculate_agreement.py       # 标注一致性计算
│   ├── build_gold_dataset.py        # 金标数据集构建
│   ├── split_by_blogger.py          # 按博主划分数据集
│   ├── migrate_p1_candidates_to_v1.py  # P1 候选迁移
│   └── report_p1_migration.py       # P1 迁移报告
├── synthetic/                       # 合成数据
│   └── simulated_posts_v1.json      # 模拟帖子 v1
├── build_synthetic_fixture.py       # 合成数据生成脚本
└── validate_submission_assets.py    # 提交资产校验脚本
```

---

## 与 implicit-ad-agent 的关系

- **`implicit-ad-agent/`**：核心 AI Agent 代码库（LangGraph 多智能体、FastAPI 服务、测试）
- **`data-tooling/`**：数据采集、标注、Schema 管理工具（本文件夹）

两者独立维护，通过 Schema 定义和数据格式约定保持兼容。

---

## 使用方式

### 爬虫

```bash
cd data-tooling/crawler
python run_full_pipeline.py
```

### 标注

```bash
cd data-tooling/annotation
python flet_annotator.py
```

### Schema 校验

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe .\data-tooling\annotation\validate_schema.py `
  .\data\interim\dataset_full_candidates_v1.jsonl `
  --target-schema 1.0 `
  --schema .\data\schema\data_schema_v1.json `
  --report .\data\reports\m1\dataset_full_schema_report.json
```

---

## M1 数据就绪工作流

以下命令均从仓库根目录运行。桌面路径只是本地示例；原始数据不会写回，迁移产物位于已忽略的 `data/interim/`，包含 ID 映射的私有报告位于已忽略的 `data/reports/m1/private/`。

```powershell
$DatasetRoot = 'C:\Users\31729\Desktop\dataset_full'
$Python = '.\implicit-ad-agent\.venv\Scripts\python.exe'

# 1. 只读聚合审计
& $Python .\data-tooling\m1_readiness.py audit `
  --dataset-root $DatasetRoot `
  --output .\data\reports\m1\dataset_full_audit.json

# 2. 保守迁移：缺失条款时间保留 null，隐私状态不自动判安全
& $Python .\data-tooling\annotation\migrate_p1_candidates_to_v1.py `
  --input-file "$DatasetRoot\anonymized_postsn.jsonl" `
  --output .\data\interim\dataset_full_candidates_v1.jsonl `
  --id-map .\data\reports\m1\private\dataset_full_id_mapping.json `
  --report .\data\reports\m1\private\dataset_full_migration_report.json `
  --media-base $DatasetRoot `
  --target-schema 1.0 `
  --skip-media-hash

# 3. 严格 Draft 2020-12 Schema 校验
& $Python .\data-tooling\annotation\validate_schema.py `
  .\data\interim\dataset_full_candidates_v1.jsonl `
  --target-schema 1.0 `
  --schema .\data\schema\data_schema_v1.json `
  --report .\data\reports\m1\dataset_full_schema_report.json

# 4. 隐私扫描。没有 --approval-file 时，public 清单必须为空
& $Python .\data-tooling\annotation\privacy_scan.py `
  --input .\data\interim\dataset_full_candidates_v1.jsonl `
  --output-dir .\data\reports\m1 `
  --public-allowlist .\data\reports\m1\public_allowlist.json

# 5. pilot 一致性；不要加 --formal-second-round
& $Python .\data-tooling\annotation\calculate_agreement.py `
  "$DatasetRoot\annotations\D_20260721_121800.json" `
  "$DatasetRoot\annotations\D_20260721_183030.json" `
  --output .\data\reports\m1\trial_agreement.json

# 6. M1 事实门。未达标时退出码为 2，这是预期阻断
& $Python .\data-tooling\m1_readiness.py gate `
  --audit .\data\reports\m1\dataset_full_audit.json `
  --guide .\docs\annotation_guide_v1.md `
  --agreement .\data\reports\m1\trial_agreement.json `
  --dataset-card-status .\data\reports\m1\dataset_card_status.json `
  --output .\data\reports\m1\m1_gate_report.json
```

只有确为指南修订后的第二轮独立盲标，才允许在一致性命令中使用 `--formal-second-round`。公开审批文件必须由人工审查流程产生，格式为 `{"post_ids": [...]}`；不得根据自动扫描结果自行生成批准清单。

---

## 依赖

部分脚本依赖 `implicit-ad-agent` 项目中的可选依赖组：

```bash
# 在 implicit-ad-agent 目录下
pip install -e ".[crawler,annotation,vision]"
```
