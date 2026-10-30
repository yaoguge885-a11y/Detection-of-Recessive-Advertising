# 本地 M1 工作交接（2026-10-30）

## 范围与版本

本交接记录当前 `P3` 工作区提交前的本地改动。原提交基线为 `0bf6a66`；本次整理是对本地工作做快照，不表示已整合远端最新工作或重新完成 M1 验收。

2026-10-30 已获取远端引用。`origin/P1-m1-gate-reconcile` 当时位于 `a5288fa`，包含 `0bf6a66` 并有 36 个额外提交；`origin/P3-合并baseline` 与 `0bf6a66` 一致。当前本地 `P3` 原先跟踪旧的 `origin/P3`，其 ahead 数字不能用于判断与最新 M1 分支的差距。远端可能继续变化，整合前应重新获取并核对。

## 本地工作内容

- M1 合规、隐私和批次准备：来源条款核验、隐私扫描和人工审核工具、批次冻结脚本、数据集卡与执行报告。
- 人工标注：支持 `uncertain`、完整正文和媒体查看、A/B 启动脚本、交接及执行指南。
- Qwen 校准：结构化输出约束、批处理延迟统计、人工复核工具及 50 条校准报告。校准结果不是人工 Gold 或正式 κ。
- 数据治理：按帖子 ID 去重、隐私扫描误报处理、Schema v1.2 校验及相关测试。
- 研究材料：MMM2027 论文选题与摘要草稿、标注方案和 Qwen 分歧诊断任务书。历史文档中的时间、路径和执行方式须按当前环境复核。

主要入口为 `data/reports/m1/a_owner_execution_report.md`、`data/reports/m1/qwen_calibration_report.md`、`docs/dataset_card_current.md` 和 `docs/M1_双人主导_Qwen本地AI辅助执行指南.md`。

## 数据和验收口径

本地数据卡记载的是 2026-08-10 附近的工作快照：原始候选 3,312 条，隐私许可池 2,992 条；它记录 `formal_3312_v1` 批次及 A 侧 Round 1 进展。远端进展文档记录后续正式内部候选池为 2,932 条，且要求重新确认模型路线和正式锁批状态。两者对应不同阶段与证据，不能把旧数值或旧批次直接当成最新正式结果；整合时应核对数据指纹、审批、批次和人工交接材料。

本地执行报告记载 Qwen 50 条校准及 A 侧 20 条复核；远端后续还有独立盲测和模型诊断。正式 Gold、第二轮 κ、无泄漏切分和 M1 最终通过不能仅凭这些历史快照推断。

## 远端整合注意事项

本地与远端均修改了 `.gitignore`、`data-tooling/annotation/auto_judge.py`、`batch_pre_annotate.py`、`manual_review_annotate.py`、`privacy_scan.py`、`data/reports/m1/privacy_scan_report.json`、`docs/dataset_card_current.md`、`implicit-ad-agent/scripts/data/annotation/privacy_scan.py` 和 `implicit-ad-agent/tests/data/test_data_governance_tools.py`。这些文件需要逐项对照，保留有效行为与较新的证据，不能整文件盲目选一侧。整合完成后重新运行针对性测试，并确认正式数据与审核记录的版本。

## 隐私与交付边界

原始数据、媒体、标注结果、私有审批和锁批材料位于 Git 忽略路径，不在本次可见工作区快照的范围内。已跟踪的 `data/reports/m1/privacy_scan_report.json` 含按记录组织的扫描发现、匹配哈希和本机输入路径；本地提交保留了它，**推送或共享提交前须先审查其隐私和发布适用性**。隐私审核和条款核验不等于获得公开再分发授权。

## 本次验证

使用仓库 `.venv` 的 Python 3.10.11 和 pytest 8.4.2，运行数据治理、人工标注、去重和自动判定相关测试，结果 **57 passed**。原已跟踪文件的 `git diff --check` 通过；暂存检查报告新纳入的历史 Markdown 中存在行尾空格（多数为 Markdown 换行）和文件末尾空行，原样保留。未重新运行全量测试、真实模型推理、正式数据审计或 M1 Gate。
