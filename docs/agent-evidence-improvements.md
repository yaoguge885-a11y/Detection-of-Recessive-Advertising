# 广告 Agent 取证与判定改进：第一批

依据《新历史数据评测与准确率改进.md》，本批先修复取证和判定接口，再为同帖比较提供工具。保留既有未提交改动，不调整历史融合权重和分类阈值。

## 已实现的范围

- HTML 结构提取跳过导航、相关推荐、页脚及隐藏子树，保留正文商业合作声明、商品链接和图片说明。采集时使用 `--use-bs4` 启用该路径。
- B 站视频保留 `type="video"` 的媒体记录，缺少视频证据时不会再退化成纯文字输入。
- 本地多图分别进入视觉工具，结果带有媒体标识。未覆盖、失败或不具备 OCR 能力的图片仍保留证据不足状态。调用预算不因图片数量而无限增长。
- 平台元数据中的已识别广告／合作／赞助徽标进入证据汇总和最终判定；普通标签及未经原文核实的结构化文字声明不直接证明披露。
- `analyze_text_intent` 可选择本地训练好的广告二分类模型，继续使用现有工具契约及判定链路。规则分数与模型分数分别保留，已确认披露不被低模型分数覆盖。
- 配对评测按 `post_id` 严格对齐相同目标帖，拒绝重复、缺项和 Gold 冲突；报告准确率、固定三类宏 F1、明广／暗广召回、正常帖商业误报、复核量及各类改对／改错 ID。

## 启用本地广告模型

在项目虚拟环境安装可选依赖：

```powershell
& '.\implicit-ad-agent\.venv\Scripts\python.exe' -m pip install -e './implicit-ad-agent[text-model]'
```

在启动 Agent 的进程中配置：

```powershell
$env:TEXT_INTENT_MODEL_PATH = (Resolve-Path '.\output\zhihu16k_20261110\pipeline\results_encoder\best_model').Path
$env:TEXT_INTENT_POSITIVE_LABEL_ID = '1'
```

也可将这两个配置写入现有 `.env`。只有配置模型路径才会加载模型；不配置时维持 `rule_v2` 基线。正类下标必须与模型训练标签一致，现有知乎模型为 `1`。

模型在 CPU 上推理，输入最多 512 个 token，并受模型位置长度限制。仅接受本地目录，模型与 tokenizer 使用 `local_files_only=True`、`trust_remote_code=False`；完整二分类任务头缺失时拒绝加载。加载或推理失败时返回带警告的规则降级结果。实现依据 [Transformers Auto 类官方文档](https://huggingface.co/docs/transformers/model_doc/auto)。

本环境尚缺 `transformers`，安装尝试未取得可用发行包，因此本批未完成真实知乎 BERT 的推理验证。接口、分数传递、失败降级和标签方向已有自动化验证。跨平台误报问题仍需本平台数据校准，不能将接入模型等同于准确率提高。

## 同帖评测

支持旧 `expanded_agent.json` 的预测分支，以及 JSON／JSONL 最小格式：

```json
{"post_id":"post-001","label":"暗广","predicted_label":"需复核"}
```

在仓库根目录运行以下命令，可检查旧数据中当前帖与三条历史分支的比较；先将 `$baseline` 改为本地旧结果文件的实际路径：

```powershell
$baseline = 'D:\path\to\expanded_agent.json'
& '.\implicit-ad-agent\.venv\Scripts\python.exe' -X utf8 '.\implicit-ad-agent\scripts\compare_agent_predictions.py' `
  --before $baseline `
  --before-arm current `
  --after $baseline `
  --after-arm own_3 `
  --output '.\output\agent_evidence_20261125\baseline_comparison.json'
```

这只是既有基线的复核。评估本批改动时，必须用完整 `graph.invoke` 或 `AnalysisService.analyze` 生成相同目标帖的新预测，再与旧结果比较。原研究脚本直接调用判定函数，不能验收图中的取证调度改进。

`需复核` 计为未判对；正常帖误报只统计被判为明广／暗广的正常帖，复核另列。商业意图分数不充当暗广概率，因此本工具不计算 AUPRC 或校准误差。

## 后续工作与结论边界

本批尚未实现 URL 原图下载落盘、视频抽帧、字幕转录或视频披露的完整覆盖验证。当前视觉改进针对已提供的本地图片；缺失媒体仍需复核。

尚未新增人工标注、训练本平台模型或调整历史融合参数，也未对 397 条 Gold 重跑完整 OCR／Agent。只有完成同帖比较，且检查改对数、改错数、宏 F1、暗广召回和正常误报，才能判断准确率是否改善。正式研究结论仍需新作者独立测试。

## 验证记录（2026-11-25）

- 主项目同步回归：616 项通过、2 项视觉集成测试跳过；另测 MCP 同步服务 4 项通过。
- HTML 提取回归：5 项通过，覆盖网页噪声、图片列表对齐、无效图片引用过滤、正文披露保留及成功但为空的提取结果。
- 最后补充的模型依赖声明及证据模型来源传递，相关 42 项测试通过。
- 本批 Python 文件通过编译检查，`git diff --check` 无空白错误。
- 原 397 帖 `current` 与 `own_3` 分支比较已生成 `output/agent_evidence_20261125/baseline_comparison.json`：均为 149/397，宏 F1 为 0.231315，暗广召回 3/40，正常帖商业误报 10/325，复核 207，改对／改错均为 0。这是旧结果复核。

完整测试在 API／MCP 异步用例挂起后中止。进一步独立运行 `asyncio.run(asyncio.sleep(0.001))` 同样无法返回，因此本批同步回归排除了四个使用 TestClient 的测试文件、两个 stdio 协议测试文件及 stdio 超时用例；未宣称完整回归通过。真实广告模型和完整 Gold 复测仍待完成。
