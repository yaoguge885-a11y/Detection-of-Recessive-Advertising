# 合并历史基线设计

## 1. 状态与目标

本文档记录 2026-08-08 已批准的独立论文基线设计。目标是在根目录
`baseline/` 建立一个与 Agent 运行主图隔离、可复现且默认 fail-closed 的三分类
实验包，固定比较以下四种输入：

1. `single_post`：仅目标帖特征；
2. `history_mean`：目标帖特征与历史 mean 池化向量拼接；
3. `history_max`：目标帖特征与历史 max 池化向量拼接；
4. `history_ema`：目标帖特征与按时间顺序计算的 EMA 向量拼接。

四种方法使用相同的目标样本、相同历史窗口、相同分类器类型和相同固定超参，
从而把差异限制在历史聚合方式本身。

当前 M1 gate 未通过，正式 Gold 为 0，creator/content-group 无泄漏划分也不存在。
因此本轮交付的是完整工程基线与合成夹具验证，不产出真实论文指标，也不宣称
CreatorShift 增益或 M4 通过。

## 2. 范围边界

### 2.1 包含

- 独立 `baseline/` Python 包、依赖文件、CLI、合成夹具和测试；
- content、Gold、split、M1 gate 及 split report 的严格加载和交叉校验；
- 防未来泄漏的历史解析与共同完整 cohort 构建；
- 固定六维 `keyword_weights_v1` 特征；
- mean、max、EMA 三种历史池化；
- scikit-learn 多分类 Logistic Regression；
- 聚合指标、方法差值、输入与配置哈希及研究声明边界；
- 当前状态文档和测试指令同步。

### 2.2 不包含

- 修改 `implicit-ad-agent` 的 LangGraph、Judge、CreatorShift 节点或线上 API；
- 使用自动/Qwen 建议代替正式人工 Gold；
- 在 M1 未通过时训练正式模型或发布真实 F1、增益、置信区间；
- 学习型 CreatorShift、视觉编码器、序列模型、XGBoost 或超参搜索；
- 自动生成正式 train/dev/test split；正式实验只消费已经审计通过的划分；
- 把合成夹具结果解释为研究效果。

## 3. 方案选择

采用 scikit-learn `LogisticRegression`，不自行实现 NumPy softmax。成熟实现更容易
审计，且能稳定提供三分类概率。scikit-learn 仅写入 `baseline/requirements.txt`，
不加入 Agent 主环境依赖。

不采用 feature-only 作为最终交付，因为它不能完成分类基线；但在正式数据门未通过
时，CLI 仍允许运行显式 `synthetic` 模式来验证完整训练、预测和报告链。所有合成报告
必须包含 `research_claims_allowed=false`。

## 4. 架构

```text
content JSONL ─┐
Gold JSONL ────┼─> 输入校验与 post_id join ─> 历史解析 ─> 共同完整 cohort
split IDs ─────┤                                      │
split report ──┤                                      ▼
M1 gate ───────┘                        keyword_weights_v1
                                                       │
                         ┌─────────────────────────────┼──────────────┐
                         ▼                             ▼              ▼
                    single_post                  mean / max          EMA
                         │                             │              │
                         └──────── 固定分类器与超参 ──┴──────────────┘
                                                       │
                                                       ▼
                                      聚合指标、差值、哈希与边界报告
```

`baseline/` 不导入 Agent 图、服务、LLM 或工具网关。六维特征规则在基线包中固定版本，
并通过等值测试与当前 `keyword_weights_v1` 语义保持一致；这是论文对照实现，不改变
Agent 侧唯一运行路径。

## 5. 输入契约

### 5.1 正式模式

CLI 必须接收：

- Schema v1.2 content JSONL；
- `build_gold_dataset.py` 生成的正式 Gold JSONL；
- train、dev、test 三份 post ID 文件；
- split report JSON；
- `m1_gate_report.json`；
- 输出报告路径；
- 评估 split，默认只能是 `dev`。

Gold 与 content 通过 `post_id` 一对一连接。每个 Gold ID 必须恰好存在于 content，
且标签只能是 `明广`、`暗广`、`非广`。`uncertain`、`out_of_scope`、自动接受、
系统标注、单人重复标注或缺失标签不得进入正式输入。

train/dev/test 必须互不相交，并且恰好覆盖全部 Gold ID 一次。split report 必须证明：

- `post_leakage_count == 0`；
- `creator_leakage_count == 0`；
- `content_group_leakage_count == 0`；
- `near_duplicate_leakage_count == 0`；
- 近重复检查不是缺失状态；
- 每个 split 均至少包含三种正式标签。

M1 gate 的顶层 `passed` 必须为 `true`。缺文件、缺字段、指纹不一致或任何检查失败均
在训练前以非零状态退出。

### 5.2 合成模式

合成模式只读取 `baseline/tests/fixtures/` 中版本化的无真实内容夹具。它可以绕过
M1 gate 以验证工程链，但报告必须同时满足：

- `mode="synthetic"`；
- `research_claims_allowed=false`；
- `dataset_kind="synthetic_fixture"`；
- 不出现原始正文、URL、creator ID、annotator ID 或 post ID 列表。

## 6. 历史解析与共同 cohort

`blogger_history_refs` 只被解释为 post ID 引用。每个被采用的历史项必须：

- 在 content 中存在且只出现一次；
- 与目标帖 `blogger_id` 相同；
- 不是目标帖本身；
- 具有时区明确的 `published_at`；
- 严格满足 `history.published_at < target.published_at`；
- 在同一目标帖历史中不重复。

最小历史数固定为 3。目标时间缺失、历史引用缺失、跨 creator、未来/同时间、重复引用
或可用历史少于 3 条的目标帖不进入完整 cohort，并按原因计数。

四种方法必须使用同一个完整 cohort。`single_post` 不能使用全量样本，而历史方法只用
子集，否则不允许比较指标。报告同时记录 Gold 总量、各 split 总量、共同 cohort 数量、
排除原因计数和覆盖率。

## 7. 特征与池化

特征版本固定为 `keyword_weights_v1`，输出顺序固定为六个已命名的数值维度。任何记录
的特征键、顺序或版本不一致都必须拒绝。

- `single_post = f(target)`；
- `history_mean = concat(f(target), mean(f(history)))`；
- `history_max = concat(f(target), max(f(history)))`；
- `history_ema = concat(f(target), ema(f(history), alpha=0.5))`。

EMA 按历史发布时间升序计算，最早记录初始化状态。所有方法只使用目标时间之前的同一
creator 历史；标签、标注证据、划分名称、未来帖子和绝对时间值均不得成为模型特征。

## 8. 模型与评估

每个方法独立创建并拟合相同类型的流水线：

1. `StandardScaler` 只在 train 拟合；
2. `LogisticRegression` 固定为 `solver="lbfgs"`、`C=1.0`、
   `max_iter=1000`、`random_state=0`、`class_weight=None`；
3. 特征预处理、模型和标签编码均不得在 dev/test 上拟合。

分类标签输出顺序固定为 `明广`、`暗广`、`非广`；模型内部 `classes_` 必须按标签名
重新映射后才能写报告。`暗广` 概率作为 `dark_ad_score`。默认评估 dev；正式 test
需要显式 `--confirm-test-evaluation`，并在报告中记录该确认和生成时间。

每个方法报告：

- Macro-F1；
- 暗广 Precision、Recall、F1 和 AUPRC；
- ECE 与 Brier score；
- confusion counts；
- 相对 `single_post` 的配对点估计差值；
- train 与评估样本数。

在没有 creator-cluster bootstrap 前，只报告点估计，不声称“稳定增益”或统计显著性。

## 9. 报告与隐私

报告仅保存聚合信息：

- mode、`research_claims_allowed` 和数据种类；
- Schema、feature、pooling、classifier 和报告版本；
- content、Gold、split IDs、split report、M1 gate 和配置的 SHA-256；
- Python、scikit-learn 版本及完整固定参数；
- cohort 数量、排除原因和覆盖率；
- 各方法聚合指标、confusion counts 和差值；
- 是否显式确认 test 评估。

报告不得保存正文、OCR、URL、媒体路径、creator/annotator/arbiter ID 或逐样本预测。

## 10. 错误处理

以下情况必须在训练前 fail closed：

- 正式模式 M1 未通过；
- scikit-learn 未安装；
- 输入无法解析或 Schema/版本不符；
- content、Gold、split ID 不能一一对应；
- split 重叠、不完整、缺类别或泄漏证据缺失；
- 历史违反 creator、时间或唯一性约束；
- 共同 cohort 任一 split 缺少三类样本；
- 特征非有限数、键不一致或版本不匹配；
- 未确认却请求正式 test 评估；
- 输出路径无法写入。

失败消息只描述聚合原因，不回显原始正文、URL或身份字段。

## 11. 文件范围

实现只新增或修改与本任务直接相关的文件：

- `baseline/README.md`；
- `baseline/requirements.txt`；
- `baseline/__init__.py`；
- `baseline/contracts.py`；
- `baseline/features.py`；
- `baseline/runner.py`；
- `baseline/reporting.py`；
- `baseline/cli.py`；
- `baseline/tests/` 及合成夹具；
- `docs/隐性广告识别项目_说明书.md`；
- `docs/隐性广告识别项目_分阶段计划表.md`；
- `docs/已有功能测试指令库.md`；
- `HANDOFF.md`；
- 必要时更新 `README.md` 的当前状态表。

不触碰当前工作树中用户已有的四个删除项，也不做邻近重构。

## 12. 验收标准

工程任务完成必须同时满足：

1. 正式模式对当前 `m1_gate_report.json` 明确拒绝，且在训练前退出；
2. 合成模式四种方法端到端运行并生成可解析、隐私安全的报告；
3. 精确值测试覆盖 mean、max 和 chronological EMA；
4. 测试覆盖跨 creator、未来/同时间、重复、缺引用和历史不足；
5. 测试证明四种方法使用完全相同的目标 ID cohort；
6. 测试证明 split 覆盖、互斥、类别和泄漏检查均 fail closed；
7. 固定输入与随机种子得到确定性指标；除 `generated_at` 外的报告内容完全一致；
8. 报告不含原文、URL或身份 ID；
9. baseline 专项测试、现有 CreatorShift 专项测试、全量默认回归、compileall 和
   `git diff --check` 全部通过；
10. 当前状态文档明确区分“历史融合基线工程包完成”与“M1/M4/真实论文评测未通过”。

这些验收只证明基线工程准备就绪。正式研究完成仍要求通过 M1、使用批准的 Gold 和
无泄漏 split、执行一次受控 test 评估，并对结果做符合论文要求的统计分析。
