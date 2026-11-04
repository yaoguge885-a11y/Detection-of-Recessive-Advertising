# HANDOFF：隐性广告识别项目

更新于 2026-11-03。研究主线是用 CreatorShift 检验创作者历史能否提升暗广识别。三元标签为明广、暗广、非广，证据不足的样本进入复核或排除流程。

## 当前进度

- A 侧已完成本轮 503 条标注，合并报告记录了 479 条三元 Gold 候选（非广 386、暗广 52、明广 41）。其中 108 条为单人无 AI 盲标，371 条为 AI 辅助后人工确认。后续分析须保留 `gold_tier`，正式双人一致性仅使用独立人工回件。[11 月 3 日标注交付](docs/progress/2026-11-03-m1-annotation-delivery.md)
- A 侧报告记录 2,932 条获批候选和 2,050 条锁批样本。B 侧交付 v3 证据字典、草稿接续、旧 v2 回件校验和证据覆盖审计。B 的 21 条接续任务与 A 的 503 条属于不同批次。[B 侧交接](docs/handoff/B_HANDOFF_2026-11-02.md)
- 正式 M1 仍待验收。公开 Gate JSON 是早期快照，最新数量来自交付报告。正式报告需用私有回件、正式一致性报告、合规材料、切分报告和 Dataset Card 状态重新生成。[公开 Gate 快照](data/reports/m1/m1_gate_report.json)

## 下一步

1. 收齐并校验私有回件与 Gold 报告，复核低置信度和缺媒体样本，确认 S-1 至 S-9 的生效版本。保留无 AI 盲标与 AI 辅助两个层级。
2. 按现行 M1 门槛组织第二轮独立双人盲标、计算 Cohen κ、仲裁分歧并补齐正式 Gold。若团队调整 1,500 条目标或研究方案，先书面批准并记录生效版本。
3. 按创作者和近重复连通组做零泄漏切分，补齐 Dataset Card 与合规签字（含外部 API 调用的授权和披露记录），重跑 M1 Gate。通过后冻结数据和切分，再跑 P4 基线及 CreatorShift 对照。

## 运行与交接

建议使用 Python 3.12。从仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-handoff.txt
.\.venv\Scripts\python.exe -X utf8 scripts/verify_handoff.py
```

验证包括合成盲标包和 AI 辅助接续演示。手动演示入口是 `scripts/demo_m1_handoff.py` 和 `scripts/demo_assisted_review.py`。正式标注回件、逐条 Gold、媒体和身份映射通过团队私有渠道交接。已发 v2 包按原清单校验，新包按冻结指南生成。

代码来源为 `P1-·-数据地基与标注规范@cb5317e` 和 `P1-m1-gate-reconcile@1c134a3`。历史信息见 [9 月交接](docs/history/HANDOFF_p1_20260909.md)、[10 月交接](docs/handoff_2026-10-01.md) 和 [P3 历史交接](docs/history/HANDOFF_p3_side_20260809.md)。
