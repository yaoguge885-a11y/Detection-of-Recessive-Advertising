# ACM 会议与 Short Paper 参考

**检索日期：** 2026-10-29。时间窗定义见上级 [README](../README.md)。本目录独立于项目主题。

## 近一年 / 近三个月的会议与投稿机会

| 会议 / track | 时间状态 | Short paper 相关性 | 官方信息 |
| --- | --- | --- | --- |
| The Web Conference 2027 Resource Track | 投稿截止 2026-12-17，落在未来三个月；截至检索日尚未截止 | 不是 short-paper track；官方名称为 Resource Paper。上限 4 页，含参考文献 | [征稿与格式](https://www2027.thewebconf.org/resource-submissions/) |
| ACM Multimedia 2026 | 会议 2026-11-10 至 11-14，未来三个月内 | ACM 多媒体旗舰会议；本次可访问的官网首页确认会议时间与主题，但未能核实 short-paper track 的规则，因此不推断其存在或页数 | [会议官网](https://2026.acmmm.org/) |
| CHI 2026 Extended Abstracts | 论文集 2026-04-13 发布，近一年内 | Extended Abstracts 包含 Late-Breaking Work 等类别；这是扩展摘要论文集，不等同所有类别均为 short paper | [论文集](https://dl.acm.org/doi/proceedings/10.1145/3772363) |
| ACM/IEEE SenSys 2026 | 论文记录于 2026-05-10 公开，近一年内 | 论文题名和论文集元数据明确标为 Short Paper；适合作为近期短稿实例 | [论文集 DOI](https://doi.org/10.1145/3774906) |

## WWW 2027 Resource Track：你给出的重点页面

官方页面将其定义为独立于常规学术 track 的 Resource Track。投稿说明如下：

- **篇幅/版式：** 英文、ACM 双栏格式，最多 4 页且包括参考文献；建议 LaTeX `\documentclass[sigconf, screen, review]{acmart}`。提交单个 PDF。
- **作者与评审：** 非匿名，列出作者和单位；Resource Committee 同行评审，single-blind。
- **资源访问：** 提供稳定访问地址和明确的开源/开放数据许可，配套文档。数据资源需向审稿人开放完整数据以便核查质量、创新性、标注和复现；软件/工具还需可运行 demo 与 quick start。
- **可持续性：** 鼓励说明维护、版本管理、治理和长期可用计划。
- **伦理说明：** 要覆盖适用的数据来源/采集合规、隐私脱敏、许可与版权、偏差和误用风险，以及合成/LLM/自动标注数据的限制。
- **日期：** 投稿 2026-12-17；reviews due 2027-01-13；通知 2027-01-20；camera-ready 2027-02-17（AoE）。

**称谓提醒：** 虽然 4 页篇幅接近很多会议的短稿，官方 Track 名称是 Resource Track，接收稿件称 Resource Paper；投稿时应使用官网术语，不应把它当作 ACM 通用 short-paper 规范。

## ACM 模板要点

ACM 官方模板页说明，会议论文通常使用 `acmart` 的 `sigconf` proceedings 模式；但具体会议可能指定不同 review/final 模式、页数和流程。ACM 不存在一个跨会议统一的 short-paper 页数规则。

- [ACM Proceedings Template 官方页](https://www.acm.org/publications/proceedings-template)：LaTeX `acmart` 主模板，当前页面列出 2026-06-28 更新的 v2.20；会议 proceedings 通常用 `sigconf`。
- ACM 模板禁止通过替换字体或调整页边距压缩篇幅；最终以该届 CFP 的格式、引用、匿名、页数和 production 流程为准。
- [ACM 官方 Overleaf 模板入口](https://www.overleaf.com/gallery/tagged/acm-official)

## 近期论文与范例

### 明确标为 Short Paper 的近期实例

**The Starlink Robot: A Platform and Dataset for Mobile Satellite Communication**，Boyi Liu 等，ACM/IEEE SenSys 2026 Short Paper，论文集记录页 683-689。

- [ACM DL 论文页 / DOI](https://doi.org/10.1145/3774906.3800503)
- [ACM/IEEE SenSys 2026 论文集 DOI](https://doi.org/10.1145/3774906)
- 元数据公开日期：2026-05-10；当前窗口内。DOI 的正式记录可核验题名、作者、会议和页码。
- 阅读时建议关注：题名直接说明资源与使用场景；平台和数据集作为贡献对象；短稿应把系统/资源构成、评估证据和可用性说明压缩成一条清楚的论证线。

另一篇同一会议、明确标为 Short Paper 的实例：**Short Paper: EarSleeve: Transforming Everyday Earphones into a 12-Lead ECG Sensing Platform**，Junxi Xia 等，页 615-621，DOI [10.1145/3774906.3802785](https://doi.org/10.1145/3774906.3802785)。

### 扩展摘要示例（类别不同，作为短篇表达参考）

**Architects at CHI**，Mafalda Gamboa 等，CHI 2026 Extended Abstracts，3 页。

- [论文 DOI](https://doi.org/10.1145/3772363.3778785)
- [CHI EA 2026 论文集](https://dl.acm.org/doi/proceedings/10.1145/3772363)
- 这是 Extended Abstract，不应与常规 CHI full paper 或 WWW Resource Paper 混为一谈。适合观察如何用有限篇幅说明设计问题、研究视角与相关依据。

## 五篇短稿结构样例

以下五篇均来自 ACM/IEEE SenSys 2026，ACM DL 论文题名明确标注为 **Short Paper**，发布时间在近一年窗口内。ACM DL 页面提供摘要、正文目录和部分全文/补充材料，可直接用来观察结构。请注意这些实例的页数并不相同：ACM 的 short-paper 标签不等于统一页数；页数必须按具体会议、track 和最终 PDF 分别判断。

| # | 论文 | 页码 | 结构类型 | 建议重点 |
| --- | --- | ---: | --- | --- |
| 1 | [The Starlink Robot: A Platform and Dataset for Mobile Satellite Communication](https://dl.acm.org/doi/10.1145/3774906.3800503) | 683-689 | 平台/数据集；7 页 | 引言把研究缺口、平台和数据贡献连起来；随后依次写相关工作、系统设计、数据集、初步发现、研究机会与结论。适合看资源稿如何把工具描述和初步实证压在同一篇短稿中。 |
| 2 | [Short Paper: EarSleeve: Transforming Everyday Earphones into a 12-Lead ECG Sensing Platform](https://dl.acm.org/doi/10.1145/3774906.3802785) | 615-621 | 系统/硬件与用户评估；7 页 | 目录为 Introduction → ECG Background → Design → Evaluation → Related Work → Conclusion。重点看如何先给出设计原理，再解释硬件和用户研究，并在讨论中收紧适用边界。 |
| 3 | [Short Paper: Towards Real-Time ECG and EMG Modeling on μNPUs](https://dl.acm.org/doi/10.1145/3774906.3802787) | 636-645 | 算法/嵌入式系统；10 页 | Introduction → Related Work/Background → Design → Experimental Setup → Results → Conclusion，附消融与参数配置。适合观察方法贡献如何同时用任务指标和硬件延迟/内存/功耗支撑。 |
| 4 | [Short Paper: Simulation-Based Performance Characterization of Common NOR Flash File Systems](https://dl.acm.org/doi/10.1145/3774906.3802793) | 1171-1178 | 工具/基准与性能研究；8 页 | Introduction → 系统背景 → 模拟器 → 多维评估 → Related Work → Discussion/Conclusion。重点看验证模拟器、说明工作负载、报告异常发现和限制如何形成连贯证据链。 |
| 5 | [Short Paper: Towards Algorithmically Grounded Embedded AI Models](https://dl.acm.org/doi/10.1145/3774906.3800495) | 478-487 | 概念框架/方法与案例；10 页 | 先定义框架和挑战，再用两个案例分别说明构建与评估，之后讨论、相关工作、结论和未来问题。适合观察概念稿怎样避免只提出口号，而用具体任务和失败定位示例支撑主张。 |

**阅读顺序建议：** 先读 1（资源/平台），再读 2 或 3（系统/方法），最后读 4（仿真与比较评估）和 5（概念框架）。第一轮先读摘要、引言末尾贡献点、各级标题、结果图表和讨论/结论；第二轮再读实验设计与局限。ACM DL 可用在线阅读器或页面所列开放版本阅读，本文档不复制论文正文。

## 写作提炼

1. **先给单一贡献主张。** 开头尽快交代资源/系统解决什么问题、面向谁、为什么现有资源不够；避免用短稿篇幅铺很长的领域史。
2. **贡献与证据匹配。** 资源稿提供数据覆盖、标注质量、许可、访问方式和复现证据；系统稿说明核心机制、目标用户和实际可用性。不要把“发布了资源”本身当成全部结果。
3. **用可核验信息代替宣传句。** 用数据规模、任务、对照、误差分析、案例或用户验证支撑价值主张；结果不充分时收窄结论并说明限制。
4. **篇幅服务于读者决策。** 保留定义、最相关工作、方法/资源设计、关键评估、限制和结论；将大表格、完整协议等放到允许的补充材料或长期资源链接中，但正文必须自洽。
5. **模板不是写法。** `sigconf` 仅说明版式；具体 track 的评审匿名性、页数以及参考文献是否计入必须单独检查。

## 官方来源

- [WWW 2027 Resource Submissions](https://www2027.thewebconf.org/resource-submissions/)
- [ACM Primary Article Template](https://www.acm.org/publications/proceedings-template)
- [ACM Multimedia 2026 官网](https://2026.acmmm.org/)
- [CHI 2026 Extended Abstracts 论文集](https://dl.acm.org/doi/proceedings/10.1145/3772363)
- [SenSys 2026 论文集](https://dl.acm.org/doi/proceedings/10.1145/3774906)
