# M1 Dataset Card 与最终 Gate：D 终审模板

状态：`preparation_only_not_formal`

- D 姓名：________________
- 审查时间：________________
- Dataset Card 路径与 SHA-256：________________
- `dataset_card_status.json` 路径与 SHA-256：________________
- `m1_gate_report.json` 路径与 SHA-256：________________

## 证据核对

- [ ] 候选数、Gold 数、平台与创作者分布有证据。
- [ ] 数据获取日期、来源条款和实际采集过程有证据。
- [ ] 隐私扫描、人工审批范围和排除规则有证据。
- [ ] Round 2 为固定 150 条独立盲标，正式 κ 不低于 0.60。
- [ ] Gold control 180 条与 gold assisted 1,620 条设计和实际执行一致。
- [ ] Qwen 完整 tag、Ollama 版本和推理参数已记录。
- [ ] `--auto-threshold 0`，Gold 中不存在 `auto_accepted/system`。
- [ ] creator 与 content_group 泄漏数均为 0。
- [ ] 已披露共享模型建议可能造成锚定的局限。

## 结论

- [ ] 通过，Gate 报告 `passed=true` 且退出码为 0。
- [ ] 不通过，缺失/不一致证据：________________

D 签字：________________
