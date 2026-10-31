# M1 A 负责人执行报告

执行日期：2026-08-10  
执行范围：A-2 来源与合规台账、A-5/B 隐私审批准备。

## 当前数据基线

- 原始只读候选：`数据集/merged_20260728/anonymized_posts.jsonl`
- 原始 SHA-256：`e9ccada23f8a09ad85dc7d99e097e717c2a9d12ab3ad0a228493460d3f79009c`
- 记录数/唯一 post_id：3,312 / 3,312；Schema v1.2 全部通过。
- 平台：Bilibili 2,503；微信公众号 809；创作者 117。
- 条款日期工作副本：`data/interim/m1_candidates_3312_terms_checked.jsonl`
- 工作副本 SHA-256：`b667eb2e9b7e495dc11033987b1422696c7fa5812a5bce4d4109875867e92aee`
- 工作副本 3,312 条均写入 `terms_checked_at=2026-08-10` 并通过 Schema；该字段只表示已核对条款，不表示平台授权。

## 来源与合规

- 2026-08-10 重新核对 Bilibili 官方使用协议和腾讯官方政策目录指向的微信软件许可及服务协议。
- Bilibili 第 4.3.15 条仍限制未经事先书面许可的机器人、蜘蛛、爬虫、脚本等自动获取。
- 微信第 7.4.2、8.2.1.6、8.2.1.8 和 9.2 条仍要求尊重相关权利、限制未经授权的自动访问及知识产权利用。
- 当前结论保持 `review_required`：允许在受控本地环境中继续最小化研究和标注准备，但不得据此公开原文、媒体、可回溯链接或声称平台授权。
- A 负责人王一帆与 B 负责人叶泽楷已于 2026-08-10 核验并签署条款材料；B 结论为“有条件通过”，并澄清 Bilibili 第 2.4 条本身不涉及或授予自动化采集、批量复制和再分发权限。A/B 签字确认材料与风险摘要基本一致，不代表取得平台授权或公开再分发许可。

## 全量隐私扫描

- 已对 3,312 条运行无审批扫描。
- 修复两类系统性误报：本地媒体哈希路径不再按密钥扫描；长中文自然语言不再按整段高熵 token 扫描。
- 修正后共 260 个模式命中，涉及 168 条记录：邮箱 112、物理地址 92、Base64/密钥样式 37、十六进制样式 11、固定电话 5、银行卡号样式 3。
- 另有原始 `contains_sensitive_data=true` 记录；采用保守策略，不自动脱敏或改变正文，所有扫描命中或敏感标记记录均进入排除草稿。
- 隐私安全候选草稿 3,080 条；排除草稿 232 条。
- 在 3,080 条中继续排除 80 条含零字节媒体的记录，得到 3,000 条正式抽样池草稿。

## 人工审批边界

已生成以下本地、Git 忽略的材料：

- `data/reports/m1/privacy/privacy_approval.draft.json`
- `data/reports/m1/privacy/privacy_review_queue.json`
- `data/reports/m1/privacy/privacy_safe_spotcheck_10pct.json`
- `data/reports/m1/privacy/privacy_a_boundary_sample_30.json`
- `data/reports/m1/privacy/privacy_a_boundary_review.json`
- `data/reports/m1/privacy/formal_sampling_pool.draft.json`

A 已于 2026-08-10 完成 30 条高风险/边界样本复核：30 条均有结论且 post_id 无重复，其中 29 条判定为扫描误报、可放行建议，1 条判定为需脱敏后再评估（命中固定电话和邮箱）。A 的复核结果 SHA-256 为 `9aa50310ac5a61820b43504d3a6fa2dbd71165efe50fd2d26830ec39ed207edc`。依据 fail-closed 规则，29 条误报建议在扫描器消除命中并重新扫描前仍不进入 public，需脱敏的 1 条继续排除。

最初审批草稿标记为 `PENDING_HUMAN_B`；A 侧 30 条边界复核已经完成。收到 B 的真人复核包前，正式 `privacy_approval.json` 未生成，根目录 `public_allowlist.json` 保持 0 条，避免把 A 的交叉检查或 AI 草稿冒充 B 的最终人工审批。

2026-08-10 收到 B 的复核包后完成对账：B 已复核 541/541 条（allow 473、redact 68），覆盖当前全部 232 条保守排除记录，并复核当前低风险记录 309 条，达到 10% 抽查下限。为避免自动修改正文和图片，68 条 `redact` 全部按保守排除处理；只有 8 条从原 3,000 条草稿池移除，形成 2,992 条工作候选。正式扫描产生 public 2,992、interim 317、raw 3，正式 allowlist 已落盘。随后收到 B 直接签署的阶段3回执（SHA-256 `23503ad1ff701d1e1856ca71376adcb96ca1ec4ce446dc8e607a83c4a4b09506`），确认上述数量、集合关系和受控内部使用边界，未提出具体 `post_id` 异议。

## Qwen 校准

- 严格使用 M1 指南指定的 `qwen3.5:9b-q4_K_M`，Ollama server 0.30.8。
- 自动判定单测 21 passed；固定 50 条校准完成。
- 首条 10.523 秒；后续中位 10.614 秒；P90 11.739 秒；无 OOM 或服务退出。
- 3/50 条因模型生成未转义直引号导致 JSON 解析失败，并安全回退；决定保留 9B，Gold 仍要求逐条人工确认。
- 20 条人工合理性抽查中，A 已完成 20/20（14 条合理、6 条修正）；B 独立复核待完成。

## 正式批次冻结

- 已从 2,992 条正式隐私许可候选中冻结 `formal_3312_v1` 四批：Round 1 100、Round 2 150、Gold 无 AI 对照 180、Gold Qwen 辅助 1,620。
- 四批共 2,050 个唯一 `post_id`，交集为 0；所有 manifest、导出 JSONL、哈希和冻结摘要位于 `data/reports/m1/locked_batches/formal_3312_v1/`。
- 旧 2,991 基线 Round 1 与旧 A 标注保留为历史审计材料，不计入本轮正式流程。
- 新版 Round 1 A 已于 2026-08-11 完成 100/100 条纯人工盲标；100 个唯一 `post_id` 与冻结 manifest 完全一致，无缺失、额外记录或重复，输出 SHA-256 为 `bbb9d1d02eab9a34e0dfdc19943730f70656cc46385ff5e901cba1418010aae1`。
- B 侧仍保持盲态且待完成。B交接包未包含A标签或输出，ZIP SHA-256 为 `7082d5762469d41cee37af3ad37629c5830c8d226fd3acfad826f0be88d510cd`。

## 验收

- 条款工作副本 Schema：3,312 valid / 0 invalid。
- 审批草稿完整性：3,080 safe + 232 excluded = 3,312，集合无重叠。
- 正式抽样池草稿：3,000 条，属于隐私安全候选子集。
- A 边界复核：30/30 完成；29 条误报建议、1 条脱敏后再评估；样本集合完全对账。
- B 提交对账：541/541 完成；保守处理后候选 2,992 条，Schema 2,992/2,992，扫描 0 命中；正式 allowlist 2,992 条。
- Qwen 性能校准：指定 9B 模型完成 50/50；A 合理性抽查完成，B 待完成。
- 正式批次冻结：四批 2,050 条，交集 0；新版 Round 1 A 已完成，B 待独立盲标，尚未解盲。
- 数据治理与标注相关测试：101 passed；仅有 pytest 缓存写权限警告。
