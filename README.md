
## 数据 Schema v2.0

标注层与内容层分离，通过 `post_id` 关联，保留两人独立原始判断。

### 内容记录结构（精简版）

```
post_id            → 标识（SHA-256 hash 前 24 位）
platform           → 平台标识（wechat_official_account / weibo_public_account / web_public）
blogger_id         → 博主标识（脱敏 hash）
published_at       → 发布时间（ISO 8601 +08:00，提取不到填 null）
title              → 标题（可为 null）
text               → 正文（含 <图片N> 标记）
media[]            → 媒体（ref, source_url, caption?, is_content?）
comments[]         → 评论（P1 为空）
blogger_history_refs[] → 同博主其他文章 post_id 列表
_collected         → 采集元数据（source_url, collected_at, collector）
```

### 缺失值规范

| 值 | 含义 |
|----|------|
| `null` | 未知 / 未采集 / 确实提取不到 |
| `""` (空串) | 已知为空（如纯图片帖无文本） |
| `[]` (空数组) | 已知无（如无图 / 无评论） |

> 时间字段统一使用中国标准时间 `+08:00`，ISO 8601 格式。

---

## 标注规范 v1.0

### 三元标签

| 标签 | 含义 |
|------|------|
| `明广` | 有明确的商业关系披露（如"广告""赞助""合作"标签） |
| `暗广` | 无披露，但通过话术、图片、转化引导等方式隐性推广 |
| `非广` | 无商业推广意图，纯粹的内容分享或信息性讲解 |
| `out_of_scope` | 不在研究范围内，单独过滤，不参与统计 |

### 七类证据编码

| 代码 | 证据名称 | 判定标准 |
|------|---------|---------|
| **D** | 明示商业关系 | 出现"广告""赞助""合作推广"等文字标签或平台商业推广标识 |
| **C** | 明确商业对象 | 全文围绕**单一**品牌/商品/店铺/型号/服务展开 |
| **P** | 劝服/促销话术 | 极端夸赞、限时限量、价格刺激、制造稀缺焦虑 |
| **A** | 转化动作 | 引导下单、扫码跳转、专属优惠码、"评论区扣1取链接" |
| **V** | 视觉商业证据 | 产品特写、品牌 Logo 大图、价格表/优惠券截图、销量数据图表 |
| **B** | 行为偏移 | 博主既往人设/主题明显不符（如军事博主突然推护肤品） |
| **M** | 评论异常 | 置顶购买链接/导流消息、格式雷同的赞美、统一队形"已买""求链接" |

### 判定流程

```
Step 1 ── 是否在研究范围内？
          ├── 否 → out_of_scope（结束）
          └── 是 → 继续
Step 2 ── 是否有 D（明示商业关系）且内容为推广？
          ├── 是 → 明广（结束）
          └── 否 → 继续
Step 3 ── 是否有 C（明确商业对象）？
          ├── 否 → 非广（大概率）（结束）
          └── 是 → 继续
Step 4 ── C 存在的情况下：
          是否有 P/A/V/B/M 中 ≥2 条独立证据？或是否有 A（直接转化动作）？
          ├── 是 → 暗广（结束）
          └── 否 → 继续
Step 5 ── 证据不足 → 非广；无法确定 → 人工复核
```

### 试标与仲裁

- 两人独立标注同一批样本 → 计算 **Cohen's κ**，目标 κ ≥ 0.6
- 只把规范缺口写入文档，**禁止**为提高 κ 而私下对齐答案
- 置信度 < 0.6 的样本自动进入复核队列
- 仲裁时展示两方标签和证据链，**不显示标注者姓名**

---

## 数据合规

所有数据来源必须在 `docs/data_compliance.md` 中登记，每条记录至少包含：

| 字段 | 说明 |
|------|------|
| `source_name` | 数据集或平台名称 |
| `source_type` | `public_dataset` / `manual_public_collection` / `authorized_export` |
| `terms_or_license` | 条款或许可证链接 |
| `checked_at` | 实际检查日期 |
| `allowed_use` | 允许用途 |
| `collection_method` | 采集技术手段 |
| `fields_collected` | 实际采集字段列表 |
| `risk` | 低/中/高及理由 |
| `decision` | 可用/限制使用/停用 |
| `owner` | 责任人代号 |

### 合规红线

- 条款不清楚时默认不采集，或降级为仅保留统计特征
- 含真实身份信息的原始内容**绝对不提交 Git**
- 仅抓取公开可访问页面，不使用登录/模拟登录绕过访问控制
- 控制请求速率，不对目标服务器造成高并发压力
- 脱敏原则：用户名、头像、手机号、微信号、精确地址、设备标识均须处理

---

## 爬虫流水线

### 环境准备

```powershell
cp .env.example .env
# 编辑 .env：ANONYMIZATION_SALT / OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL

pip install -r requirements.txt
playwright install chromium
```

### 全自动流水线（推荐）

```powershell
# 搜索 + 并发抓取（分文件、LLM 直分析 HTML、3 worker）
python scripts/data/run_full_pipeline.py `
  --mode sogou `
  --accounts-file data/accounts.txt `
  --output-dir data/run_outputs `
  --media-dir data/media `
  --use-llm `
  --max-articles 50 `
  --workers 3

# 断点续传
python scripts/data/run_full_pipeline.py `
  --mode sogou `
  --output-dir data/run_outputs `
  --media-dir data/media `
  --use-llm --workers 3 `
  --resume

# 清洗 + 去重
python scripts/data/normalize_and_deduplicate.py `
  data/run_outputs/anonymized_posts.jsonl `
  data/run_outputs/anonymized_posts_dedup.jsonl

# Schema 校验
python scripts/data/validate_schema.py `
  data/run_outputs/anonymized_posts_dedup.jsonl
```

### LLM 文本规范化

`--use-llm` 启用 HTML 直分析模式：DeepSeek 直接从原始 HTML 提取纯净正文 + 图片位置 + 图片标注。

| 正则模式（默认） | LLM 模式（--use-llm） |
|-----------------|---------------------|
| 黑名单 + 规则清洗 | 语义理解，准确区分 UI vs 正文 |
| 免费、快速 | 消耗 API Token |
| `<图片N>` 标记不支持 | 自动插入 `<图片N>` 位置标记 |

---
# 隐性广告识别 · LangGraph 多智能体骨架

融合多模态行为特征与文本推断的隐性广告识别项目。
已从单体智能体扩成 **Supervisor + 专家(NLP/视觉/行为) + Judge** 的多智能体图：

```
START → Supervisor（按输入排专家队列：纯文本跳过视觉、无历史跳过行为）
          → NLP 专家（LLM；未配 Key 自动降级为规则，零成本可跑）
          → 视觉专家（占位，P2 接 OCR/图文一致性）
          → 行为专家（占位规则，P3 接 EMA+Chroma 记忆）
        → Judge（按专家可靠度加权聚合 + 低置信反思质询） → END
```

## 快速开始

```bash
# 1) 建虚拟环境（本机 Python 3.10，推荐 3.11+）
python -m venv .venv

# 2) 激活虚拟环境（务必先激活，否则会用到系统 Python，报 No module named 'langgraph'）
source .venv/Scripts/activate        # Windows Git Bash / macOS / Linux
# 见下方「Windows PowerShell 激活」                   # Windows PowerShell

# 3) 装依赖
python -m pip install -r requirements.txt

# 4) 零成本跑通（不需要任何 Key）
python run_demo.py

# 5) 配好 .env 后，用真正的 LLM 跑（会在 LangSmith 出轨迹）
cp .env.example .env                 # 然后填入 Key
python run_demo.py --llm

# 6) 起后端服务
uvicorn app:app --reload             # 打开 http://127.0.0.1:8000/docs
```

### Windows PowerShell 激活（踩坑指南）

PowerShell 的激活脚本是 `Activate.ps1`（不是 `activate`）：

```powershell
.venv\Scripts\Activate.ps1
```

- 若报「无法加载 …… 未数字签名 / 禁止运行脚本」，是执行策略拦的。**当前窗口临时放行一次**（只影响这个窗口，安全）：
  ```powershell
  Set-ExecutionPolicy -Scope Process RemoteSigned
  ```
  再执行 `.venv\Scripts\Activate.ps1`。激活成功后命令行前面会出现 `(.venv)`。
- 验证用对了 Python：`where.exe python`，第一行应指向 `...\implicit-ad-agent\.venv\Scripts\python.exe`。
- **不想激活也行**，直接点名 venv 的 python 即可：
  ```powershell
  .venv\Scripts\python.exe run_demo.py
  ```

> `No module named 'langgraph'` = 没激活 venv、命令跑到系统 Python 上了。依赖装在 venv 里，先激活或用上面的点名方式。

## 看 LangSmith 轨迹
1. 去 https://smith.langchain.com 注册，拿 API Key。
2. 把 Key 填进 `.env`，确认 `LANGSMITH_TRACING=true`。
3. 运行 `python run_demo.py --llm`。
4. 打开 LangSmith → 项目 `implicit-ad-agent` → 点开最新一条 run，即可看到
   supervisor / nlp / judge 等各节点的输入输出、LLM 调用、耗时与 token。

## 目录说明
| 路径 | 作用 |
| --- | --- |
| `impad/hello_graph.py` | 零 Key 的最小图（规则占位），验证环境与轨迹 |
| `impad/graph.py` | 多智能体图的装配（只搭骨架，不写业务逻辑） |
| `impad/agents/supervisor.py` | 主控调度：按输入决定派哪些专家 + 条件路由 |
| `impad/agents/nlp_agent.py` | NLP 专家：LLM 判意图/话术，无 Key 自动降级规则 |
| `impad/agents/vision_agent.py` | 视觉专家（占位，P2 接 OCR/图文一致性） |
| `impad/agents/behavior_agent.py` | 行为专家（占位规则，P3 接 EMA+Chroma） |
| `impad/agents/judge.py` | 加权聚合投票 + 低置信反思质询 |
| `impad/tools/keywords.py` | 广告信号关键词清单（规则降级共用） |
| `impad/state.py` | 图的共享状态定义（plan / agent_votes / evidence …） |
| `impad/llm.py` | 厂商无关 LLM 客户端（OpenAI 兼容端点） |
| `impad/config.py` | 读取 `.env` 的集中配置 |
| `app.py` | FastAPI，`POST /analyze`（返回含各专家投票） |
| `run_demo.py` | 一键跑样本 |
| `samples/` | 固定测试帖子 |
| `tests/` | 冒烟测试 + 多智能体路由/聚合测试（全部零 Key） |
