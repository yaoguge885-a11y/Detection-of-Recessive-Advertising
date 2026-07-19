# 交接文档 · 隐性广告识别项目（大创）

> 写给一个完全没有上下文的新会话。读完这份就能接手，不用再翻旧记录。
> 最后更新：2026-07-19

---

## 一、我们在做什么

**项目**：华东理工大学 信息科学与工程学院 的大学生创新创业训练计划（大创）项目——
**《融合多模态行为特征与文本推断的隐性广告识别》**。

**一句话目标**：识别社交媒体帖子是「明广 / 暗广 / 非广」三类里的哪一类。暗广 = 没标注广告、但有明显导购意图/软广话术的内容。

**技术路线的关键转向**：申报书里原本的方案是传统流水线（BERT 文本 + CNN/YOLO 视觉 + BERTopic 主题漂移 + XGBoost/MLP 二分类）。经过调研，我们**转向了 LangGraph 多智能体架构**（Supervisor 调度 + NLP/视觉/行为 专家智能体 + RAG 法规库 + Judge 聚合 + 人在环 HITL）。传统流水线（尤其 XGBoost）保留作为对照基线，用于论文的消融/对比实验。

**团队**：4 名本科二年级学生（用户称在新加坡 UC 大学读 Information Engineering；申报书上写的是华东理工大学，以申报书为准）。角色分工代号：
- **L**（负责人/架构）= 姚家辉
- **N**（NLP）= 江灵均
- **V**（视觉）= 叶泽楷
- **D**（数据/评估）= 王一帆（商学院金融+计算机双学位）
- 指导老师：胡庆春 副教授（NLP 方向）

**时间**：约 6 个月（2026-07 起步）。暑假可全职，秋季学期半负荷，期末几乎停摆，寒假可全职。计划表已按校历排好产能。

**最终产出目标**：论文 + 软件著作权 + 竞赛 + 一个能演示的 Web 应用。

---

## 二、已经完成了什么

### A. 两份核心交付文档（在本文件夹根目录）
1. **`隐性广告识别项目_分阶段计划表.md`**
   —— P0~P6 分阶段计划、里程碑 M0~M6 及其完成标准（DoD）、校历产能表、甘特概览、MVP 优先级阶梯（L0必做/L1应做/L2可做/L3冲刺）、每周节奏（周一站会/周五 demo+复盘/双周见导师）。
2. **`隐性广告识别项目_说明书.md`**
   —— 战略说明（为何从 XGBoost 转 LangGraph）、目标架构 ASCII 图、推荐技术栈、5 份参考资料各自的用途、P0~P6 每阶段的「目标/先学/工作路线/工具库/常见坑/完成标准」、数据与标注规范（三元标签、Cohen's κ≥0.6、训练/测试集不允许同博主重叠）、评估方案与论文提纲、风险表、协作规范、以及分类关键词清单（A~H 八大类）。
3. **`implicit-ad-agent/docs/ADR.md`**（2026-07-12 初稿，任务 0.2）
   —— 10 条架构决策：ADR-001 LLM 分档用模（DeepSeek-chat 主力 / Qwen-VL 视觉 / 便宜模型路由，厂商无关端点）、002 LangGraph 编排、003 Chroma + bge-small-zh-v1.5、004 Streamlit 前端、005 FastAPI + 腾讯云 CVM、006 LangSmith（含数据脱敏红线）、007 原生 @tool（FastMCP=L2）、008 降级阶梯 + 四个降级决策点（M1/M3/M4/M5）、009 Python 3.10 环境、010 json_mode 结构化输出策略。**待 4 人签字**，签字后 M0 的 ADR 项即验收。计划表/说明书已同步更新交叉引用。

> 这两份是给全组人看的"作战地图"，任何新决策都应回头对照它们、必要时更新它们。

### B. 项目起步骨架（在子目录 `implicit-ad-agent/`）
一个**最小可运行的 LangGraph 起步骨架**，已实测跑通。结构：

| 路径 | 作用 | 状态 |
| --- | --- | --- |
| `impad/hello_graph.py` | 零 Key 规则占位图（不花钱、不需 API Key） | ✅ 实测跑通 |
| `impad/graph.py` | **多智能体图装配**：Supervisor→专家→Judge（2026-07-12 从单体裂变） | ✅ 零 Key 实测跑通（NLP 无 Key 自动降级规则） |
| `impad/agents/` | supervisor（调度+条件路由）/ nlp_agent（LLM+规则降级）/ vision_agent（占位）/ behavior_agent（占位规则）/ judge（加权聚合+反思质询） | ✅ 骨架就绪，视觉/行为待填肉（P2/P3） |
| `impad/tools/keywords.py` | 明广标识 + 软广信号词清单（规则降级共用） | ✅ |
| `impad/state.py` | 共享状态 `AdCheckState`（已加 `plan`/`agent_votes`） | ✅ |
| `impad/llm.py` | 厂商无关 LLM 客户端（OpenAI 兼容端点） | ✅ |
| `impad/config.py` | 读 `.env` 的集中配置 | ✅ |
| `app.py` | FastAPI，`GET /health` + `POST /analyze` | ✅ /health 实测 200；/analyze 需配 Key |
| `run_demo.py` | 一键跑样本（`--llm` 切真实 LLM） | ✅ 实测跑通（含 UTF-8 修复） |
| `samples/sample_posts.json` | 3 条固定样本（暗广/明广/非广各一） | ✅ |
| `tests/test_smoke.py` | 冒烟测试（零 Key） | ✅ 通过 |
| `tests/test_agents.py` | 多智能体路由/聚合/全图测试（零 Key，monkeypatch 掉 Key 防误调 LLM） | ✅ 通过 |
| `requirements.txt` / `pyproject.toml` | 依赖（含 pytest） | ✅ |
| `.env.example` | LLM/LangSmith 配置模板 | ✅（用户尚未 cp 成 .env 填 Key） |
| `.gitignore` | 已排除 .env / .venv / __pycache__ 等 | ✅ |
| `.python-version` | `3.10`（本机 Python 3.10.11） | ✅ |
| `README.md` | 快速开始 + LangSmith 看轨迹步骤 | ✅ |

### B+. 平行实现的代码移植（2026-07-13）
桌面另有一版同课题的未完成实现 `hidad_detect_agent-unfinished--main`（评估见其中的
`移植评估与方案.md`），确认三块可移植：① 关键词清单+6维权重、② 视觉模块(YOLO+OCR)、
③ ERNIE 训练管线做论文对照基线。**已完成块①与块②，仅剩块③**：

#### 块① 关键词清单 + 6 维权重（2026-07-13）

- `impad/tools/keywords.py`：从十几个词扩成 6 组分类词表（促销/价格/紧迫/品牌/行动/自然），
  新增 `compute_keyword_weights(text)`（确定性算 6 维 0~1 权重，无需 LLM）、`ad_pressure()`、
  `summarize_weights()`。明广标识/软广词表也一并扩充。
- `impad/agents/nlp_agent.py`：prompt 融合三分类判据（明广/暗广/非广定义更清晰，仍保 json_mode+英文字段）；
  LLM 与规则降级两条路径**都产出** keyword_weights；规则降级新增"导购压力"兜底层
  （未命中软广词但 promotion/price/urgency/action 均值≥0.5 且盖过自然表达 → 判暗广）。
- `impad/agents/judge.py`：证据链与报告里加入 6 维特征参考（不改加权投票数学，保证原测试稳定）。
- `impad/state.py` 加 `keyword_weights` 字段；`app.py` 的 `/analyze` 响应透出该字段；
  `hello_graph.py` 改为复用共享词表并展示权重（顺手补了 `__main__` 的 UTF-8 reconfigure，见坑#1）。
- 新增 `tests/test_keywords.py`（7 项）。零 Key 与真实 LLM 均实测跑通。
- **关键设计决定**：6 维权重刻意在代码里确定性计算，不让 LLM 吐嵌套 JSON——
  避开国产端点复杂结构化输出不稳的坑（同坑#4），且规则降级路径也能有同样特征。

#### 块② 视觉专家：物体检测 + OCR + 焦点（2026-07-13）
- `impad/tools/vision.py`（新）：从桌面 `pics/yolo_detector.py` 精简移植。YOLO11 物体检测 + EasyOCR
  中英文 + 加权焦点。**精进三点**：① 去掉标注绘图（智能体只需结构化数据，不需画框图，省 ~150 行与 PIL 字体依赖）；
  ② 所有重依赖（cv2/numpy/ultralytics/easyocr）改**带守卫的惰性导入**，缺依赖时 import 不报错、
  `vision_available()` 返回 False；③ 模型模块级缓存，只加载一次。
- `impad/agents/vision_agent.py`（重写）：占位 → 真实分析。**核心是把 OCR 抠出的图内文字回灌关键词规则**
  （复用块①的 keywords），抓"广告词印在图上、文本专家看不见"的暗广。判定逻辑抽成纯函数
  `vote_from_findings`（无重依赖，可零依赖单测）。四级降级：无图 / 缺依赖 / 文件缺失 / 推理异常，
  都投 confidence=0 空票并说明原因，绝不拖垮全图（ADR-008）。
- `impad/state.py` 加 `vision_findings`；`supervisor.py` 改为 `image_path` 或 `image_url` 任一即调度视觉；
  `app.py` 的 `PostIn` 加 `image_path` 字段、`/analyze` 透出 `vision_findings`；
  `run_demo.py` 加 `--image path` 带图跑多智能体图。
- 新增 `requirements-vision.txt`（ultralytics/easyocr/opencv，约 2~3GB，可选）、`samples/images/`（2 张测试图）。
- 新增 `tests/test_vision.py`（9 项）。**全套 `pytest` 21 项通过**。
- **实测状态**：降级路径已实测（本机未装视觉依赖，`run_demo.py --image` 正确降级、全图跑通）；
  **真实视觉路径尚未在本机跑过**——需先 `pip install -r requirements-vision.txt`（2~3GB）。
  代码是桌面版已实测逻辑的忠实移植，装好依赖后叶泽楷（V）可直接在此基础上做图文一致性（P2）。

### C. 已解答的用户问题（不用重复讲）
- Git/GitHub 基本操作、关联远程仓库
- Pull Request 用法
- 一行命令把整个文件夹 push 到某分支
- PR 合并"看似删掉了 main 原有文件"的根因排查与修复（真正原因通常是新分支历史里本就没那个文件，不是 merge 会删文件）
- 帮用户找了 3 个匹配的开源参考项目（含 MANA：https://github.com/MANA-2026/MANA）
- 做成软件/浏览器插件/网站的取舍
- 部署选型：**推荐腾讯云普通服务器，不用 AWS Lambda**（Lambda 有超时/无状态/GPU/国内区摩擦问题）；Docker 留到 P5 部署阶段再上，前期本地 venv 即可
- LangSmith 的用途与是否必须（答：非必须，但强烈推荐——看轨迹/调试/Dataset+Evaluation）
- `http://127.0.0.1:8000/docs` 是什么（FastAPI 自动生成的 Swagger 交互文档）

### D. 记忆文件（在 `.claude/.../memory/`）
- `implicit-ad-detection-project.md` 已记录项目身份/团队/转向/时间线/交付物
- `MEMORY.md` 索引已更新

---

## 三、当前卡在哪 / 下一步

### P2 · L（Owner）工具舱进展（2026-07-19）

L 已按 `docs/P2_工具舱模型工具化_执行指南.md` 完成目前可独立完成的 Owner 工作：

- 新增公共契约 `impad/tools/contracts.py`：统一四态状态、证据结构和结果信封。
- 新增 4 个“纯 core + LangChain @tool 薄适配”工具：`analyze_text_intent`、`sentiment_curve`、`topic_drift`、`comment_anomaly`。
- 新增 `impad/tools/registry.py`，真实记录 4 个 L 工具 ready、3 个 V 视觉工具 pending，不虚报 M2。
- 新增 5 份测试文件；2026-07-19 全套回归 **36 passed**（原 21 + 新 15），零 Key、零联网、无视觉重依赖。
- 新增 `run_tools_demo.py` 固定零 Key 演示，以及 `docs/tool_catalog_v1.md` 的接口、限制、调用示例和替换点。

关键实现边界：文本意图复用现有关键词唯一事实来源；情绪将普通正负情感与焦虑/紧迫分离；主题漂移只读当前时间之前的历史，当前用字符 bigram 余弦作为明确标注的降级实现；评论少于 5 条、历史少于 3 条均返回 `skipped` 而不是 0 分。

**P2/M2 尚未完成，当前 4/7 ready。** 下一交接点是 V 实现 `ocr_extract`、`detect_logo_product`、`image_text_consistency`，并由 V 评审 L 四工具的输入输出/证据/降级/测试；L 随后评审视觉接口、把 7 工具纳入注册表并做最终 M2 回归。真实视觉 integration 和 30 对图文一致性质量小测仍由 V 执行。

**当前没有硬卡点。** 骨架已跑通，用户正在自己上手体验 `/docs` 页面。

**下一步计划**（按《说明书》P0→P6 推进，短期最该做的）：
0. ADR 拿给 4 人签字确认（初稿已完成，见 `implicit-ad-agent/docs/ADR.md`），签完 M0 即可关口。
1. 开始搭数据与标注流程（D 主导）：三元标签、标注手册、Cohen's κ 一致性校验。
2. ~~把 `graph.py` 扩成多智能体图~~ ✅ 已完成（2026-07-12）：Supervisor+3专家+Judge 骨架就位，视觉/行为是占位，待填肉。
3. 视觉专家（P2）：~~OCR + 物体 + 焦点骨架~~ ✅ 已完成（块②，2026-07-13，见 B+）。
   下一步是**图文一致性**（文案痛点 vs 图片焦点/物体的反差）——在 `vision_findings` 基础上做，V 主导；
   并需 `pip install -r requirements-vision.txt` 后实跑真实视觉路径验证。
   行为专家（P3）：EMA 偏好偏移 + Chroma 情景记忆，仍是占位待填。
   ~~关键词清单+6维权重（块①）~~ ✅ 已完成（2026-07-13，见 B+）。
4. **论文对照基线（块③，待做）**：从桌面 `hidad_detect_agent-unfinished--main/text/train/` 搬文件到仓库根目录
   `baseline/`，加 `requirements.txt`（paddlepaddle 生态，独立 venv）和 `README.md`。
   桌面版已有实测结果（acc≈90.5%，macro-F1≈0.90，54 组超参实验）；`build_balanced_dataset.py` 是
   P1 标注阶段 D 需要的构建工具。搬文件本身不依赖标注数据，**半天内可完成**；真正训练等 P1 数据就绪。
   详见 `implicit-ad-agent/README.md`「论文对照基线（待做：块③）」小节。
4. 逐步接入：Chroma（RAG 法规库）、XGBoost 对照基线；Judge 权重（现为手工 nlp 0.6/vision 0.25/behavior 0.15）P4 用验证集误判率校准。

> 接手时：先读上面 B 两份 .md，再看 `implicit-ad-agent/README.md`，就能对齐。

---

## 四、踩过的坑，绝对不要再踩

1. **Windows 终端中文乱码（GBK vs UTF-8）**
   - 现象：`python run_demo.py` 打出 "ʹ����ɱ�ռλͼ" 之类乱码。
   - 根因：Windows 控制台默认 GBK，与 UTF-8 stdout 冲突。
   - **已永久修复**：`run_demo.py` 顶部加了 `sys.stdout.reconfigure(encoding="utf-8")`。**新写任何会打印中文的脚本都要照抄这一段**，不要让用户去记 `PYTHONUTF8=1` 环境变量。

2. **`antiword` 解 .doc 出问号乱码**
   - 必须加映射参数：`antiword -m UTF-8.txt <file>`，否则中文全变 `?`。

3. **`pdftoppm` 未安装** —— Read 工具渲染 PDF 页面会失败。
   - 绕过：直接用 Python 的 `fitz`（PyMuPDF）抽文本。

4. **`with_structured_output` 的坑**
   - `graph.py` 里用的是 `method="json_mode"` 且 **prompt 里强制英文字段名**（verdict/confidence/evidence）。这是有意为之：DeepSeek 等国产端点对默认 function-calling 结构化输出支持不稳，json_mode + 显式字段约束更稳。**不要随手改回默认结构化模式**，否则国产 Key 可能报错。

5. **`/analyze` 返回错误 ≠ 代码坏了**
   - 没配 `.env` Key 时，`/analyze` 走真实 LLM 会失败，这是**预期**。别去"修" app.py。
   - 想零成本验证逻辑，用 `hello_graph`（`python run_demo.py` 不带 `--llm`）或跑 `pytest`。

5b. **视觉专家投 `confidence=0` 的空票 ≠ 代码坏了**
   - 没装 `requirements-vision.txt` 时，`vision_available()` 返回 False，视觉专家自动降级投空票，
     Judge 会忽略它。这是**预期降级**（ADR-008），不是 bug。想让它真出结果就装那份可选依赖（2~3GB）。
   - 另注：`from impad.agents import supervisor` 拿到的是**函数**不是模块（`__init__` 里 re-export 了），
     写测试时直接 `supervisor({...})`，别写 `supervisor.supervisor(...)`。

6. **pytest 找不到包**
   - `pyproject.toml` 里已配 `[tool.pytest.ini_options] pythonpath = ["."]`，这样才能 import `impad`。别删。
   - pytest 已写进 `requirements.txt`，别再当它是可选。

7. **本机没有 `uv`，也没有 `py -3.11`**
   - 只有 `C:\Python310\python.exe`（3.10.11）。用 `python -m venv .venv` 建环境，别指望 uv。

8. **PR 合并"删文件"的误解**
   - 用户曾以为"合并含不同文件的分支会删掉 main 原文件"。真相：正常 merge 不动未触碰的文件；真删了几乎一定是**新分支历史里本来就没那个文件**（比如在新文件夹里重新 `git init` 建的分支，而非从最新 main 切出来的）。
   - 正确姿势：永远先 `git pull` 更新 main，再 `git checkout -b 新分支`。

9. **交付原则：不要在终端里长篇输出交付内容**
   - 用户明确要求过"不要在终端内输出"——交付物一律写成文件（.md / 代码），终端只给简短的"怎么运行/怎么看结果"说明。

10. **`Fatal error in launcher`＝Windows venv launcher exe 把 Python 路径编码坏了**
    - 现象：激活了 venv 后跑 `uvicorn app:app --reload`（或 `pip`/`pytest`），报 `Fatal error in launcher: Unable to create process using '...\?????\...'`。
    - 根因：`.venv\Scripts\uvicorn.exe`（以及 pip.exe、pytest.exe 等）在 venv 创建时把 Python 绝对路径硬编码进去；路径含中文字符或 venv 被移过位置时，这个 exe 就坏掉了。
    - **修**：用 `python -m uvicorn`（模块方式）完全绕过 launcher exe，效果一样，永久有效。同理：`python -m pip install …`、`python -m pytest`。
    - **项目内所有地方统一用 `python -m <命令>` 的形式**，不要用裸命令 `uvicorn`/`pip`/`pytest`，避免同类问题。

11. **`No module named 'langgraph'`＝venv 没激活，不是没装依赖**
    - 现象：PowerShell 里 `python run_demo.py --llm` 报 `ModuleNotFoundError: No module named 'langgraph'`。
    - 根因：直接敲 `python` 用的是系统 `C:\Python310\python.exe`，依赖装在 `.venv` 里，两者不是一个环境。
    - 修：先激活 venv。**PowerShell 的激活脚本是 `Activate.ps1`**（不是 `activate`）：`.venv\Scripts\Activate.ps1`。
      若报"未数字签名/禁止运行脚本"，当前窗口临时放行：`Set-ExecutionPolicy -Scope Process RemoteSigned`，再激活。激活成功前面会有 `(.venv)`。
    - 懒人版：不激活，直接点名 `.venv\Scripts\python.exe run_demo.py`。README「快速开始」已补详细步骤。

---

## 五、关键资料索引（本文件夹内的原始调研材料）

| 文件 | 用途 |
| --- | --- |
| `面向隐性广告识别的智能体（Agent）架构重构与多模态协同演进路径深度研究报告.md` | 转向 Agent 架构的主论证，目标架构来源 |
| `大学生创新创业训练计划项目申报书-...doc` | 项目身份/团队/原始技术方案/预算/时间线 |
| `2508.10143v1.pdf` | MCP 编排多智能体检测虚假信息（架构模板，F1=0.964） |
| `2603.20351v1.pdf` | MANA：清华，移动端广告检测多模态智能体（**有开源代码**） |
| `MemGPT Towards LLMs as Operating Systems.pdf` | 分层记忆设计基础 |
| `基于一对多关系的多模态虚假新闻检测.pdf` / `多模态混合注意力机制的虚假新闻检测研究.pdf` | 图文一致性/跨模态融合技巧 |

---

## 六、技术栈速记

LangGraph（StateGraph/节点/边/compile/invoke） · LangChain + langchain-openai（OpenAI 兼容端点，DeepSeek/Qwen/OpenAI 可互换，改 base_url+model 即可） · Pydantic 结构化输出 · FastAPI + uvicorn · LangSmith（轨迹/Dataset+Evaluation） · Chroma（后续，向量库） · 评估：P/R/F1/AUC-ROC + 消融 + Cohen's κ。
