# 隐性广告识别：证据驱动的多智能体分析系统

本项目面向社交媒体内容，结合文本、图像、评论与创作者历史，判断帖子属于 **明广 / 暗广 / 非广**，并输出可以回溯到原始内容与法规来源的结构化证据链。

项目由4名开发者首先作为内部研究工具使用，最终以论文、答辩演示和可直接下载运行的 GitHub 开源工程交付。最低产品形态是网页端；浏览器插件是完成网页端后的冲刺形态。

## 项目定位

项目同时追求三类成果，但彼此边界明确：

- **研究主线**：CreatorShift——建模创作者长期内容偏好及目标帖的纵向变化，验证历史信息是否真正提升暗广识别。
- **Agent工程主线**：LangGraph、Function Calling、MCP、A2A与RAG形成可观测、可降级、可替换的完整协作链。
- **产品主线**：网页端支持手工输入、JSON/文件导入和平台URL，展示证据画布、创作者变化时间线、法规引用与Agent运行轨迹。

传统文本/视觉/XGBoost流水线继续保留为论文基线，不再作为最终系统架构。

## 标签与输出口径

正式金标仍是三类：

| 标签 | 定义 |
| --- | --- |
| 明广 | 存在商业推广意图，且发现明确、可核查的广告/赞助/合作披露 |
| 暗广 | 存在商业推广意图；在采集信息充分的前提下，没有发现明确披露 |
| 非广 | 没有足够证据支持商业推广意图 |

`需复核`、`uncertain`、`out_of_scope` 是数据治理或运行状态，不是第四个正式金标。系统必须把“没有发现披露”与“因为页面缺失而无法确认披露”区分开。

## 目标架构

```text
手工输入 / JSON / URL / 浏览器插件
                  │
            PlatformAdapter
                  │
        PostRecord + CaptureStatus
                  │
          Capability Planner
                  │
          Function Calling
            ┌─────┴─────┐
            │           │
      本地专家模式   A2A分布式模式
            │           │
            └─────┬─────┘
                  │
            MCP Tool Gateway
      ┌───────────┼────────────┐
      │           │            │
   文本工具     视觉工具    历史/评论工具
      └───────────┼────────────┘
             EvidenceBundle
                  │
      商业意图聚合 + 披露证据判断
                  │
         Calibrated Judge / 复核门
                  │
       明广 / 暗广 / 非广 / 需复核
                  │
       法规与平台规则 RAG（带引用）
                  │
             VerdictReport
```

协议分工：

- **Function Calling** 是Agent默认的工具选择与参数生成机制。
- **MCP** 统一暴露现有工具和知识服务；本地调用与MCP调用复用同一实现。
- **A2A** 是正式交付的可切换分布式专家模式，不替代默认本地模式。
- **RAG** 为结论提供法规和平台规则引用，不直接参与训练标签，也不把检索结果当分类真值。

## 当前事实快照（2026-07-26）

| 模块 | 当前状态 | 下一步 |
| --- | --- | --- |
| LangGraph P2.5主链 | `PostRecord → Capability Plan → 七工具组 → EvidenceBundle → 充分性门 → Judge`可运行 | P3拆统一分析服务并接知识层 |
| P2工具舱 | 7/7工具ready；严格受限Function Calling、运行级预算与LocalToolGateway已接主图 | P3实现MCPToolGateway与本地回落 |
| 视觉环境 | YOLO/EasyOCR与RTX 4060 Laptop GPU实测通过 | 保持真实视觉测试显式opt-in |
| P1数据资产 | 远端最新P1已合入本地P2；含schema、30条合成样例和独立`data-tooling/` | 完成真实候选数据的合规、双标、κ与划分验收 |
| CreatorShift | 已有防未来泄漏的历史视图、mean/max/EMA基线和shift结果；行为组已接时间安全topic_drift | P4接真实历史特征、模型和校准 |
| RAG/MCP/A2A | 法规RAG离线基线和Detection MCP已实现；知识MCP、主图MCP回落和A2A尚未接入 | P3接知识/MCP，P5再建设A2A专家模式 |
| Web/API | FastAPI确定性P2.5起步接口存在 | P3拆正式API服务；P5再接URL与研究工作台 |

远端 [`P1-·-数据地基与标注规范`](https://github.com/yaoguge885-a11y/Detection-of-Recessive-Advertising/tree/P1-%C2%B7-%E6%95%B0%E6%8D%AE%E5%9C%B0%E5%9F%BA%E4%B8%8E%E6%A0%87%E6%B3%A8%E8%A7%84%E8%8C%83) 的最新提交 `6679671` 已通过合并提交 `98cb599` 进入本地P2。`data/schema/data_schema_v1.json` 是当前提交资产校验所使用的权威字段标准；`data-tooling/schema/data_schema_v1_1.json` 是数据工具舱中待走兼容评审的后续版本，二者不能混用。

本地零Key全量回归当前为 `227 passed, 2 skipped`，P2.5准入重点为`116 passed`。真实视觉、LLM和联网采集均是显式可选测试。

## P1数据地基

本次合并保留了两类入口：

- `data/` 与 `scripts/data/`：提交级schema、30条合成fixture及标准库校验器。
- `data-tooling/`：独立的数据采集、标注、隐私扫描、κ计算、金标构建和按博主划分工具舱。

在仓库根目录运行两个零Key校验入口：

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe scripts\data\validate_submission_assets.py
.\implicit-ad-agent\.venv\Scripts\python.exe data-tooling\validate_submission_assets.py
```

两者均应输出 `VALIDATION PASSED`、30条内容记录和30条补充标注。真实平台采集可能联网并涉及平台条款，不属于默认测试。

## 快速开始

项目主程序位于 `implicit-ad-agent/`。

```powershell
cd implicit-ad-agent

# 使用项目虚拟环境，避免Windows launcher和中文路径问题
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 默认回归：零Key、零联网
.\.venv\Scripts\python.exe -m pytest -q

# 运行本地样例
.\.venv\Scripts\python.exe run_demo.py

# 启动当前FastAPI接口
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

启动后打开：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

真实视觉集成测试默认跳过，需要在已安装视觉依赖和CUDA环境中显式运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m vision_integration -q
```

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `implicit-ad-agent/impad/agents/` | 当前专家Agent、Supervisor与Judge |
| `implicit-ad-agent/impad/tools/` | 7个独立工具、视觉上下文、工具契约与注册表 |
| `implicit-ad-agent/tests/` | 零网络默认回归与显式真实视觉测试 |
| `data/schema/` | 提交级权威数据JSON Schema |
| `data/synthetic/` | 仅用于schema与流水线冒烟的30条合成样例 |
| `scripts/data/` | 提交资产构造与校验入口 |
| `data-tooling/` | 独立采集、标注、迁移、隐私与数据质量工具舱 |
| `docs/隐性广告识别项目_说明书.md` | 目标架构、设计边界与验收原则 |
| `docs/隐性广告识别项目_分阶段计划表.md` | 阶段、日期、Owner、里程碑与降级策略 |
| `docs/现有代码修改大纲.md` | 从当前代码迁移到目标架构的文件级改造范围与短期顺序 |
| `HANDOFF.md` | 当前分支、已完成事实、风险与接手步骤 |

## 路线概览

1. **P1收口 + P2.5证据整合**：冻结schema握手，完成数据迁移、证据契约、Function Calling和现有7工具接入。
2. **P3证据型Agent MVP**：本地端到端报告、Chroma法规RAG、MCP工具服务与可观测轨迹。
3. **P4 CreatorShift研究**：纵向偏好变化、校准Judge、强基线与泄漏安全评估。
4. **P5产品与分布式模式**：网页端、小红书/B站URL适配、A2A专家模式。
5. **P6开源与论文**：完整实验、浏览器插件冲刺、复现文档、论文/答辩/软著材料。

## 工程原则

- 先稳定 `PostRecord → EvidenceBundle → VerdictReport`，再增加协议和界面。
- 缺失模态必须记为 `skipped/unavailable`，不能当作0分。
- 默认测试始终零Key、零联网；真实模型和真实平台测试必须显式opt-in。
- 工具、本地MCP适配和A2A专家不得复制业务逻辑。
- CreatorShift只读取目标帖之前的历史，train/dev/test按创作者隔离。
- 无可靠RAG证据时不生成法规引用；信息不足时允许拒绝分类并列出缺失项。
- 数据采集遵守来源条款、最小必要、脱敏与可追溯原则。

更完整的设计与执行顺序见 `docs/` 下的说明书、阶段计划和代码修改大纲。
