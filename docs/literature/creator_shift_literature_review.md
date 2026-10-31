# 创作者历史与隐性广告识别：文献检索与筛选记录

**检索日期：** 2026-10-31<br>
**服务对象：** `short-paper-research/creator_shift_study_draft_20261031.docx`<br>
**状态：** 面向研究设计稿的定向文献检索，不是系统综述，也不是元分析。

## 1. 目的与范围

本记录服务于一个可证伪的研究问题：在同一创作者的目标帖上，目标帖相对于其既往内容的“变化”表示，能否在单帖基线和简单历史聚合之外，提高明广、暗广、非广三分类的效果，同时不损害暗广召回。

检索围绕六组概念展开：

1. 隐性广告、未披露赞助、原生广告与披露识别；
2. 中文社交媒体上的隐性广告检测；
3. 影响者画像、创作者历史与时间信息；
4. 广告数据漂移与标签漂移；
5. 多模态证据定位与视觉语言模型的局限；
6. 大模型辅助标注及其与独立人工标注的边界。

## 2. 检索来源与过程

### 2.1 已有候选池

主候选池来自 `docs/literature/open_access_report.md`。该报告由 `scripts/literature/fetch_open_access.py` 生成，汇总 Unpaywall、ACL Anthology 与 arXiv 的开放获取状态，共 284 条记录：

- 127 条有可直接访问的 PDF 链接；
- 114 条只有出版社页面；
- 43 条没有发现开放版本。

报告是“广告/传播/计算”混合候选池，包含大量程序化广告、竞价、CTR 预测与异常检测论文，不能整体视为隐性广告文献。筛选时逐条判断题名、摘要与任务对象，而不是按“广告”关键词全收。

### 2.2 补充元数据

OpenAlex 与 Crossref 的批量检索在当前网络下多次返回 `HTTP 429`，Semantic Scholar 亦持续限流。因此改用：

- 对 17 个与本研究直接相关的 DOI 逐条查询 OpenAlex，保存于 `data/run_outputs/openalex_creator_shift.json`；
- 对 CHASM 与 AdSpectorX 做定向网页核对；
- 以出版社/arXiv/ACL Anthology 页面核对作者、年份、venue 与 DOI。

### 2.3 检索概念组合

英文检索概念包括：

```text
("covert advertising" OR "undisclosed sponsorship" OR "native advertising"
 OR "sponsored post" OR "affiliate marketing")
AND ("social media" OR influencer OR creator)

("creator history" OR "temporal" OR "longitudinal" OR "drift"
 OR "content shift")
AND (advertising OR sponsorship OR influencer)

("multimodal" OR "vision-language" OR "image-text")
AND (advertising OR sponsored content)

("LLM annotation" OR "model-assisted annotation" OR "synthetic data")
AND (advertising OR content moderation)
```

中文检索概念包括“隐性广告”“暗广”“未披露广告”“软广”“种草”“品牌合作”“创作者历史”“内容漂移”等。中文平台相关工作主要靠题名、摘要与引用链补充，未做完整中文数据库检索。

## 3. 纳入与排除标准

### 3.1 纳入

- 直接研究社交媒体商业内容、赞助披露、隐性/原生广告或影响者营销；
- 直接研究创作者层面的画像、历史、时间动态或广告数据漂移；
- 直接研究多模态广告理解、证据定位或视觉语言模型在广告任务上的可靠性；
- 直接研究大模型辅助标注、合成数据或人机协作标注；
- 能核验作者、年份、venue 与 DOI，且对本文论证有明确用途。

### 3.2 排除

- 程序化广告、实时竞价、CTR/转化率预测、广告拍卖与流量异常检测；
- 隐私领域的 self-disclosure（自我披露）研究，即使题名含 “disclosure”；
- 仅研究 Wikipedia 付费编辑、且不能提供社媒广告类比的条目（只保留一条方法类比）；
-  Conversational search 中的生成式原生广告（作为相邻问题记录，不纳入主论证）；
- 无法核验元数据、无法判断任务对象的条目；
- 仅凭题名无法确认与“商业推广意图/披露”有关的条目。

## 4. 筛选结果

- 候选池：284 条；
- 逐条元数据补充：17 个 DOI；
- 进入本文论证：18 条（含 1 条方法类比、1 条概念模型、1 条校准方法、1 条聚类 bootstrap 方法）；
- 明确排除但值得记录的条目：
  - *A Semantics-based Approach to Disclosure Classification in User-Generated Online Content*（Findings of EMNLP 2020）：研究 Reddit 上的隐私 self-disclosure，不是赞助/广告披露，不能作为广告披露文献引用；
  - *Detecting Undisclosed Paid Editing in Wikipedia*（WWW 2020）：只作为“未披露付费内容”的方法类比，不能外推为社媒广告证据；
  - *Detecting Generated Native Ads in Conversational Search*（WWW 2024）：研究对象是对话式搜索中的生成式原生广告，与社媒帖子/创作者历史不同；
  - *Understanding Advertisements with BERT*（ACL 2020）：广告理解任务，但不是隐性广告披露或创作者历史，未进入主论证。

## 5. 纳入文献与用途

| # | 文献 | 年份 / venue | 可核查内容（来自摘要或元数据） | 在本文中的用途 |
|---|---|---|---|---|
| 1 | Zheng J, Hu T, Liu Y, Sun Z, Zhang Z, Peng Z, Dong W, He X. CHASM: Unveiling Covert Advertisements on Chinese Social Media | NeurIPS Datasets & Benchmarks, 2025 | 4,992 条匿名人工标注的中文社交媒体实例；通用 MLLM 零样本/ICL 表现不稳定；微调开源 MLLM 有提升 | 中文隐性广告基准与任务动机；模型辅助的上限与风险 |
| 2 | Kim S, Jiang J-Y, Wang W. Discovering Undisclosed Paid Partnership on Social Media via Aspect-Attentive Sponsored Post Learning (SPoD) | WSDM, 2021 | 1,601,074 条 Instagram 帖、38,113 名影响者、26,910 个品牌、6 年；文本/图像/GCN/时间流形正则 | 未披露赞助检测的直接前作；时间信息的使用方式 |
| 3 | Song Y, Zeng X, Cui S, Sun L, Liu Z, Yuan Y, Wang Y, Zhou H M, Gong Z. AdDriftBench | Findings of EMNLP, 2025 | 短视频广告数据漂移与标签漂移基准；本次未取得摘要，不引用具体数值 | 说明广告数据/标签随时间变化，支撑时间安全评估 |
| 4 | Mathur A, Narayanan A, Chetty M. Endorsements on Social Media | PACM HCI, 2018 | 50 万 YouTube 视频 + 210 万 Pinterest 钉；仅约 10% 联盟内容有披露；1,791 人用户实验 | 披露缺失的普遍性；披露措辞/位置影响识别 |
| 5 | Gilardi F, Alizadeh M, Kubli M. ChatGPT Outperforms Crowd Workers for Text-Annotation Tasks | PNAS, 2023 | 多项文本标注任务上 ChatGPT 可超过众包工作者 | 模型辅助标注的可能性与边界 |
| 6 | Field C A, Welsh A H. Bootstrapping Clustered Data | JRSS-B, 2007 | 聚类数据的 bootstrap 方法 | 创作者聚类配对区间估计 |
| 7 | Guo C, Pleiss G, Sun Y, Weinberger K Q. On Calibration of Modern Neural Networks | ICML, 2017 | 现代神经网络校准误差与温度缩放 | ECE/Brier 与校准报告 |
| 8 | Zhang Z, Han Y, Zhang Z, Liu Y, Zheng J, Sun Z-T. AdSpectorX | SocialMeta '24, 2024 | 摘要称 500 条 REDnote 人工收集帖（文本/图片/评论），准确率 95.06%；数据链接在 GitHub | 中文多模态隐性广告检测的直接相关系统 |
| 9 | Sun C, Vekaria Y, Shafiq Z, Nithyanand R. Turning Trust to Transactions | ICWSM, 2026 | 200 万 YouTube 视频、约 54 万创作者、10 年；联盟披露合规率低；平台标准化披露功能与更高合规相关 | 披露合规的规模测量与平台因素 |
| 10 | Wojdynski B W, Evans N J. The Covert Advertising Recognition and Effects (CARE) Model | International Journal of Advertising, 2019 | 概念模型：识别是 covert advertising 说服效果的核心中介；前因包括格式、披露与受众知识 | 把“披露是否被识别”与“是否商业推广”分开 |
| 11 | Kim D Y, Kim H-Y. Influencer Advertising on Social Media: The Multiple Inference Model | Journal of Business Research, 2020 | 概念模型：影响者-产品一致性与赞助披露的多重推断 | 披露识别的受众侧机制 |
| 12 | Kim S, Jiang J-Y, Nakada M, Han J, Wang W. Multimodal Post Attentive Profiling for Influencer Marketing | WWW, 2020 | 33,935 名影响者、10,180,500 条 Instagram 帖；影响者/帖子分类 98%/96% | 创作者画像与内容历史表示 |
| 13 | Bavaresco A, Testoni A, Fernández R. Don't Buy it! | ACL Short, 2024 | TRADE 对抗测试；四个对比式 VLM 会被 grounding heuristics 误导 | 多模态模型的高分不等于真正广告理解 |
| 14 | Bertaglia T, Heisig L, Kaushal R, Iamnitchi A. InstaSynth | ICWSM, 2024 | 用 LLM 生成合成 Instagram  caption；保真度与检测效用可能冲突；合成数据整体缺乏多样性/主题连通性 | 合成数据不能替代真实标注；数据门禁的必要性 |
| 15 | Nakshatri N S, Caplan E, Pujari R, Goldwasser D. TAIGR | ACL, 2026 | 三阶段：推荐结论识别、论证图构建、因子图概率推断；健康影响者视频转录 | 影响者话语需要语用/论证结构，不能只做扁平文本分类 |
| 16 | Zhang X, Liu Y, Wang J, Hu Z, Chen X, Yan R. SAGraph | SIGIR, 2025 | 微博 345,039 名用户、44K 帖、1.3M 评论、554K 转发；含时间交互模式 | 创作者/活动层面的时间交互数据 |
| 17 | Saha D, Hasan M R, Mueen A. Followers Tell Who an Influencer Is | WWW Companion, 2023 | 用 follower 信息识别影响者类别 | 创作者画像的替代信号，说明“创作者身份”可建模但不等同于广告意图 |
| 18 | Joshi N, Spezzano F, Green M, Hill E. Detecting Undisclosed Paid Editing in Wikipedia | WWW, 2020 | 检测未披露的付费编辑/利益冲突 | 仅作“未披露付费内容”的方法类比 |

## 6. 主题综合

### 6.1 披露是否存在，不等于商业意图是否存在

Mathur 等的大规模测量表明，联盟营销内容的披露率很低，且披露措辞与位置会影响用户识别[4]。CARE 模型把“用户是否意识到这是广告”放在说服效果的中心，并列出格式熟悉度、披露显著性与受众广告知识等前因[10]。Kim 与 Kim 的多重推断模型进一步把影响者-产品一致性与赞助披露放在同一个推断框架中[11]。

这支持本文把标注拆成两个维度：商业推广意图（内容是否在推广）与披露状态（是否观察到明确披露）。前者不能由品牌词、好评或产品特写直接推出；后者也不能因为“页面没看到”就记为“未披露”，必须先确认披露区域被完整采集。CHASM 与 AdSpectorX 的中文数据进一步说明，这两个维度在中文平台语境下同样需要分别记录[1][8]。

### 6.2 隐性广告检测：从单帖分类到关系与时间

SPoD 是未披露赞助检测的直接前作：它把文本、图像物体、影响者-品牌图和时间信息联合起来，用 GCN 与流形正则学习帖子表示[2]。AdSpectorX 面向 REDnote，把帖子文本、相关图片与评论组合成多模态专家系统，摘要报告 500 条人工收集帖和 95.06% 准确率[8]。CHASM 则提供了更大的中文基准（4,992 条），并明确指出通用 MLLM 的零样本/ICL 判断仍不稳定[1]。

这些工作把任务从“广告文本分类”推进到“多模态商业内容识别”，但多数仍以单帖或“帖子+关系”为单位。它们没有把“同一创作者目标帖相对于其既往内容的偏移”作为独立比较对象，也没有统一报告历史窗口、历史充分性与时间泄漏边界。本文的 CreatorShift 正是把这一层单独拿出来做配对比较，而不是再增加一个单帖特征。

### 6.3 创作者画像、历史与漂移

创作者侧研究可分为三类：

- **画像**：Kim 等用文本-图像注意力对 33,935 名影响者、约 1,018 万条帖子做兴趣分类，报告 98%/96% 的准确率[12]；Saha 等用 follower 信息识别影响者类别[17]。
- **关系与活动**：SAGraph 提供微博 campaign 数据，包含 345,039 名用户、44K 帖、1.3M 评论、554K 转发及时间交互模式[16]。
- **时间与漂移**：SPoD 将时间信息作为流形正则[2]；AdDriftBench 把短视频广告的数据漂移与标签漂移作为基准问题[3]。

这些工作说明创作者历史“有信息”，但没有回答本文的问题：在相同目标帖表示、相同标签与相同测试队列上，历史变化是否比均值/最大值/EMA 等简单聚合多出可检验的增量。本文应把贡献限定为“中文平台、证据完整性约束、创作者历史增量评测”，而不是宣称首次提出创作者建模或时间建模。

### 6.4 多模态证据与视觉语言模型的局限

多模态模型确实能提供商品、品牌、屏幕文字等线索；SPoD 与 AdSpectorX 都把图像作为输入[2][8]。但 Bavaresco 等的 TRADE 对抗测试表明，四个对比式 VLM 会依赖 grounding heuristics，看似合理的解释可能并不反映真正的多模态推理[13]。因此，多模态分数不能直接当作“广告意图”证据；本文要求把判断落到可核查的文本/图像区域，并显式记录未采集、不可读与未发现三种状态。

### 6.5 模型辅助标注：能降本，但不能冒充独立人工

Gilardi 等发现 ChatGPT 在多项文本标注任务上可超过众包工作者[5]，但该结论依赖任务、提示与参照标签，不能直接推出广告意图判断的准确性。CHASM 的零样本/ICL 结果说明通用多模态模型在中文隐性广告上仍不稳定[1]；InstaSynth 表明合成帖子单条可能逼真，但整体缺乏多样性、主题连通性与真实互动模式，保真度与检测效用可能冲突[14]；TAIGR 则说明影响者话语需要语用/论证结构，扁平文本分类不足以刻画推荐结论及其理由[15]。

对本文的直接影响是：模型建议只能作为辅助证据，不能进入独立双标的 κ 计算；若标注者看过建议，记录必须标为 `human_assisted`，并与独立 `human` 分开导出。现有 `build_gold_dataset.py` 与 `calculate_agreement.py` 会拒绝非 `human` 记录，这是有意的数据门禁，不应为了“兼容”而把辅助判断改标为独立人工。

### 6.6 研究空白

综合以上，本文可以主张的空白是：

1. 现有隐性广告检测多以单帖或帖子-关系为单位，缺少“目标帖 vs 同一创作者历史”的配对比较；
2. 现有创作者画像/时间建模多用于表示学习或漂移测量，未把“变化”作为与简单历史聚合对照的独立变量；
3. 中文平台上的公开数据、标签映射与许可仍未核验，不能把不同来源直接混成一个测试集；
4. 模型辅助标注与独立盲标的边界在工程上常被混淆，需要记录级字段与下游门禁共同约束。

## 7. 对论文初稿的具体改写

- 2.1 增补 Mathur et al. (2018)、CARE、Kim & Kim (2020)、SPoD、AdSpectorX、CHASM、Sun et al. (2026)，把“披露识别”与“广告检测”分开；
- 2.2 增补 AdSpectorX、SPoD 的多模态输入，以及 Bavaresco et al. (2024) 对 VLM grounding heuristics 的警告；
- 2.3 增补 Kim et al. (2020) 的创作者画像、SAGraph 的时间交互、SPoD 的时间正则、AdDriftBench 的漂移，并明确“没有直接研究 CreatorShift”的空白；
- 2.4 增补 Gilardi et al. (2023)、CHASM、InstaSynth、TAIGR，并写明 `human` 与 `human_assisted` 的下游区别；
- 新增 2.5“文献检索范围与筛选记录”，交代候选池、纳入/排除与局限；
- 参考文献从 7 条扩到 18 条，并在正文中逐条引用；
- 4.3 增补聚类 bootstrap[6] 与校准[7] 的方法依据。

## 8. 未核实项与限制

1. **AdSpectorX 数据许可与标签映射未核验。** 论文摘要称数据在 `https://github.com/Zonmgin-Zhang/AdSpectorX`，但本次网络无法访问 GitHub 页面；其 500 条数据是否可公开下载、许可为何、标签如何映射到本项目三分类，均待确认。报告将其标为 closed，与论文摘要的“data available”存在张力，正文只能写“论文声称公开、待核验”。
2. **CHASM 版本与作者顺序。** 以 arXiv `2604.20511` 与 NeurIPS 2025 D&B 页面为准；正式投稿前仍需核对 camera-ready 作者顺序与页码。
3. **AdDriftBench 未取得摘要。** 仅按题名判断其研究数据漂移与标签漂移，未引用具体方法或数值。
4. **部分条目只读摘要/元数据。** 未对 18 条全部做全文精读；涉及具体实验数字时，正文使用“该文报告/摘要称”的限定语。
5. **候选池不是完整检索。** 284 条来自既有开放获取报告，未覆盖所有中文数据库、会议论文与出版社闭源文献；因此本文不称“系统综述”。
6. **网络限流。** OpenAlex/Crossref/Semantic Scholar 多次 429，无法做可复现的批量检索；本记录保留检索式与 DOI 清单，便于后续重跑。
7. **不同数据集不可直接混合。** AdSpectorX、CHASM 与本项目数据的平台、标签定义、采集完整性与许可均不同；在完成映射与门禁前，只能分别做探索性试标。

## 9. 参考文献

[1] Zheng J, Hu T, Liu Y, Sun Z, Zhang Z, Peng Z, Dong W, He X. CHASM: Unveiling Covert Advertisements on Chinese Social Media. NeurIPS Datasets and Benchmarks, 2025. arXiv:2604.20511.

[2] Kim S, Jiang J-Y, Wang W. Discovering Undisclosed Paid Partnership on Social Media via Aspect-Attentive Sponsored Post Learning (SPoD). WSDM, 2021. DOI: 10.1145/3437963.3441803.

[3] Song Y, Zeng X, Cui S, Sun L, Liu Z, Yuan Y, Wang Y, Zhou H M, Gong Z. AdDriftBench: A Benchmark for Detecting Data Drift and Label Drift in Short Video Advertising. Findings of EMNLP, 2025. DOI: 10.18653/v1/2025.findings-emnlp.545.

[4] Mathur A, Narayanan A, Chetty M. Endorsements on Social Media: An Empirical Study of Affiliate Marketing Disclosures on YouTube and Pinterest. PACM HCI, 2018, 2(CSCW):119. DOI: 10.1145/3274388.

[5] Gilardi F, Alizadeh M, Kubli M. ChatGPT Outperforms Crowd Workers for Text-Annotation Tasks. PNAS, 2023, 120(30):e2305016120.

[6] Field C A, Welsh A H. Bootstrapping Clustered Data. Journal of the Royal Statistical Society: Series B, 2007, 69(3):369-390. DOI: 10.1111/j.1467-9868.2007.00593.x.

[7] Guo C, Pleiss G, Sun Y, Weinberger K Q. On Calibration of Modern Neural Networks. ICML, 2017.

[8] Zhang Z, Han Y, Zhang Z, Liu Y, Zheng J, Sun Z-T. AdSpectorX: A Multimodal Expert Spector for Covert Advertising Detection on Chinese Social Media. SocialMeta '24, 2024. DOI: 10.1145/3698387.3700001.

[9] Sun C, Vekaria Y, Shafiq Z, Nithyanand R. Turning Trust to Transactions: Tracking Affiliate Marketing and FTC Compliance in YouTube's Influencer Economy. ICWSM, 2026. DOI: 10.1609/icwsm.v20i1.42748.

[10] Wojdynski B W, Evans N J. The Covert Advertising Recognition and Effects (CARE) Model: Processes of Persuasion in Native Advertising and Other Masked Formats. International Journal of Advertising, 2019. DOI: 10.1080/02650487.2019.1658438.

[11] Kim D Y, Kim H-Y. Influencer Advertising on Social Media: The Multiple Inference Model on Influencer-Product Congruence and Sponsorship Disclosure. Journal of Business Research, 2020. DOI: 10.1016/j.jbusres.2020.02.020.

[12] Kim S, Jiang J-Y, Nakada M, Han J, Wang W. Multimodal Post Attentive Profiling for Influencer Marketing. WWW, 2020. DOI: 10.1145/3366423.3380052.

[13] Bavaresco A, Testoni A, Fernández R. Don't Buy it! Reassessing the Ad Understanding Abilities of Contrastive Multimodal Models. ACL (Short Papers), 2024. DOI: 10.18653/v1/2024.acl-short.77.

[14] Bertaglia T, Heisig L, Kaushal R, Iamnitchi A. InstaSynth: Opportunities and Challenges in Generating Synthetic Instagram Data with ChatGPT for Sponsored Content Detection. ICWSM, 2024. DOI: 10.1609/icwsm.v18i1.31303.

[15] Nakshatri N S, Caplan E, Pujari R, Goldwasser D. TAIGR: Towards Modeling Influencer Content on Social Media via Structured, Pragmatic Inference. ACL, 2026. DOI: 10.18653/v1/2026.acl-long.1868.

[16] Zhang X, Liu Y, Wang J, Hu Z, Chen X, Yan R. SAGraph: A Large-Scale Social Graph Dataset with Comprehensive Context for Influencer Selection in Marketing. SIGIR, 2025. DOI: 10.1145/3726302.3730334.

[17] Saha D, Hasan M R, Mueen A. Followers Tell Who an Influencer Is. WWW (Companion), 2023. DOI: 10.1145/3543873.3587576.

[18] Joshi N, Spezzano F, Green M, Hill E. Detecting Undisclosed Paid Editing in Wikipedia. WWW, 2020. DOI: 10.1145/3366423.3380055.
