# M1 阶段 3 — 组员 B 状态

- 最近更新：2026-08-09（Asia/Shanghai）
- 权威数据：`data/run_outputs/merged_20260728/anonymized_posts.jsonl`
- 数据指纹：`e9ccada23f8a09ad85dc7d99e097e717c2a9d12ab3ad0a228493460d3f79009c`
- 记录数：3,312
- 当前结论：B 的 541 条隐私人工审批和条款抽查签字均已完成；A 侧条款证据，以及数据脱敏后的复扫仍未完成，因此阶段 3 尚不能正式关闭。

## 已完成的自动化工作

1. 在不提供人工审批文件的情况下运行隐私扫描；`public` 清单保持为空。
2. 修复规范媒体引用被误判为 Base64/高熵内容的问题，并补充回归测试。
3. 生成 B 的强制复核清单和低风险 10% 抽样清单。
4. 核对 Bilibili 与微信官方条款页面，形成 `source_terms_evidence.md` 草稿。
5. 准备人工审批 JSON 模板；没有生成或伪造正式审批文件。

## Qwen 辅助状态

本机 `qwen3.5:4b` 可被 Ollama 正常识别，但两次批量风险摘要均在 5 分钟内超时，因此没有生成或采用 Qwen 审批建议。人工清单由规则扫描结果和固定抽样规则生成；最终判断仍由 B 完成，不受未完成的模型摘要影响。

## 最新隐私扫描结果

- 总 findings：4,881
- 严重度：critical 3、high 204、medium 77、low 4,597
- 自动分层（无审批）：raw 3、interim 3,309、public 0
- 含 medium/high/critical finding 的记录：169
- `privacy.contains_sensitive_data=true` 的记录：155
- 两类合并后的强制人工复核记录：233
- 自动低风险池：3,079；固定规则抽样：308（不少于 10%）

## AI 初审辅助（2026-08-08，源数据感知规则第 3 版）

- `privacy/privacy_AI_pre_review_B.md` 已覆盖全部 541 条人工范围。
- 扫描器已修复已遮罩邮箱尾部、网址路径、三位数媒体路径和 `guide`/`UID` 混淆；修订后建议为：redact 62、exclude 0、allow 479。
- 每条新增 `Source state`，区分明文风险、源数据已遮罩、公开/非私人位置、无风险和未定位风险；证据摘要继续隐藏完整敏感值。
- 扫描器修复前的临时选择已在重建审核表时重新核对；最终 541 条 B 确认和正式审批文件已保留，旧临时归档已在本轮收尾清理。
- `agree`/`disagree` 已改为标准 Markdown 任务方框；在支持任务列表的编辑器中可以点击切换。
- 本轮媒体审核曾使用临时浏览页覆盖 427 条含媒体记录、3,953 个本地图片和 209 个仅来源视频，缺失本地图片 0 个；审核完成后该临时浏览页已清理，正式媒体审核 JSON 已保留。
- B 已于 2026-08-09 导出并导入 `privacy/privacy_media_review_B.json`：427/427 条含媒体记录均已查看，420 条标记为 clean、7 条标记为 risk；原始导出文件和项目内导入副本 SHA-256 一致。
- 媒体结果已合并写入 `privacy/privacy_AI_pre_review_B.md`，并生成 `privacy/privacy_media_review_B_summary.md`。文本 AI 初判与媒体审核合并后的初步结果为：allow 473、redact 68、exclude 0；其中 6 条原文本 allow 因媒体风险提高为 redact，另 1 条媒体风险项原本已是 redact。
- 媒体审核不替代文本部分的人工勾选；在 B 完成全部文本确认后，已与文本结论共同写入正式 `privacy_approval.json`。

## B 隐私人工审批（2026-08-09）

- `privacy/privacy_AI_pre_review_B.md` 的 541/541 条均已由 B 勾选，未发现漏选或双选；最终决定为 allow 473、redact 68、exclude 0。
- 已据此生成正式 `privacy/privacy_approval.json`：473 个 B 人工确认允许的 `post_id`，68 个 `redact` 记录及其不暴露明文的理由；无重复、交集或无效 ID。
- 已带该审批文件重新运行 `privacy_scan.py`：3312 条中 public 213、interim 3099、raw 0。473 条人工允许记录中仅 213 条满足扫描器的 public 条件；其余 260 条仍有规则命中，保留在 interim，不能对外发布。
- 这份审批仅覆盖 233 条强制复核和 308 条固定低风险抽样，不把未人工复核的其他记录伪造为已批准。

## B 已完成

1. 完成 `privacy/privacy_AI_pre_review_B.md` 中全部 541 条正文、评论和关联媒体的最终确认。
2. 导入 427 条媒体审核，并对 7 条媒体 risk 项合并判定。
3. 基于 B 的实际勾选生成 `privacy/privacy_approval.json`，并完成重扫和结构核验。

## B 阶段 3 结论

- B 主责的隐私复核、媒体审核、正式审批 JSON 和条款抽查签字均已完成。
- 后续 B 任务须等待 A 补齐采集证据、处理需要脱敏的记录并重新扫描后再继续。

## 仍需 A 完成

1. 核验数据声明的 `manual_public_collection` 与实际采集过程一致，并补充授权或人工采集过程证据。
2. 对 B 的高风险/边界判断抽查至少 30 条。
3. 当前有 1,125 条记录缺少 `provenance.terms_checked_at`；只有在证据成立后才能补写，不能自动推定。

## 当前事实门

即便把全部 3,312 个 ID 假设为已人工批准，在当前数据与条款状态下也只有 1,974 条能进入 `public`，低于指南要求的 2,050 条。主要阻断项是 1,125 条缺少条款核验时间，以及 233 条需要人工隐私判断。完成 A/B 人工步骤后，必须重新运行 Schema 校验、隐私扫描和正式池导出，再以实际结果判断是否达标。
