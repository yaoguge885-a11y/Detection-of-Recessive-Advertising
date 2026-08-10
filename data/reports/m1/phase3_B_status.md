# M1 阶段 3 — 组员 B 状态

- 最近更新：2026-08-10（Asia/Shanghai）
- 权威数据：`data/run_outputs/merged_20260728/anonymized_posts.jsonl`
- 数据指纹：`e9ccada23f8a09ad85dc7d99e097e717c2a9d12ab3ad0a228493460d3f79009c`
- 记录数：3,312
- 当前结论：B 的 541 条隐私人工审批和条款抽查签字均已完成；61 条无媒体风险的已批准文本脱敏也已应用到独立候选副本。原补充队列中的 581 条无本地帧远程视频已由 581 条可审记录替换，不再要求逐个观看远程视频；A 侧条款证据、既有媒体风险处理及 1,696 条补充最终人工决定仍未完成，因此阶段 3 尚不能正式关闭。

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

## B 文本脱敏候选（2026-08-09）

- 未覆盖权威 `anonymized_posts.jsonl`；所有变更均写入独立候选 `anonymized_posts.redacted_B_candidate.jsonl`。
- 改进 `mask_sensitive_pii.py`：支持用正式审批文件把范围严格限制到 `decision=redact`，覆盖 UID、QQ、邮箱、固定电话、物理地址及已人工确认的疑似密钥，并输出不含敏感明文的审计摘要。
- 修复扫描器把“下载地址：https://...”误判为物理地址的问题；真实地点仍会命中。隐私扫描回归测试 10/10 通过，annotation 全套测试 36/36 通过。
- 68 条已签字 redact 中，63 条发生文本遮罩；其中 61 条无媒体风险且遮罩后无任何 medium/high/critical 文本命中，已写入派生审批 `privacy_approval_after_text_redaction_B.json`。
- 其余 7 条均有媒体风险（其中 2 条同时完成了文本遮罩），继续保留为 excluded，未擅自修改图片。
- 候选副本 Schema 校验 3,312/3,312；使用派生审批复扫后 public=289、interim=3,023、raw=0。相较权威原文件 public=213，增加 76 条；其中 54 条来自完成的文本脱敏审批，其余来自网络地址误报修复。
- 61 条已完成文本脱敏中另有 7 条仅因 `terms_checked_at` 缺失而暂未进入 public；A 完成条款核验并依法补写后才能重新计算。
- 在不考虑条款日期和人工审批、但保留当前隐私规则的假设下，候选副本最多有 3,133 条隐私层面可用；现有派生审批中仅 408 条可在条款齐全后进入 public，因此达到 2,050 仍至少需要 1,642 条额外人工审批。
- 已从 2,722 条未审批、无 medium/high/critical 规则命中且隐私标志合格的候选中，以固定 seed=505、创作者平衡策略生成 1,700 条补充人工复核 manifest：Bilibili 1,298 条、微信公众号 402 条，预留 58 条缓冲。该 manifest 状态为 `pending_B_human_privacy_review`，不构成自动批准。
- 已生成本地续审页面 `privacy/privacy_supplemental_review_B.html`：内含 1,700 条、7,680 个本地媒体引用且缺失 0；浏览器本地保存进度，完成后导出 `privacy_supplemental_review_B.json`。页面 SHA-256 为 `FFE9F5503C2CFE5020EF1FC2BEB3811A568C46A75A7494E57723DF75DCD84B72`。

## 补充队列 AI 首轮分流（2026-08-09）

- 使用 SHA-256 精确复用 B 既往人工判为 clean 的媒体结果；风险记录中的其他媒体没有被错误继承为风险。
- 对此前未见的 4,095 个本地媒体哈希生成 64 张联系表，并由 Codex 自身视觉完成缩略图级初筛；未调用 GLM Vision、Ollama 或 Qwen。GIF 仅查看首帧。
- `privacy/privacy_supplemental_ai_triage_B.json` 将 1,700 条分为：1,115 条 AI 低风险快速确认、2 条建议 redact、2 条视觉边界、581 条仅有远程 Bilibili 视频且无本地帧的技术未验证项。
- 4 条视觉重点项入口：`privacy/privacy_supplemental_visual_secondary_review_B.html`；全部 585 条二审/技术未验证项入口：`privacy/privacy_supplemental_secondary_review_B.html`；1,115 条低风险快速确认入口：`privacy/privacy_supplemental_quick_confirm_B.html`。
- B 已完成 4 条视觉重点项人工二审并导出 `privacy/privacy_supplemental_visual_secondary_review_B.json`：allow 2、redact 2、exclude 0；4 个 ID、完成状态、备注、manifest 指纹和候选数据指纹均核对通过。
- 两条 redact 涉及私人聊天头像/昵称等媒体内容，目前只形成正式人工决定，尚未实际修改图片；完成媒体遮罩或改为 exclude 前不能进入正式 public 池。
- 以上均是 AI 分流证据，不构成正式隐私批准。B 仍需对进入正式池的记录留下最终人工决定。原方案要求远程视频查看、取得可审帧或保守排除；现已由下节的 581 条可审记录替换，B 不再需要逐个观看这些远程视频。

## 远程视频替换队列（2026-08-10）

- 原 1,700 条中 581 条仅有远程 Bilibili 视频且无本地帧。为避免要求 B 逐个观看远程视频，已从原 manifest 之外的 674 条可审候选（316 条有本地媒体、358 条纯文本）中，以固定 seed=506 选出 581 条替换记录；替换 manifest 为 `privacy/privacy_supplemental_replacement_review_manifest_B.json`，明确排除 remote-video-only。
- 替换队列构成为：394 条 Bilibili、187 条微信公众号；273 条有本地媒体、308 条纯文本。媒体预筛精确复用 54 条既往人工 clean 记录，剩余 219 条含未见本地媒体。
- 已生成 33 张联系表并由 Codex 自身视觉检查 2,112 个未见本地媒体哈希，随后对候选原图逐项复核；未调用 GLM Vision、Ollama 或 Qwen。
- `privacy/privacy_supplemental_replacement_ai_triage_B.json` 将 581 条分为：576 条 AI 低风险快速确认、5 条建议 redact 的视觉重点项、0 条远程视频未验证项。重点入口为 `privacy/privacy_supplemental_replacement_visual_secondary_review_B.html`，快速确认入口为 `privacy/privacy_supplemental_replacement_quick_confirm_B.html`。
- 这 581 条用于替代原 manifest 中的 581 条远程视频，不与原 1,700 条叠加计数。原队列已有 4 条视觉重点项完成人工二审，因此当前补充人工待办为原队列 1,115 条低风险确认，加替换队列 5 条重点复核和 576 条低风险确认，共 1,696 条。
- 替换队列仍只是 AI 分流证据，不构成正式隐私批准。5 条重点项必须先由 B 复核；576 条 AI 低风险项仍需 B 留下最终人工决定。

## B 阶段 3 结论

- B 主责的初始隐私复核、媒体审核、正式审批 JSON、条款抽查签字、可机械执行的文本脱敏候选、补充队列 AI 首轮分流及 581 条远程视频替换队列的 AI 视觉初筛均已完成。
- 后续仍需 B 对 1,696 条补充记录作最终人工决定；7 条既有媒体风险和 2 条已人工判定的补充媒体 redact 需落实，另有 5 条替换队列视觉风险待 B 复核。A 还必须补齐采集/条款证据并完成 30 条抽查，最终复扫通过后才能进入阶段 5。

## 仍需 A 完成

1. 核验数据声明的 `manual_public_collection` 与实际采集过程一致，并补充授权或人工采集过程证据。
2. 对 B 的高风险/边界判断抽查至少 30 条。
3. 当前有 1,125 条记录缺少 `provenance.terms_checked_at`；只有在证据成立后才能补写，不能自动推定。

## 当前事实门

即便把全部 3,312 个 ID 假设为已人工批准，在当前数据与条款状态下也只有 1,974 条能进入 `public`，低于指南要求的 2,050 条。主要阻断项是 1,125 条缺少条款核验时间，以及 233 条需要人工隐私判断。完成 A/B 人工步骤后，必须重新运行 Schema 校验、隐私扫描和正式池导出，再以实际结果判断是否达标。
