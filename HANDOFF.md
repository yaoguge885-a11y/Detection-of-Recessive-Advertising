# HANDOFF：隐性广告识别项目

更新于 2026-11-03。研究主线是用 CreatorShift 检验创作者历史能否提升暗广识别。三元标签为明广、暗广、非广，证据不足的样本进入复核或排除流程。

## 当前进度

- B 侧私有包已核验为 **2,932 条获批候选**。候选、审批和正式化报告的指纹一致。它是后续锁批的输入。桌面旧 ZIP 的 2,901 条仅作历史复现或媒体查找。
- 本轮 **503 条 = 479 条保留 + 24 条排除**，三份 Gold 文件与合并报告已对账，479 条全部属于获批池。按团队补标计划纳入这 479 条，距 1,500 条还差 **1,021 条净保留标签**。其中 108 条单人无 AI、371 条 AI 辅助后人工确认，保留分层。[标注交付记录](docs/progress/2026-11-03-m1-annotation-delivery.md)
- **正式 M1 仍待验收。** 第一轮综合表是否保留两人的原始标签待核对，第二轮 150 条清单需向批次负责人领取或重新锁定。公开 Gate JSON 仍是早期快照。[数据索引与本地目录](docs/handoff/M1_DATA_INVENTORY.md)

## 下一步

1. 用第一轮 A/B 原始标签或已有一致性报告完成复盘，冻结下轮规则并记录指纹。综合表如果只保留裁决标签，需找回一致性报告或补齐独立回件。
2. 从获批池锁定与已标样本不重叠的 150 条新样本。A/B 各自纯人工标同一批，独立导出后算 Cohen κ。κ 至少 0.60 再扩量，低于门槛先修订规则并换一批新题。
3. 补齐正式 Gold 与仲裁证据，按创作者和近重复连通组做零泄漏切分，完成 Dataset Card 与合规签字后重跑 M1 Gate。若正式验收采用 479 条的纳入口径，先记录团队批准的协议版本。Gate 通过后再跑正式 P4。

## 运行与交接

建议使用 Python 3.12。从仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-handoff.txt
.\.venv\Scripts\python.exe -X utf8 scripts/verify_handoff.py
```

验证包括合成盲标包和 AI 辅助接续演示。手动演示入口是 `scripts/demo_m1_handoff.py` 和 `scripts/demo_assisted_review.py`。正式标注回件、逐条 Gold、媒体和身份映射通过团队私有渠道交接。已发 v2 包按原清单校验，新包按冻结指南生成。

代码来源为 `P1-·-数据地基与标注规范@cb5317e` 和 `P1-m1-gate-reconcile@1c134a3`。历史信息见 [9 月交接](docs/history/HANDOFF_p1_20260909.md)、[10 月交接](docs/handoff_2026-10-01.md) 和 [P3 历史交接](docs/history/HANDOFF_p3_side_20260809.md)。
