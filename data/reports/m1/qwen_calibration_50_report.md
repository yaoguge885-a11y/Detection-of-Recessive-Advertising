# M1 Qwen 本机 50 条校准报告（B 自动部分）

- 状态：自动运行完成；A/B 人工合理性抽查 20 条待完成。
- 运行时间：2026-08-06 23:51:55 至 2026-08-07 00:33:32（Asia/Shanghai）
- 输入：`data/run_outputs/merged_20260728/anonymized_posts.jsonl` 的前 50 条
- 数据指纹：`e9ccada23f8a09ad85dc7d99e097e717c2a9d12ab3ad0a228493460d3f79009c`
- 用途：仅做速度、稳定性与人工质量校准；不得进入正式 κ 或 Gold。

## 配置

- Ollama：`0.32.5`
- 模型：`qwen3.5:4b`
- 模型 digest：`2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`
- 参数/量化：4.7B / Q4_K_M
- context length：4,096
- Ollama 报告 `size_vram=0`：本次为 CPU 推理
- `think:false`、temperature 0、`num_predict=1024`
- `--timeout 120 --keep-alive 30m --auto-threshold 0.95 --no-images --limit 50`

## 性能与故障

- 预热成功：是；预热 8.708 秒
- 首条推理：58.488 秒
- 冷启动总计（预热 + 首条）：67.196 秒
- 后续 49 条中位数：49.431 秒
- 后续 49 条 P90：60.542 秒
- 50 条循环总耗时：2,488.2 秒（约 41.47 分钟）
- 最长单条未超过 120 秒；fallback 1；error 1
- 分层：auto 32、suggest 17、manual 1；合计 50
- 有效模型建议标签：明广 23、暗广 13、非广 13；另 1 条无建议

按任务书估算式，仅以中位推理等待计算 1,620 条约需 `1,620 × 49.431 ÷ 3,600 × 1.15 = 25.58` 小时，尚未包含人工阅读和媒体检查。因此 4B 技术上可运行但本机 CPU 性能偏慢。是否仍使用 4B，必须等待 A/B 对 20 条输出做质量与节省时间评估；若收益不足，正式 Gold assisted 使用 `--no-llm` 更稳妥。

## 产物与哈希

- `data/run_outputs/m1_calibration_50/auto_20260806_235155.jsonl`  
  SHA-256：`7A3DDCCE2D672C8573986B08C38A22A24A60448F12F4AE341A737B23CF6BA216`
- `data/run_outputs/m1_calibration_50/suggest_20260806_235155.jsonl`  
  SHA-256：`7F2A4419A31CA31BD5C182B73A9A5097DF81E8DCEC460702BEE74AC4176CB27F`
- `data/run_outputs/m1_calibration_50/stats_20260806_235155.json`  
  SHA-256：`15E682EF0B2E9D6F88E6478571E05FFD46425555443D1918D865FD34C0066D1A`

## 尚需人工

使用 `qwen_calibration_20_review_manifest.json` 中的固定样本。B 可打开 `qwen_calibration_20_review_B.html`，页面已整合 20 条原文、评论、362 个本地媒体文件和模型建议，缺失媒体 0，并支持本地保存进度和完成后导出 JSON。A 应依据同一 manifest 建立独立副本，A/B 在两边完成前不得互看判断。两人分别填写人工标签、模型建议是否合理、主要错误类型和是否节省时间。完成前不得把模型质量标成通过，也不得把这些 `auto_accepted` 结果纳入正式数据。
