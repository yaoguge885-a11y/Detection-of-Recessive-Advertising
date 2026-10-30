# B 侧阶段 5–12 下游工具回归记录

状态：`preparation_only_not_formal`

执行日期：2026-08-22

## 目的与边界

本记录验证阶段5–12脚本在合成测试夹具上的基本行为，以便在阶段4路线签字后降低工具故障风险。

它不生成、查看或修改正式候选、预演批次、`locked_batches/`、人工标注、Gold、切分或任何签字文件；不得据此宣称阶段5或后续正式阶段已经开始或通过。

## 执行命令

```powershell
& $Python -m pytest `
  .\data-tooling\annotation\tests\test_m1_lock_batches.py `
  .\data-tooling\annotation\tests\test_m1_annotation_output.py `
  .\data-tooling\annotation\tests\test_m1_downstream_pipeline.py `
  .\data-tooling\annotation\tests\test_m1_downstream_readiness.py `
  .\data-tooling\annotation\tests\test_m1_gold_metadata.py `
  -q --basetemp <工作区专用临时目录> -p no:cacheprovider
```

## 结果

```text
10 passed in 0.28s
```

覆盖范围：正式/预演锁批逻辑、人工标注输出验收、下游门禁、Gold 元数据回连。

## 后续

仍需等待 A/B 模型路线共同签字。签字后必须重新运行正式门禁并使用无 `--preflight` 的正式锁批命令；本记录不能替代 C 的封存核验或任何人工标注证据。
