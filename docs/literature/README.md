# 相关论文检索：该查哪些会议，以及已落地的 DOI 清单

> 生成时间：2026-10-27。本目录只存放题录元数据（题名/作者/年份/会议/DOI）与链接，不存放任何平台正文，也不随仓库分发 PDF。
> 自动生成的完整结果见 [venue_results_generated.md](./venue_results_generated.md)，开放获取情况见
> [open_access_report.md](./open_access_report.md)，原始数据见
> [venue_search_results.json](./venue_search_results.json)，检索脚本见
> [venue_paper_search.py](../../scripts/literature/venue_paper_search.py) 与
> [fetch_open_access.py](../../scripts/literature/fetch_open_access.py)。

## 1. 结论：按项目主线映射到会议

项目要交付三样东西——暗广识别（明广/暗广/非广 + 证据链）、CreatorShift（创作者纵向变化）、
可引用的法规 RAG。这三个方向在文献里的落点并不在同一个会议，因此检索要分圈层做。

| 圈层 | 会议 | 对应项目里的哪条线 | DOI | 本次命中 |
| --- | --- | --- | --- | ---: |
| **必查·社交媒体实证** | ICWSM | 推广内容检测、影响者披露合规、创作者经济 | `10.1609/...` | 28 |
| **必查·Web/数据挖掘** | WWW、KDD、WSDM、CIKM | 商业意图识别、影响者/创作者建模、图与行为序列 | `10.1145/...` | 41 / 23 / 8 / 14 |
| **必查·NLP** | ACL、EMNLP（含 Findings）、NAACL、EACL、COLING | 披露文本分类、广告合规、术语与证据抽取 | `10.18653/v1/...` | 15 / 21 / 9 / 3 / 3 |
| **必查·通用 AI** | AAAI | 合规检查、广告检测任务化 | `10.1609/...` | 36 |
| 应查·多模态 | ACM MM、CVPR、ICCV、ECCV | 图片/视频里的品牌、LOGO、场景文字，图文一致性 | `10.1145` / `10.1109` / `10.1007` | 3 / 1 / 2 / 0 |
| 应查·检索 | SIGIR | 赞助搜索、广告检索与相关性 | `10.1145/...` | 10 |
| 应查·社会计算 | IJCAI | 检测方法与社会计算 | `10.24963/...` | 18 |
| 视角补充 | CHI、CSCW | 用户能否识别披露、"暗广"感知实验、平台劳动 | `10.1145/...` | 18 / 3 |
| **无 DOI 但必须看** | NeurIPS（含 D&B track）、ICLR、ICML | 数据集/基准、多模态与 Agent 方法 | 无（OpenReview / PMLR） | 2（arXiv 补位） |
| 会议清单之外 | workshop 与期刊（兜底检索） | 同题工作常常不发在这些会议上 | 混合 | 26 |

判断依据（都来自仓库文档）：

- 标签口径是"有没有发现明确披露"，本质是**披露证据的有无**，属文本分类 + 证据抽取问题，
  所以 ACL/EMNLP/COLING 是主场（[说明书 3.1/3.3](../隐性广告识别项目_说明书.md)）。
- 证据包含图像与评论，且要做图文一致性，落在 ACM MM / CVPR / ICCV / ECCV。
- CreatorShift 是"同创作者、目标帖之前的历史 + 纵向偏移"，属于创作者/行为序列建模，
  落在 KDD/WWW/WSDM 与 ICWSM。
- 法规与平台规则要做可引用 RAG，法律文本 NLP 在 ACL/EMNLP（含 NLLP workshop）；
  "广告合规检查"这类任务化工作在 AAAI / ACL Industry Track 出现得更频繁。
- 平台的披露规范、影响者经济、用户侧的披露识别，属社会计算与人机交互，落在 ICWSM/CSCW/CHI。

## 2. DOI 可得性对照（决定能不能用"DOI 号"作为检索凭证）

| 会议 | DOI 前缀 | 备注 |
| --- | --- | --- |
| ACL / EMNLP / NAACL / EACL / COLING（含 Findings、Industry、Demo） | `10.18653/v1/...` | ACL Anthology 原生 DOI，最稳定 |
| ACM 系（KDD/WWW/WSDM/CIKM/SIGIR/MM/CHI/CSCW） | `10.1145/...` | 含 companion/workshop 卷 |
| AAAI、ICWSM | `10.1609/...` | 注册为 journal-article，卷号可还原会议年份（`aaai.v40`→2026、`icwsm.v18`→2024） |
| IJCAI | `10.24963/...` | |
| CVPR / ICCV（IEEE） | `10.1109/...` | workshop 卷为 `cvprw`/`iccvw` |
| ECCV（Springer LNCS） | `10.1007/...` | |
| **NeurIPS** | 无 | proceedings.neurips.cc，按 URL 或 arXiv 引用 |
| **ICLR** | 无 | OpenReview ID |
| **ICML** | 无 | PMLR 卷号（如 `v235`） |
| arXiv 预印本 | `10.48550/arXiv.xxxx.xxxxx`（DataCite） | 可作为补充，但不等于会议正式版 |

## 3. 检索方法（可复现）

```powershell
cd d:\projectsnew\Detection-of-Recessive-Advertising
.\.venv\Scripts\python.exe scripts\literature\venue_paper_search.py `
  --rows 500 --with-arxiv `
  --output docs\literature\venue_search_results.json `
  --markdown docs\literature\venue_results_generated.md
```

- **数据源**：ACL Anthology 逐卷 `.bib`（ACL 系全量主会/Findings）+ Crossref 公开 API
  （按 DOI 前缀分组、用 proceedings 名正则归会）+ arXiv API（补 NeurIPS/ICLR/ICML）
  + 不限会议的短语兜底检索（catch workshop/期刊上的同题工作）。
- **过滤策略**：先过"广告/赞助/推广"硬门槛词（`advertis*`、`sponsor*`、`influencer`、
  `native ad`、`advertorial`、`undisclosed` 等），再打主题标签
  （covert_advertising / ad_detection / multimodal / creator_history / compliance_rag / agent_system）。
  没有硬门槛时，`multimodal`、`compliance`、`agent` 这类泛词会把整届会议都捞进来——实测 AAAI
  一届就能误命中上百条。兜底检索（不限会议）额外要求题名或摘要里出现计算/实证口径的词
  （detect/classif/model/LLM/dataset/benchmark/regulation 等），把营销学与语言学的纯理论文章挡在外面。
- **检索式**（Crossref 用相关性检索，不是布尔式）：
  `covert advertising detection social media`、`implicit advertising undisclosed sponsorship`、
  `influencer advertising disclosure`、`native advertising detection`、
  `promoted post commercial intent detection`、`multimodal advertising detection image text`、
  `influencer creator history modeling`、`advertising regulation compliance`；
  兜底一组为 `covert advertising detection`、`implicit advertising detection`、
  `undisclosed advertising social media`、`advertorial detection`、`influencer disclosure compliance`。
- **已知限制**：
  - ACL Anthology 的 `.bib` 一般不含摘要，所以这一路只按**题名**匹配，召回偏低；
    Crossref 一路才有摘要。
  - DBLP 已启用 Anubis 反爬（返回 JS 挑战页），无法脚本化；OpenAlex 与 Semantic Scholar 在
    本网络下持续返回 429。因此这两个源没有进链路，改由 Crossref 承担。
  - Crossref 偶发 429/连接中断，脚本有退避重试，个别查询会缺一条（日志里会打印）。
  - 期刊（Journal of Advertising、International Journal of Advertising、IP&M、TOIS、
    Telematics and Informatics 等）未做系统检索，只是兜底短语偶然命中了少量传播学/营销学期刊文章，
    见第 6 节第 3 条。

## 4. 结果规模

本次共命中 **284** 条记录，其中 **279** 条带 DOI（含 arXiv 补位 2 条、会议清单外兜底命中 26 条）。
分公司计数见 [venue_results_generated.md](./venue_results_generated.md)。

开放获取情况见 [open_access_report.md](./open_access_report.md)：284 条中 127 条有可直接下载的
PDF 直链（ACL Anthology / AAAI OJS / arXiv），107 条只能给到出版社页面（ACM DL、IEEE Xplore 等，
需机构订阅），43 条查不到开放版本。生成命令：

```powershell
.\.venv\Scripts\python.exe scripts\literature\fetch_open_access.py
```

只重跑兜底短语（不重复跑 Anthology/Crossref 主检索，约 1 分钟）：

```powershell
.\.venv\Scripts\python.exe scripts\literature\venue_paper_search.py --stage global
```

## 5. 核心必读清单（已逐条读摘要核对）

判断依据是**摘要**，不是题名——这一步改变了结论：题名里带 `disclosure` 的论文未必是广告披露
（例如 Findings EMNLP 2020 的 *A Semantics-based Approach to Disclosure Classification* 讲的是
**自我披露/隐私**），题名像广告检索的论文也未必在判"是否暗广"。下表按"与本项目的直接程度"排序，
DOI 均已在 Crossref 核验可解析。5.1–5.3 是读摘要后确认相关的，5.4 是题名命中但读摘要后判定只是远亲的。

### 5.1 第一梯队：直接同任务或同数据形态（必须精读）

| # | 题名 | 会议/年份 | DOI | 摘要里最关键的事实 |
| --- | --- | --- | --- | --- |
| 1 | Discovering Undisclosed Paid Partnership on Social Media via Aspect-Attentive Sponsored Post Learning (SPoD) | WSDM 2021 | `10.1145/3437963.3441803` | **与本项目最像的一篇**：显式建模"未披露付费合作"，用图文对象 + 影响者-品牌-帖子异构图（GCN）+ 时间流形正则；数据是 1,601,074 条 Instagram 帖、26,910 个品牌、38,113 位创作者、跨 6 年。它已经把"创作者×品牌×时间"的设定跑通了，本项目的差异点只剩中文平台、三分类与证据链 |
| 2 | AdDriftBench: A Benchmark for Detecting Data Drift and Label Drift in Short Video Advertising | Findings EMNLP 2025 | `10.18653/v1/2025.findings-emnlp.545` | 短视频广告 3,480 条，把漂移拆成 **data drift（广告主刻意规避审核导致分布突变）** 与 **label drift（平台审核指南演化导致判定边界移动）**。这正是 CreatorShift 与"阈值/校准会过期"的直接依据，也是必引的竞品基准 |
| 3 | The Covert Advertising Recognition and Effects (CARE) model | Int. J. Advertising 2019 | `10.1080/02650487.2019.1658438` | 给了"暗广"的构念定义：隐蔽广告借用非广告形式，效果取决于**受众是否识别出这是广告**。为本项目"明广/暗广/非广"标签与"披露证据"提供理论辩护 |
| 4 | Turning Trust to Transactions: Tracking Affiliate Marketing and FTC Compliance in YouTube's Influencer Economy | ICWSM 2026 | `10.1609/icwsm.v20i1.42748` | 10 年、200 万视频、54 万创作者的测量：联盟链接普遍存在但**披露合规率低**，且平台标准化披露功能显著改善合规。这是"未披露是普遍现象"的最强实证，直接支撑 motivation |
| 5 | Multimodal Post Attentive Profiling for Influencer Marketing | WWW 2020 | `10.1145/3366423.3380052` | 用图文注意力做创作者主题画像，并公开 33,935 位创作者 / 10,180,500 条帖的标注数据。是 CreatorShift"历史表示"最现实的基线实现与数据来源 |
| 6 | Detection of Promoted Social Media Campaigns | ICWSM 2016 | `10.1609/icwsm.v10i1.14772` | 把"这条传播是被推广活动推动的，还是自然发生的"做成早期检测任务（95% AUC），核心信号是**网络扩散模式 + 内容线索**。任务定义与评估口径可沿用 |
| 7 | TAIGR: Towards Modeling Influencer Content on Social Media via Structured, Pragmatic Inference | ACL 2026 | `10.18653/v1/2026.acl-long.1868` | 影响者内容不是事实主张而是**语用说服**：先抽 recommendation-takeaway，再建论证图，再做概率校验。对应本项目"商业意图聚合"这一步该怎么做才不是简单分类 |
| 8 | AdSpectorX: A Multimodal Expert Spector for Covert Advertising Detection on Chinese Social Media | SocialMeta workshop @ SenSys 2024 | `10.1145/3698387.3700001` | 中文社媒 + 隐蔽广告 + 多模态专家模型的直接对标（workshop 论文，体量小，但题目完全撞车） |

### 5.2 第二梯队：合规 / 法规 RAG（对应项目第 7 步）

| # | 题名 | 会议/年份 | DOI | 摘要里最关键的事实 |
| --- | --- | --- | --- | --- |
| 9 | VietCheckMed: Explainable Regulatory Compliance Checking for Medical Advertisements on Vietnamese Social Media | AAAI 2026 | `10.1609/aaai.v40i2.37077` | RAG + 权威法规库（9,978 家机构）+ 8,329 条广告基准；**比不带检索的强 LLM 高 0.38 F1**，并明确指出剩余难点是语义与逻辑推理。这就是"法规检索必须带引用"的实验证据 |
| 10 | ℛ3: Advertisement Compliance ℛectification via Group-Relative Experience Extractor and Curriculum Reinforcement | ACL 2026 Industry | `10.18653/v1/2026.acl-industry.24` | 视频广告的**语音转写 + 屏显文本**违规整改，强调"合规"与"保留广告原意"的权衡；工业 A/B 验证。对应本项目图像文字与文本双通道的证据采集 |
| 11 | Assessing Compliance in Digital Advertising: A Deep Dive into Acceptable Ads Standards | WWW 2025 | `10.1145/3696410.3714725` | 1 万个高流量站点的合规测量：近 10% 站点展示不合规广告，且**规则清单本身有设计漏洞**。提醒：法规 RAG 的语料与判据要能指出规则缺陷，而不只是复述规则 |
| 12 | Regulations on Covert Advertising: An Analysis of Advertising Board Decisions in Türkiye | Ege Academic Review 2025 | `10.21121/eab.20250407` | 监管机构对隐性广告的裁量要素清单，可作为 RAG 语料结构（要件→判定）的模板（期刊论文，权威性一般） |

### 5.3 第三梯队：新形态 / 可迁移方法 / 数据补充

| # | 题名 | 会议/年份 | DOI | 摘要里最关键的事实 |
| --- | --- | --- | --- | --- |
| 13 | Detecting Generated Native Ads in Conversational Search | WWW 2024 | `10.1145/3589335.3651489` | LLM 回答里插入的**生成式原生广告**检测；发布 Webis Generated Native Ads 2024 数据集；LLM 直接判不行，微调 sentence transformer 的 P/R 可过 0.9。对应"未来暗广形态"与轻量基线选择 |
| 14 | Detecting Undisclosed Paid Editing in Wikipedia | WWW 2020 | `10.1145/3366423.3380055` | 另一域的"未披露付费"检测（维基推广性条目），可借鉴它如何界定"未披露"的证据边界 |
| 15 | InstaSynth: Opportunities and Challenges in Generating Synthetic Instagram Data with ChatGPT for Sponsored Content | ICWSM 2024 | `10.1609/icwsm.v18i1.31303` | 用 LLM 造未披露广告语料；结论是 **fidelity 与 utility 会冲突**，单条像真的但整体缺多样性与真实互动结构。直接关系本项目暗广稀有类怎么补数据 |
| 16 | Evaluating Audience Loyalty and Authenticity in Influencer Marketing via Multi-task Multi-relational Learning | ICWSM 2021 | `10.1609/icwsm.v15i1.18060` | 用评论互动网络判影响者受众的忠诚/真实性（假粉、机器人）；14,221 位影响者、6,584 万次互动。可作为创作者历史特征与"需复核"信号 |
| 17 | The Effects of Influencer Advertising Disclosure Regulations: Evidence From Instagram | EC 2020 | `10.1145/3391403.3399477` | 德国/西班牙 50 位头部影响者 2014–2019 的 DiD：监管变化后披露采纳不均，赞助内容反而可能增加。是"只靠监管不够、需要检测"的因果证据 |
| 18 | SAGraph: A Large-Scale Social Graph Dataset with Comprehensive Context for Influencer Selection in Marketing | SIGIR 2025 | `10.1145/3726302.3730334` | 微博营销数据：345,039 用户、44K 帖、1.3M 评论、554K 转发，含时序互动；中文平台 + 时间序列，形态最接近本项目语料 |
| 19 | Followers Tell Who an Influencer Is | WWW 2023 Companion | `10.1145/3543873.3587576` | 用粉丝结构给影响者归类，说明"创作者画像"可由受众侧信号补足 |
| 20 | Desire Guidance Mechanisms and Covert Advertising: A Case Study of Xiaohongshu | ICA PMM 2025（SCITEPRESS） | `10.5220/0014108500004942` | 唯一直接研究**小红书**隐性广告的定量/质性论文，平台完全对齐（会议层级低，只作场景引用） |

> 注：5.1 的第 6 条（ICWSM 2016）早于本次年份窗口，5.3 的第 17 条（EC 2020）与第 20 条（小红书 2025）
> 不在上述会议清单内、且题名不含计算类词，因此这三条不在 `venue_search_results.json` 的按会议分组里，
> 但 DOI 都已单独在 Crossref 核验可解析。

### 5.4 读摘要后判定为"远亲"，只放 related work 边缘

| 题名 | DOI | 为什么降级 |
| --- | --- | --- |
| A Semantics-based Approach to Disclosure Classification in User-Generated Online Content (Findings EMNLP 2020) | `10.18653/v1/2020.findings-emnlp.312` | 讲的是 Reddit 上的**自我披露/隐私**（用语义角色标注），不是广告披露。仅可作"披露"一词的方法学类比 |
| Benchmarking Commercial Intent Detection Services (NAACL 2021 Industry) | `10.18653/v1/2021.naacl-industry.38` | "intent detection" 指对话系统意图识别（Watson Assistant 等），与广告商业意图无关 |
| Real-time Ad Retrieval via LLM-generative Commercial Intention (EMNLP 2025) | `10.18653/v1/2025.emnlp-main.1473` | 用 LLM 生成商业意图做**广告检索**，目标是提高 GMV/CTR，不判"是否暗广" |
| Hybrid Advertising in the Sponsored Search (SIGIR 2025) | `10.1145/3726302.3729999` | 搜索广告机制设计，与披露/意图判定无关 |
| ADMoE (AAAI 2023) 等噪声命中 | `10.1609/aaai.v37i4.25620` | 题名含 Ad 的缩写（anomaly detection），纯误召回 |

做 related work 时的分组建议：`① 未披露推广检测与基准`（SPoD、AdDriftBench、Promoted Campaigns、AdSpectorX、InstaSynth）、
`② 披露/暗广的构念与效果`（CARE、EC'20 监管、ICWSM'26 FTC）、`③ 创作者与影响者建模`（Multimodal Profiling、SAGraph、Audience Loyalty、TAIGR）、
`④ 广告合规与法规 RAG`（VietCheckMed、ℛ3、Acceptable Ads）、`⑤ 新形态与迁移`（Generated Native Ads、Wikipedia Paid Editing）。

## 6. 后续建议

1. **英文检索词要与中文口径对齐**：本项目说的"暗广"，英文文献里分散在
   `covert advertising`、`implicit advertising`、`undisclosed sponsorship`、`native advertising`、
   `advertorial`、`stealth marketing`、`deceptive advertising`、`shill` 等词下，单一关键词会漏。
2. **NeurIPS/ICLR/ICML 单独走 OpenReview 与 arXiv**，不要指望 DOI；数据集类论文优先看
   NeurIPS Datasets & Benchmarks track。
3. **补期刊一圈**：Journal of Advertising、International Journal of Advertising、
   Information Processing & Management、ACM TOIS、Telematics and Informatics、
   Electronic Commerce Research——披露效果的实证大多在传播学/营销学期刊，不在会议里。
4. **补 ACL/EMNLP 的 workshop**：NLLP（法律 NLP）、SICON（社会影响对话）、
   WOAH 等卷没有在本次逐卷抓取范围内，做 RAG 与安全章节时应单独检索。
5. **取全文的顺序**：先看 [open_access_report.md](./open_access_report.md) 里 `direct-pdf` 的 127 条
   （ACL Anthology / AAAI OJS / arXiv 直链，直接下）；ACM DL 与 IEEE Xplore 的 107 条走校园网或
   作者主页 / arXiv 预印本；43 条查不到开放版本的（多为 CHI）只能找通讯作者或走机构订阅。
   需要批量下载时加 `--download-dir`，文件只落本地，不入库。
6. **投稿定位建议**（与阶段计划表的"一篇 CreatorShift 主论文"对齐）：
   - 方法与实证都扎实 → ICWSM / WWW（社媒推广、创作者生态，最贴合）；
   - 偏 NLP 的披露分类与证据抽取 → EMNLP / ACL Findings（体量更匹配本科毕设）；
   - 偏系统与工程 → AAAI/ACL Industry Track 或 CIKM applied track；
   - 加用户实验 → CHI / CSCW。
   NeurIPS/ICLR 不作为首投目标：审稿口径偏方法新颖性，本项目卖点是纵向数据与证据链。
