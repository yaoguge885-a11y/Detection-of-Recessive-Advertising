# P1/M1 整合进入 P3 设计

## 1. 目标

在不改动原始 `P3` 工作树、不提交真实帖子正文与媒体的前提下，将远端
`P1-·-数据地基与标注规范` 的最新数据工程成果整合到从 `P3` 创建的
`codex/p1-m1-into-p3` 分支，并完成以下本地闭环：

1. 保留 P3 已完成的统一分析服务、P4 工程准入和 P5.2 工作台；
2. 引入 P1 最新爬取、合并、隐私处置、盲标批次和 Schema v1.2 工具；
3. 删除不属于正式仓库资产的临时脚本、运行输出、测试标注和本机采集清单；
4. 让 P3 的 P1 Adapter 能严格验证并转换 Schema v1.0、v1.1 和 v1.2；
5. 对用户提供的外部 `merged_20260728.zip` 做安全解压和 M1 聚合审计，确认唯一候选、Schema、媒体与合规事实。

本设计只完成原“推荐整合顺序”的第 1～5 项，不把候选数据自动写成 Gold，
也不宣称 M1、M3 或论文研究门通过。

## 2. 分支与隔离策略

- 基线分支：`P3`，基线提交 `ba0ab5802b75ddb58967bbf66b83eb360c395e77`。
- 被整合分支：`origin/P1-·-数据地基与标注规范`，提交
  `43c59ac11770ea29b87c0612da31ab02d579e165`。
- 整合分支：`codex/p1-m1-into-p3`。
- 工作目录：项目内受本地 Git exclude 保护的
  `.worktrees/codex-p1-m1-into-p3/`。
- 使用 `--no-ff` 合并以保留 P1 的 27 个独立提交及合并边界；禁止把 P1
  覆盖到 P3，也禁止 force push、reset 或清理用户数据。

Git 的文本合并成功不代表语义兼容。合并后仍必须检查 Schema 权威版本、
P3 输入适配器、两份事实文档和数据工具镜像。

## 3. 正式保留与清理边界

### 3.1 保留

- Schema v1.2 及变更说明；
- B 站、微信公众号和小红书采集/解析代码；
- 合并、去重、Schema 校验、隐私掩码、批次锁定、人工标注和 Gold 构建工具；
- 与工具行为对应的单元测试；
- 只含聚合统计、无正文/URL/身份映射的 M1 报告；
- P1/M1 双人任务书、标注指南和合规台账，但状态必须与新审计一致。

### 3.2 从整合结果删除

- `temp_*.py`、根目录一次性诊断脚本；
- `scripts/merge_output.txt`、`scripts/validate_result.txt`、运行日志；
- `data/annotations/cli_test_*.json` 和少量本机自动预标注输出；
- `data/bili_urls*.txt`、`data/wechat_authors*.txt` 等本机采集目标清单；
- 任何真实帖子正文、媒体、明文 URL、账号映射、私有审批材料和 ZIP 备份。

相应模式写入 `.gitignore`，防止本地复跑再次污染状态。删除只发生在整合分支
的 Git 结果中，不删除外部 ZIP 或用户本地数据。

## 4. Schema v1.2 与 P3 主链兼容

### 4.1 权威选择

- v1.0 合成提交资产继续由 `data/schema/data_schema_v1.json` 验证；
- v1.1/v1.2 正式候选统一由 `data/schema/data_schema_v1_2.json` 验证；
- `schema_version` 以记录实际值路由验证器，未知版本必须 fail closed；
- 两份 v1.2 schema 镜像必须保持字节一致。

### 4.2 转换边界

`post_record_from_content_record()` 先严格执行对应 JSON Schema，再映射到
`PostRecord`。P3 运行契约只保留分析需要的字段；v1.2 的采集审计扩展字段仍
留在原始候选记录和数据报告中，不擅自扩张 `PostRecord`。

必须用 TDD 证明：

- 合法 v1.2 B 站记录可进入 `normalize_post_record()`；
- v1.1 记录可由 v1.2 schema 向后兼容验证；
- 未知 schema 版本、额外字段或不合规平台被拒绝；
- v1.0 现有合成资产行为不回退。

## 5. 本地数据处理与审计

权威本地输入为用户提供的外部 `merged_20260728.zip`。原 ZIP 只读。

处理顺序：

1. 用 ZIP central directory 检查绝对路径和 `..` 路径穿越；
2. 解压到受 `.gitignore` 保护的 `data/run_outputs/merged_20260728/`；
3. 优先审计 `anonymized_posts.jsonl`，不把 `.bak` 当作额外候选；
4. 运行 Schema v1.2 校验并生成聚合报告；
5. 运行 `m1_readiness.py audit`，核对唯一帖子、创作者、平台、重复行、媒体引用与磁盘文件；
6. 报告只保存聚合统计和哈希，不提交正文、媒体或私有映射。

候选规模以“去重后、Schema 有效、来源可追溯的唯一帖子”计算。ZIP 中存在
约 3000 行不自动等于满足 `>=3000`；若审计仍为 2991，则第 5 项的正确结果是
明确记录还差 9 条，而不是修改阈值或虚构补齐。

## 6. 错误处理

- 合并冲突按 base/ours/theirs 和调用方语义解决；不整文件选择一侧；
- ZIP 有任一路径穿越条目时停止解压；
- JSONL 解析、Schema、媒体缺失或审计失败时保留报告并返回非零退出码；
- 缺少 Gold、正式双标、切分或人工审批时保持 M1 `passed=false`；
- 不因自动预标注或隐私掩码报告而推断正式 κ、Gold 或人工隐私批准。

## 7. 验证与完成标准

第 1～5 项完成必须同时有以下新鲜证据：

- 当前分支为 `codex/p1-m1-into-p3`，起点可追溯到 P3，P1 提交为祖先；
- Git 状态不包含被列为清理对象的路径，真实数据目录保持 ignored；
- Schema v1.2 新测试经历 RED→GREEN，P1 Adapter 聚焦测试通过；
- `pip check`、`compileall`、P1/M1 聚焦测试和全量 pytest 通过；
- ZIP 安全检查通过，解压记录数、唯一候选数、Schema 有效率和媒体缺失数均来自本次运行；
- `HANDOFF.md` 与 `docs/已有功能测试指令库.md` 只陈述本次验证事实，并继续区分工程准入与正式 M1。
