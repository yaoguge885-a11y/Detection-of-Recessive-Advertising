# M1 双人主导、Qwen 本地 AI 辅助执行指南

> **For agentic workers:** 按本文件的阶段顺序执行；每个阶段达到“通过条件”后再进入下一阶段。不得把 `auto_accepted`、`system` 或同一标注者的结果计入正式 κ 或 Gold。

版本：2026-08-01  
适用仓库：`D:\AAA Jobs\Detection-of-Recessive-Advertising`  
适用分支：`P3`  
输入压缩包：`C:\Users\31729\Desktop\merged_20260728.zip`  
推荐模型：`qwen3.5:9b-q4_K_M`；显存不足或速度不合格时降级为 `qwen3.5:4b`

---

## 1. 结论与执行边界

本方案采用“正式 κ 纯人工、Gold 由 Qwen 辅助但双人逐条确认”的混合路线。

1. 正式第二轮 κ：A、B 对同一批 150 条进行完全独立、互相不可见、AI 关闭的盲标。
2. Gold：Qwen 只给建议；A、B 必须各自检查文字和媒体，再逐条按键确认或修改。
3. `--auto-threshold 0` 是正式 Gold 的强制参数，防止高置信度结果自动保存为机器标签。
4. `auto_accepted`、`system`、`model_calibration`、同一 annotator 的两份结果不能进入 κ 或 Gold。
5. Gold 池中抽取 10% 作为“无 AI 对照组”，用来测量 Qwen 对人工判断的锚定影响。
6. 来源条款和隐私可由 AI 整理、扫描和排序，但最终批准必须由人完成并留下证据。
7. C、D 只承担少量独立抽查与签字；不能完全取消，因为需要最低限度的外部复核。

预期结果不是“让 AI 自动标完”，而是：让 AI 承担阅读摘要、候选建议、风险排序和重复劳动，同时保留正式研究证据所需的人类独立性。



## 3. 四人分工、工作量与时间

以下只使用 A/B/C/D 角色，具体人员由团队自行映射。

| 角色 | 比例 | 预计时间 | 主要职责 |
|---|---:|---:|---|
| A（主负责人一） | 48% | 35–55 小时 | 环境与数据、候选补齐、来源条款、A 侧标注、共同裁决 |
| B（主负责人二） | 48% | 35–55 小时 | Qwen 校准、隐私审批、B 侧标注、κ/Gold/切分执行 |
| C（轻量审计） | 2% | 2–4 小时 | 批次封存、哈希核验、随机抽查 30–50 条 |
| D（轻量签字） | 2% | 2–4 小时 | Dataset Card 终审、M1 证据清单和最终签字 |

总人时：约 74–118 小时。A、B 并行时，墙钟时间约 7–12 个工作日（按每天有效工作 6 小时估算）。

时间必须在前 50 条完成后重新估算：

```text
预计标注小时数 = 待标条数 × 最近 50 条的中位秒数 ÷ 3600 × 1.15
```

其中 1.15 是复查、故障和休息余量。不得沿用提交中“2–4 秒/条”的旧机器数字来安排本机工期。

---

## 4. M1 完成定义

所有条件必须同时满足：

- 候选池至少 3,000 条；当前历史审计为 2,901 条，需要新增至少 99 条。
- 正式 Gold 至少 1,500 条，且每条由两个不同的人类 annotator 独立标注后达成一致或完成人工裁决。
- 正式第二轮独立盲标完成，Cohen’s κ 达到 `0.60`；目标建议 `0.70` 以上。
- 来源条款核验完成并有证据文件。
- 正式发布/Gold 范围的隐私人工审批完成。
- train/validation/test 按创作者隔离，且 `content_group_id` 近重复组不跨集合。
- Dataset Card 的相应布尔项有证据后才能设为 `true`。
- 最终 `m1_readiness.py gate` 返回退出码 0，且报告 `passed=true`。

工程测试通过不等于 M1 通过。M1 是数据、治理和研究证据门禁。

---

## 5. 每个新 PowerShell 窗口先执行的变量

```powershell
$RepoRoot = 'D:\AAA Jobs\Detection-of-Recessive-Advertising'
$Python = Join-Path $RepoRoot 'implicit-ad-agent\.venv\Scripts\python.exe'
$ZipPath = 'C:\Users\31729\Desktop\merged_20260728.zip'
$DatasetRoot = Join-Path $RepoRoot 'data\run_outputs\merged_20260728'
$CandidateFile = Join-Path $DatasetRoot 'anonymized_posts.jsonl'
$FormalCandidateFile = Join-Path $RepoRoot 'data\reports\m1\formal_eligible_candidates.jsonl'
$Model = 'qwen3.5:9b-q4_K_M'
$OllamaModelRoot = 'D:\OllamaModels'
Set-Location -LiteralPath $RepoRoot
```

检查变量：

```powershell
Test-Path -LiteralPath $Python
Test-Path -LiteralPath $ZipPath
Get-Item -LiteralPath $Python, $ZipPath | Select-Object FullName, Length
```

通过条件：两次 `Test-Path` 都为 `True`。

---

## 6. 阶段 0：本地环境与 Ollama（A 主责，B 复核，2–4 小时）

### 6.1 使用已有项目虚拟环境

当前项目已经有 `.venv`，不要重新创建，不要使用系统 Python。

```powershell
& $Python --version
& $Python -m pip check
```

预期：Python 3.10.x；`pip check` 输出 `No broken requirements found.`。

核心 CLI 不需要 Flet。当前环境没有 Flet，因此本方案以命令行标注器为正式入口。

如团队确实想用 GUI，再单独安装可选依赖：

```powershell
Set-Location -LiteralPath (Join-Path $RepoRoot 'implicit-ad-agent')
& $Python -m pip install -e '.[annotation]'
Set-Location -LiteralPath $RepoRoot
```

GUI 只能选择 `suggest` 模式，不得以 `auto` 模式生产正式 Gold。

### 6.2 安装 Ollama for Windows

官方文档：[Ollama on Windows](https://docs.ollama.com/windows)。

```powershell
Start-Process 'https://ollama.com/download/windows'
```

浏览器打开后下载并执行官方安装器。安装完成后关闭当前 PowerShell，重新打开，再执行第 5 节变量。

```powershell
Get-Command ollama
ollama --version
```

如果命令仍不存在，先退出并重新启动 Ollama 和 PowerShell；不要把其他电脑上的 `E:\ollama` 路径写进本项目。

### 6.3 把模型放到 D 盘

```powershell
New-Item -ItemType Directory -Force -Path $OllamaModelRoot | Out-Null
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $OllamaModelRoot, 'User')
[Environment]::GetEnvironmentVariable('OLLAMA_MODELS', 'User')
```

然后从系统托盘退出 Ollama，再启动 Ollama，并重新打开 PowerShell。再次执行第 5 节变量。

```powershell
$env:OLLAMA_MODELS
```

预期为 `D:\OllamaModels`。

### 6.4 下载模型

官方模型页：[Qwen3.5 tags](https://ollama.com/library/qwen3.5/tags)。9B 的 q4_K_M 文件约 6.6GB；当前 8GB 显存余量较紧，所以必须先测，不保证全量稳定。

```powershell
ollama pull $Model
ollama list
nvidia-smi
```

如出现显存不足、频繁 CPU 回退或中位耗时明显过高：

```powershell
$Model = 'qwen3.5:4b'
ollama pull $Model
ollama list
```

模型降级只影响辅助效率，不影响正式 κ，因为正式 κ 本来就关闭 AI。必须把最终使用的 tag 记录进 Dataset Card。

### 6.5 启动、预热和 API smoke test

```powershell
& $Python .\data-tooling\annotation\ollama_server.py `
  --model $Model `
  --models-dir $OllamaModelRoot `
  status

& $Python .\data-tooling\annotation\ollama_server.py `
  --model $Model `
  --models-dir $OllamaModelRoot `
  serve `
  --preload
```

结构化输出、`think` 和 `keep_alive` 的官方说明：

- [Chat API](https://docs.ollama.com/api/chat)
- [Thinking](https://docs.ollama.com/capabilities/thinking)
- [Structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [Keep models loaded](https://docs.ollama.com/faq)

```powershell
$Body = @{
  model = $Model
  messages = @(
    @{
      role = 'user'
      content = '只输出 JSON：{"status":"ok"}'
    }
  )
  format = 'json'
  stream = $false
  think = $false
  keep_alive = '30m'
  options = @{
    temperature = 0
    num_predict = 128
  }
} | ConvertTo-Json -Depth 8

$Smoke = Invoke-RestMethod `
  -Uri 'http://127.0.0.1:11434/api/chat' `
  -Method Post `
  -ContentType 'application/json' `
  -Body $Body

$Smoke.message.content
$Smoke.message.content | ConvertFrom-Json
```

通过条件：能解析出 JSON，且没有网络/模型错误。

---

## 7. 阶段 1：载入 3GB 数据、校验与恢复基线（A 主责，B 复核，1–3 小时）

### 7.1 先验证压缩包哈希

已知压缩包 SHA-256：

```text
998FB8759539C04561034BE51B67258D1E6481C7F4F74C961534C07E5D337F11
```

```powershell
$ZipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash
$ZipHash
if ($ZipHash -ne '998FB8759539C04561034BE51B67258D1E6481C7F4F74C961534C07E5D337F11') {
  throw '压缩包 SHA-256 不匹配，停止解压和标注。'
}
```

### 7.2 解压到正确层级

压缩包根目录已经直接包含 `anonymized_posts.jsonl` 和 `media`，所以解压目标必须是 `$DatasetRoot`。

```powershell
if (Test-Path -LiteralPath $DatasetRoot) {
  throw "目标目录已存在：$DatasetRoot。先人工检查，不要覆盖。"
}

New-Item -ItemType Directory -Path $DatasetRoot | Out-Null
Expand-Archive -LiteralPath $ZipPath -DestinationPath $DatasetRoot

Test-Path -LiteralPath $CandidateFile
Test-Path -LiteralPath (Join-Path $DatasetRoot 'media')
Get-Item -LiteralPath $CandidateFile | Select-Object FullName, Length
```

通过条件：JSONL 和 media 目录都存在。

### 7.3 Schema 校验

```powershell
& $Python .\data-tooling\annotation\validate_schema.py `
  $CandidateFile `
  --target-schema 1.2 `
  --schema .\data\schema\data_schema_v1_2.json `
  --report .\data\reports\m1\schema_validation.json

if ($LASTEXITCODE -ne 0) { throw 'Schema 校验失败。' }
```

### 7.4 M1 审计

```powershell
& $Python .\data-tooling\m1_readiness.py audit `
  --dataset-root $DatasetRoot `
  --output .\data\reports\m1\m1_data_audit.json
```

历史预期基线：2,901 条、108 位创作者、媒体引用缺失 0、数据指纹为：

```text
adb39f1840df62cbeef52faabde85177536478c1c06d37bbb747a9a2bb59a3a5
```

打开报告：

```powershell
Get-Content -LiteralPath .\data\reports\m1\m1_data_audit.json -Encoding UTF8
```

如果数量、缺失媒体或指纹与历史基线不一致，停止，不进入标注。

---

## 8. 阶段 2：补齐 99 条候选（A 主责，B 抽查，4–8 小时）

### 8.1 新增批次要求

- 至少新增 99 条有效、去重、媒体可访问、schema 合格的记录。
- 建议采集 120–150 条，给无效、重复和隐私排除留余量。
- 新增批次放到：`data\run_outputs\m1_new_batch_001`。
- 不修改原始 2,901 条文件；通过增量合并生成新 canonical 数据集。

### 8.2 新批次单独校验

```powershell
$NewBatchRoot = Join-Path $RepoRoot 'data\run_outputs\m1_new_batch_001'
$NewBatchFile = Join-Path $NewBatchRoot 'anonymized_posts.jsonl'

& $Python .\data-tooling\annotation\validate_schema.py `
  $NewBatchFile `
  --target-schema 1.2 `
  --schema .\data\schema\data_schema_v1_2.json `
  --report .\data\reports\m1\new_batch_schema_validation.json

if ($LASTEXITCODE -ne 0) { throw '新增批次 Schema 校验失败。' }
```

### 8.3 增量合并

保留原始 2,901 条目录，先复制出一个新的合并目录，再追加新批次：

```powershell
$MergedRoot = Join-Path $RepoRoot 'data\run_outputs\merged_m1_3000plus'
if (Test-Path -LiteralPath $MergedRoot) {
  throw "合并目标已存在：$MergedRoot。先人工检查，不要覆盖。"
}

Get-PSDrive -Name D
Copy-Item -LiteralPath $DatasetRoot -Destination $MergedRoot -Recurse

& $Python .\scripts\merge_incremental.py `
  --source $NewBatchRoot `
  --target $MergedRoot

if ($LASTEXITCODE -ne 0) { throw '增量合并失败。' }

$DatasetRoot = $MergedRoot
$CandidateFile = Join-Path $DatasetRoot 'anonymized_posts.jsonl'
```

随后在这个新目录中生成 `content_group_id` 并去除内容级精确重复。先留备份，再把规范化结果写回工作副本：

```powershell
$PreNormalize = Join-Path $DatasetRoot 'anonymized_posts.pre_normalize.jsonl'
Copy-Item -LiteralPath $CandidateFile -Destination $PreNormalize

& $Python .\data-tooling\annotation\normalize_and_deduplicate.py `
  --input $PreNormalize `
  --output $CandidateFile `
  --report .\data\reports\m1\dedup_and_content_group_report.json `
  --content-group-threshold 0.85

if ($LASTEXITCODE -ne 0) { throw '去重或 content_group 生成失败。' }
```

重新执行第 7.3、7.4 节。注意：去重后的有效唯一候选仍必须 `>=3000`；如果降到 3,000 以下，继续新增合格候选，不能使用被去掉的重复记录凑数。

通过条件：审计中的有效唯一候选数 `>= 3000`，媒体引用缺失为 0，schema invalid 为 0。

---

## 9. 阶段 3：来源条款与隐私审批（A/B 并行，8–15 小时）

### 9.1 来源条款：A 主责

AI 可以做：从官方条款中提取平台、URL、获取日期、允许/限制用途、再分发限制、删除/撤回要求、研究使用说明。

AI 不能做：凭模型记忆替代官方页面，或自动把 `terms_verified` 设为 `true`。

执行步骤：

1. 逐个平台打开当前官方条款，而不是博客或二手解读。
2. 保存 URL、页面标题、访问时间、适用范围和关键限制的人工摘要。
3. 对 Bilibili 与 WeChat 分别形成证据条目。
4. A 完成，B 抽查 URL 与摘要一致性。
5. 只有证据完整时才更新 Dataset Card。

建议证据路径：

```text
data/reports/m1/source_terms_evidence.md
```

每个平台最少包含：

```markdown
## 平台名
- 官方条款 URL：
- 页面标题：
- 访问时间：
- 数据获取方式：
- 研究使用边界：
- 禁止或限制事项：
- 删除/撤回处理：
- A 核验：姓名/日期
- B 抽查：姓名/日期
```

两个平台都核验完成后，才能把核验日期写入新合并工作副本。以下命令拒绝修改原始 `merged_20260728`：

```powershell
$TermsEvidence = Join-Path $RepoRoot 'data\reports\m1\source_terms_evidence.md'
if (-not (Test-Path -LiteralPath $TermsEvidence)) { throw '来源条款证据文件不存在。' }
if ((Split-Path -Leaf $DatasetRoot) -eq 'merged_20260728') {
  throw '当前仍指向原始 2,901 条目录，拒绝写入 terms_checked_at。'
}

$TermsCheckedAt = (Get-Date).ToString('yyyy-MM-dd')
$VerifiedPlatforms = [System.Collections.Generic.HashSet[string]]::new()
[void]$VerifiedPlatforms.Add('bilibili')
[void]$VerifiedPlatforms.Add('wechat_official_account')

$PreTerms = Join-Path $DatasetRoot 'anonymized_posts.pre_terms_verified.jsonl'
Copy-Item -LiteralPath $CandidateFile -Destination $PreTerms

$TermsApplied = [System.Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $PreTerms -Encoding UTF8 | ForEach-Object {
  if ([string]::IsNullOrWhiteSpace($_)) { return }
  $row = $_ | ConvertFrom-Json
  if ($VerifiedPlatforms.Contains([string]$row.platform)) {
    $row.provenance.terms_checked_at = $TermsCheckedAt
  }
  $TermsApplied.Add(($row | ConvertTo-Json -Compress -Depth 100))
}
[IO.File]::WriteAllLines($CandidateFile, $TermsApplied, [Text.UTF8Encoding]::new($false))

& $Python .\data-tooling\annotation\validate_schema.py `
  $CandidateFile `
  --target-schema 1.2 `
  --schema .\data\schema\data_schema_v1_2.json `
  --report .\data\reports\m1\terms_applied_schema_validation.json

if ($LASTEXITCODE -ne 0) { throw '写入 terms_checked_at 后 Schema 校验失败。' }

& $Python .\data-tooling\m1_readiness.py audit `
  --dataset-root $DatasetRoot `
  --output .\data\reports\m1\m1_data_audit.json
```

检查最新 audit 中 `terms_checked_records` 已覆盖要进入正式池的记录。其他未核验平台保持 `null`，不得进入 public/Gold。

### 9.2 隐私：B 主责

先执行一次不带人工批准的扫描；这时任何记录都不会被错误地自动批准为 public：

```powershell
$PrivacyReportDir = Join-Path $RepoRoot 'data\reports\m1\privacy'
$PrivacyApproval = Join-Path $PrivacyReportDir 'privacy_approval.json'
$PublicAllowlist = Join-Path $PrivacyReportDir 'public_allowlist.json'

& $Python .\data-tooling\annotation\privacy_scan.py `
  --input $CandidateFile `
  --output-dir $PrivacyReportDir `
  --public-allowlist $PublicAllowlist
```

工作顺序：

1. 规则扫描找出电话、邮箱、地址、身份证样式、二维码/水印等风险。
2. Qwen 对命中项做摘要和严重度排序，减少人工阅读时间。
3. B 必须人工查看所有高风险/命中项。
4. B 对自动判定为“无风险”的记录再随机抽查至少 10%。
5. 所有进入正式 κ、Gold 和发布切分的记录都必须在人工审批清单中。
6. 被排除的记录写明 `post_id`、原因和处理方式。

人工审批文件固定为：

```text
data/reports/m1/privacy/privacy_approval.json
```

它必须是一个 JSON 对象，至少包含：

```json
{
  "reviewer": "B",
  "reviewed_at": "ISO-8601",
  "scope": "M1 formal kappa, Gold and release splits",
  "post_ids": ["人工确认可发布的 post_id"],
  "excluded": [
    {"post_id": "...", "decision": "redact|exclude", "reason": "..."}
  ]
}
```

AI 只能生成待审草稿，`reviewer`、`post_ids` 和最终 `decision` 必须由 B 确认。A 随机抽查 30 条高风险/边界样本。扫描器检测到敏感项的记录即使列入批准清单也仍会留在 interim；必须先脱敏或排除，再重新扫描。

人工审批完成后重跑：

```powershell
& $Python .\data-tooling\annotation\privacy_scan.py `
  --input $CandidateFile `
  --output-dir $PrivacyReportDir `
  --public-allowlist $PublicAllowlist `
  --approval-file $PrivacyApproval

if ($LASTEXITCODE -ne 0) { throw '隐私扫描失败。' }
```

通过条件：正式数据范围内不存在未处理的高风险项，审批清单与正式批次 post_id 可对账。

把隐私扫描器最终生成的 public allowlist 精确导出为正式可抽样池。Round 1、Round 2 和 Gold 只能从这个文件锁定：

```powershell
$AllowlistPayload = Get-Content -LiteralPath $PublicAllowlist -Raw -Encoding UTF8 | ConvertFrom-Json
$ApprovedIds = [System.Collections.Generic.HashSet[string]]::new()
foreach ($id in $AllowlistPayload.post_ids) { [void]$ApprovedIds.Add([string]$id) }

$FormalLines = [System.Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $CandidateFile -Encoding UTF8 | ForEach-Object {
  if ([string]::IsNullOrWhiteSpace($_)) { return }
  $row = $_ | ConvertFrom-Json
  if ($ApprovedIds.Contains([string]$row.post_id)) { $FormalLines.Add($_) }
}

if ($FormalLines.Count -lt 2050) {
  throw "正式可用隐私批准记录不足 2050 条：$($FormalLines.Count)"
}
[IO.File]::WriteAllLines($FormalCandidateFile, $FormalLines, [Text.UTF8Encoding]::new($false))
Get-FileHash -LiteralPath $FormalCandidateFile -Algorithm SHA256
[pscustomobject]@{ FormalEligibleCount = $FormalLines.Count; Path = $FormalCandidateFile }
```

如果不足 2,050 条，先完成脱敏、重新审批或新增候选；不能从未批准记录中抽样。

---

## 10. 阶段 4：Qwen 本机性能与质量校准（B 主责，A 复核，2–4 小时）

### 10.1 先跑现有自动判定单测

```powershell
& $Python -m pytest .\data-tooling\annotation\tests\test_auto_judge.py -q
if ($LASTEXITCODE -ne 0) { throw '自动判定相关测试失败。' }
```

当前版本的预期结果是 `21 passed`；如数量随代码版本变化，以退出码 0 为通过标准。

### 10.2 只做小批量预标注，不做全量自动接受

```powershell
$CalibrationRoot = Join-Path $RepoRoot 'data\run_outputs\m1_calibration_50'

& $Python .\data-tooling\annotation\batch_pre_annotate.py `
  --input $CandidateFile `
  --output-dir $CalibrationRoot `
  --ollama-model $Model `
  --ollama-url 'http://127.0.0.1:11434' `
  --timeout 120 `
  --keep-alive '30m' `
  --auto-threshold 0.95 `
  --no-images `
  --media-base $DatasetRoot `
  --limit 50 `
  --annotator-id 'model_calibration'
```

注意：此阶段生成的 `auto_*.jsonl`、`suggest_*.jsonl` 仅用于速度和故障率校准，绝不能进入正式 κ 或 Gold。

记录以下数据：

- 首条冷启动耗时。
- 后续 49 条的中位耗时、P90 耗时。
- `fallback_used=true` 的数量。
- JSON 解析失败数。
- GPU/CPU 使用情况。
- A/B 对 20 条输出的人工合理性抽查。

建议决策：

- 9B 可稳定运行、没有明显 CPU 回退、速度可接受：保留 9B。
- OOM、系统卡死、P90 过高或频繁 CPU 回退：切到 4B，重新跑同一校准。
- 两个模型都不稳定：Gold 改为 `--no-llm`，M1 有效性不受影响，只是人工时间增加。

不得用这 50 条的模型建议来宣称论文准确率。

---

## 11. 阶段 5：冻结批次并导出可标注 JSONL（B 执行，C 封存，1–2 小时）

### 11.1 为什么需要额外导出

`lock_annotation_batch.py` 生成的是带 `post_ids` 的 manifest，不是可直接送给标注器的 JSONL。因此必须按 manifest 从 canonical JSONL 精确导出，并校验缺失、重复和数量。

### 11.2 在当前 PowerShell 定义导出函数

```powershell
function Export-LockedBatch {
  param(
    [Parameter(Mandatory=$true)][string]$ManifestPath,
    [Parameter(Mandatory=$true)][string]$SourceJsonl,
    [Parameter(Mandatory=$true)][string]$OutputJsonl
  )

  $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $wanted = [System.Collections.Generic.HashSet[string]]::new()
  foreach ($id in $manifest.post_ids) {
    if (-not $wanted.Add([string]$id)) { throw "Manifest 含重复 post_id：$id" }
  }

  $found = @{}
  Get-Content -LiteralPath $SourceJsonl -Encoding UTF8 | ForEach-Object {
    if ([string]::IsNullOrWhiteSpace($_)) { return }
    $record = $_ | ConvertFrom-Json
    $id = [string]$record.post_id
    if ($wanted.Contains($id)) {
      if ($found.ContainsKey($id)) { throw "源文件含重复 post_id：$id" }
      $found[$id] = $_
    }
  }

  $missing = @($manifest.post_ids | Where-Object { -not $found.ContainsKey([string]$_) })
  if ($missing.Count -gt 0) { throw "缺失 post_id：$($missing -join ', ')" }

  $ordered = @($manifest.post_ids | ForEach-Object { $found[[string]$_] })
  if ($ordered.Count -ne $wanted.Count) { throw '导出条数与 manifest 不一致。' }

  $parent = Split-Path -Parent $OutputJsonl
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  [IO.File]::WriteAllLines($OutputJsonl, $ordered, [Text.UTF8Encoding]::new($false))

  Get-FileHash -LiteralPath $OutputJsonl -Algorithm SHA256
  [pscustomobject]@{ Count = $ordered.Count; Output = $OutputJsonl }
}
```

### 11.3 定义四个互斥批次

| 批次 | 数量 | AI | 目的 |
|---|---:|---|---|
| round1 | 100 | 关闭 | 指南磨合，不作为正式第二轮 |
| round2 | 150 | 关闭 | 正式独立盲标与 κ |
| gold_control | 180 | 关闭 | Gold 中 10% 无 AI 对照 |
| gold_assisted | 1,620 | Qwen 建议 | Gold 主池 |

总计 2,050 个互不重叠的 post_id。

所有 manifest、导出 JSONL、SHA-256 和创建时间放到：

```text
data/reports/m1/locked_batches/
```

先定义累计排除 manifest 函数：

```powershell
function New-CumulativeManifest {
  param(
    [Parameter(Mandatory=$true)][string[]]$ManifestPaths,
    [Parameter(Mandatory=$true)][string]$OutputPath
  )

  if (Test-Path -LiteralPath $OutputPath) {
    throw "拒绝覆盖已存在的累计 manifest：$OutputPath"
  }

  $ids = [System.Collections.Generic.HashSet[string]]::new()
  foreach ($path in $ManifestPaths) {
    $manifest = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($id in $manifest.post_ids) { [void]$ids.Add([string]$id) }
  }

  $payload = [ordered]@{
    created_at = [DateTimeOffset]::UtcNow.ToString('o')
    source_manifests = $ManifestPaths
    post_ids = @(@($ids) | Sort-Object)
  }
  $parent = Split-Path -Parent $OutputPath
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  [IO.File]::WriteAllText(
    $OutputPath,
    (($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
    [Text.UTF8Encoding]::new($false)
  )
  Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256
}
```

然后逐批锁定。以下 seed 必须保留，以便复现：

```powershell
$LockedRoot = Join-Path $RepoRoot 'data\reports\m1\locked_batches'
$Guide = Join-Path $RepoRoot 'docs\annotation_guide_v1.md'
New-Item -ItemType Directory -Force -Path $LockedRoot | Out-Null

$Round1Manifest = Join-Path $LockedRoot 'round1_manifest.json'
& $Python .\data-tooling\annotation\lock_annotation_batch.py `
  --candidates $FormalCandidateFile `
  --guide $Guide `
  --output $Round1Manifest `
  --batch-id 'm1_round1_100' `
  --count 100 `
  --seed 101 `
  --batch-kind pilot `
  --require-platform bilibili `
  --require-platform wechat_official_account `
  --require-media-state available

$Round2Manifest = Join-Path $LockedRoot 'round2_manifest.json'
& $Python .\data-tooling\annotation\lock_annotation_batch.py `
  --candidates $FormalCandidateFile `
  --guide $Guide `
  --output $Round2Manifest `
  --batch-id 'm1_round2_formal_150' `
  --count 150 `
  --seed 202 `
  --batch-kind formal_kappa `
  --formal-second-round `
  --previous-manifest $Round1Manifest `
  --require-platform bilibili `
  --require-platform wechat_official_account `
  --require-media-state available

$PriorRound2 = Join-Path $LockedRoot 'exclude_round1_round2.json'
New-CumulativeManifest `
  -ManifestPaths @($Round1Manifest, $Round2Manifest) `
  -OutputPath $PriorRound2

$ControlManifest = Join-Path $LockedRoot 'gold_control_manifest.json'
& $Python .\data-tooling\annotation\lock_annotation_batch.py `
  --candidates $FormalCandidateFile `
  --guide $Guide `
  --output $ControlManifest `
  --batch-id 'm1_gold_control_180' `
  --count 180 `
  --seed 303 `
  --batch-kind formal_gold `
  --previous-manifest $PriorRound2 `
  --require-platform bilibili `
  --require-platform wechat_official_account `
  --require-media-state available

$PriorControl = Join-Path $LockedRoot 'exclude_round1_round2_control.json'
New-CumulativeManifest `
  -ManifestPaths @($Round1Manifest, $Round2Manifest, $ControlManifest) `
  -OutputPath $PriorControl

$AssistedManifest = Join-Path $LockedRoot 'gold_assisted_manifest.json'
& $Python .\data-tooling\annotation\lock_annotation_batch.py `
  --candidates $FormalCandidateFile `
  --guide $Guide `
  --output $AssistedManifest `
  --batch-id 'm1_gold_assisted_1620' `
  --count 1620 `
  --seed 404 `
  --batch-kind formal_gold `
  --previous-manifest $PriorControl `
  --require-platform bilibili `
  --require-platform wechat_official_account `
  --require-media-state available

if ($LASTEXITCODE -ne 0) { throw '批次锁定失败。' }
```

脚本拒绝覆盖已有 manifest。如果需要重做，必须换新的 batch-id、文件名和 seed，并保留旧文件作为审计证据。

按 manifest 导出四个 JSONL：

```powershell
$Exports = @(
  @{ Manifest = $Round1Manifest; Output = (Join-Path $LockedRoot 'round1.jsonl') },
  @{ Manifest = $Round2Manifest; Output = (Join-Path $LockedRoot 'round2.jsonl') },
  @{ Manifest = $ControlManifest; Output = (Join-Path $LockedRoot 'gold_control.jsonl') },
  @{ Manifest = $AssistedManifest; Output = (Join-Path $LockedRoot 'gold_assisted.jsonl') }
)

foreach ($item in $Exports) {
  Export-LockedBatch `
    -ManifestPath $item.Manifest `
    -SourceJsonl $FormalCandidateFile `
    -OutputJsonl $item.Output
}
```

C 的轻量工作：核对四个 manifest 的数量和哈希，并运行以下交集检查：

```powershell
$Owner = @{}
foreach ($manifestPath in @($Round1Manifest, $Round2Manifest, $ControlManifest, $AssistedManifest)) {
  $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  foreach ($id in $manifest.post_ids) {
    $key = [string]$id
    if ($Owner.ContainsKey($key)) {
      throw "批次 post_id 重叠：$id；出现在 $($Owner[$key]) 和 $manifestPath"
    }
    $Owner[$key] = $manifestPath
  }
}
if ($Owner.Count -ne 2050) { throw "四批唯一 post_id 应为 2050，实际为 $($Owner.Count)" }
'PASS: 四批无交集，共 2050 条。'
```

---

## 12. 阶段 6：Round 1 指南磨合（A/B 各 3–5 小时）

### 12.1 盲标规则

- A、B 使用不同电脑账户或至少不同输出目录。
- 不得查看对方输出、聊天讨论单条结果或共享实时进度。
- 关闭 Qwen、关闭自动补充。
- 有媒体的记录必须查看媒体；不能只读文字。
- 不确定时选择 `uncertain`，不要猜。

### 12.2 A 侧命令

```powershell
$Round1 = Join-Path $RepoRoot 'data\reports\m1\locked_batches\round1.jsonl'
$Round1A = Join-Path $RepoRoot 'data\run_outputs\m1_annotations\round1\A'

& $Python .\data-tooling\annotation\manual_review_annotate.py `
  --input $Round1 `
  --guide .\docs\annotation_guide_v1.md `
  --output-dir $Round1A `
  --limit 100 `
  --no-llm `
  --no-supplement `
  --media-base $DatasetRoot `
  --auto-view `
  --annotator-id 'A' `
  --auto-threshold 0
```

### 12.3 B 侧命令

```powershell
$Round1B = Join-Path $RepoRoot 'data\run_outputs\m1_annotations\round1\B'

& $Python .\data-tooling\annotation\manual_review_annotate.py `
  --input $Round1 `
  --guide .\docs\annotation_guide_v1.md `
  --output-dir $Round1B `
  --limit 100 `
  --no-llm `
  --no-supplement `
  --media-base $DatasetRoot `
  --auto-view `
  --annotator-id 'B' `
  --auto-threshold 0
```

脚本支持续标：中断后使用相同输出目录再次运行，会跳过已完成 post_id。

### 12.4 Round 1 解盲

两人都完成后才计算：

```powershell
$Round1AFile = Get-ChildItem -LiteralPath $Round1A -File -Filter 'A_*.json*' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

$Round1BFile = Get-ChildItem -LiteralPath $Round1B -File -Filter 'B_*.json*' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

& $Python .\data-tooling\annotation\calculate_agreement.py `
  $Round1AFile `
  $Round1BFile `
  --output .\data\reports\m1\round1_agreement.json
```

不要给 Round 1 增加 `--formal-second-round`。此轮用于：

- 找出标签定义分歧。
- 修改/补充 annotation guide 的具体例子。
- 统一媒体查看规则。
- 记录争议类型，而不是追求“讨论到 κ 变高”。

指南冻结后，由 C 记录文件 SHA-256。正式 Round 2 开始后不得继续改指南。

---

## 13. 阶段 7：正式 Round 2 盲标与 Cohen’s κ（A/B 各 5–8 小时）

### 13.1 正式命令

把输入改为：

```text
data\reports\m1\locked_batches\round2.jsonl
```

A、B 分别运行与第 12 节完全相同的命令，只把输出目录改为：

```text
data\run_outputs\m1_annotations\round2\A
data\run_outputs\m1_annotations\round2\B
```

强制检查命令中包含：

```text
--no-llm --no-supplement --auto-threshold 0
```

### 13.2 计算正式 κ

先从各输出目录确定唯一标注文件：

```powershell
$Round2AFile = Get-ChildItem .\data\run_outputs\m1_annotations\round2\A -File |
  Where-Object { $_.Extension -in '.json', '.jsonl' } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

$Round2BFile = Get-ChildItem .\data\run_outputs\m1_annotations\round2\B -File |
  Where-Object { $_.Extension -in '.json', '.jsonl' } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

$Round2AFile
$Round2BFile
```

生成正式报告：

```powershell
& $Python .\data-tooling\annotation\calculate_agreement.py `
  $Round2AFile `
  $Round2BFile `
  --formal-second-round `
  --output .\data\reports\m1\formal_second_round_agreement.json

if ($LASTEXITCODE -ne 0) { throw '正式 κ 计算失败。' }
```

输出路径固定为：

```text
data/reports/m1/formal_second_round_agreement.json
```

通过条件：

- 150 条批次全部完成或报告明确说明排除原因。
- 两个 annotator_id 分别为 A、B。
- 没有 `auto_accepted/system/nonhuman`。
- 报告标记为 formal。
- κ `>= 0.60`。

若 κ `< 0.60`：停止 Gold 生产，解盲后修订指南，再锁定一个全新的 150 条批次重做。不得挑删分歧样本来抬高 κ。

---

## 14. 阶段 8：Gold 的 180 条无 AI 对照组（A/B 各 5–8 小时）

输入：

```text
data\reports\m1\locked_batches\gold_control.jsonl
```

A、B 使用第 12 节的纯人工命令：

```text
--no-llm --no-supplement --auto-threshold 0
```

输出目录：

```text
data\run_outputs\m1_annotations\gold_control\A
data\run_outputs\m1_annotations\gold_control\B
```

这 180 条可以进入 Gold，但不能与 Round 2 重叠。它的用途是与 AI 辅助组对比人工一致率、耗时和标签分布，检查共同看到 Qwen 建议是否造成锚定。

---

## 15. 阶段 9：Gold 的 1,620 条 Qwen 辅助双人确认（A/B 各 14–27 小时）

### 15.1 强制规则

- Qwen 的建议不是标签真值。
- A、B 各自运行，不得查看对方输出。
- 每条都必须由人按键确认或修改。
- 必须使用 `--auto-threshold 0`，不能用 0.85、0.90 或 0.95。
- 使用 `--no-supplement`，防止其他自动逻辑补标签。
- 记录必须最终保存为 `annotation_method="human"`。
- 有图像/视频帧时必须查看；文字模型建议不能代替视觉核验。

### 15.2 A 侧命令

```powershell
$GoldAssisted = Join-Path $RepoRoot 'data\reports\m1\locked_batches\gold_assisted.jsonl'
$GoldAssistedA = Join-Path $RepoRoot 'data\run_outputs\m1_annotations\gold_assisted\A'

& $Python .\data-tooling\annotation\manual_review_annotate.py `
  --input $GoldAssisted `
  --guide .\docs\annotation_guide_v1.md `
  --output-dir $GoldAssistedA `
  --limit 300 `
  --no-supplement `
  --media-base $DatasetRoot `
  --auto-view `
  --annotator-id 'A' `
  --auto-threshold 0 `
  --ollama-backend `
  --ollama-model $Model `
  --ollama-url 'http://127.0.0.1:11434' `
  --ollama-timeout 120
```

### 15.3 B 侧命令

```powershell
$GoldAssistedB = Join-Path $RepoRoot 'data\run_outputs\m1_annotations\gold_assisted\B'

& $Python .\data-tooling\annotation\manual_review_annotate.py `
  --input $GoldAssisted `
  --guide .\docs\annotation_guide_v1.md `
  --output-dir $GoldAssistedB `
  --limit 300 `
  --no-supplement `
  --media-base $DatasetRoot `
  --auto-view `
  --annotator-id 'B' `
  --auto-threshold 0 `
  --ollama-backend `
  --ollama-model $Model `
  --ollama-url 'http://127.0.0.1:11434' `
  --ollama-timeout 120
```

每次只做 300 条，休息并检查输出后，以同一命令和同一目录续标。脚本会跳过已经完成的 post_id，直到 1,620 条结束。

### 15.4 单条操作方法

1. 阅读正文、标题、标签和平台信息。
2. 查看 Qwen 建议、置信度与理由，但不立即接受。
3. 若记录有媒体，使用标注器的查看命令/按键打开媒体；至少检查广告主体、品牌、字幕、口播/水印线索。
4. 判断 Qwen 建议是否符合 annotation guide。
5. 建议正确时按 `y`，仍然是一次人工确认。
6. 建议错误时按 `n`，人工修改 label、subcategory、confidence 和理由。
7. 无法判断时标 `uncertain`；不要为了凑 1,500 条强行给标签。

### 15.5 每 300 条的暂停检查

检查内容：

- A/B 是否都完成同一数量。
- 输出中是否出现 `auto_accepted`、`system` 或 annotator_id 错误。
- Ollama fallback/超时是否异常上升。
- 各标签数量是否突然塌缩为单一类别。
- AI 辅助组与无 AI 对照组的分布是否有异常大偏移。

停止条件：

- 发现任何自动保存进入正式输出。
- 模型错误/回退连续出现。
- 人工未查看媒体就批量接受。
- A/B 开始共享单条答案。
- 滚动一致率明显低于 Round 2，或某一类异常消失。

---

## 16. 阶段 10：解盲、人工裁决与生成 Gold（A/B 主责，C 抽查，8–14 小时）

### 16.1 合并原则

先分别对 `gold_control` 和 `gold_assisted` 计算一致性报告，再合并进入 Gold 构建流程。

Gold 可进入条件：

- A、B 标签一致；或
- A、B 在解盲后共同完成裁决，并留下裁决人、时间和理由。

必须排除：

- `uncertain`、`out_of_scope`、缺失标签。
- 同一 annotator 的两份标签。
- `auto_accepted`、`system`、`model_calibration`。
- 未完成隐私审批或来源许可范围不明的记录。
- 无法完成裁决的记录。

### 16.2 裁决文件

固定路径：

```text
data/reports/m1/adjudication.jsonl
```

每行至少：

```json
{"post_id":"...","label":"明广|暗广|非广","conflict_reason":"A/B 分歧点","arbiter":"A+B","arbiter_note":"共同复核后的依据","decided_at":"ISO-8601"}
```

C 只随机抽查 30–50 条裁决记录，核对原文、A/B 原标签和理由，不承担全量裁决。

### 16.3 构建 Gold

先定位四个输出文件并分别计算对照组/AI 辅助组的一致性：

```powershell
$ControlAFile = Get-ChildItem .\data\run_outputs\m1_annotations\gold_control\A -File -Filter 'A_*.json*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
$ControlBFile = Get-ChildItem .\data\run_outputs\m1_annotations\gold_control\B -File -Filter 'B_*.json*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
$AssistedAFile = Get-ChildItem .\data\run_outputs\m1_annotations\gold_assisted\A -File -Filter 'A_*.json*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
$AssistedBFile = Get-ChildItem .\data\run_outputs\m1_annotations\gold_assisted\B -File -Filter 'B_*.json*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName

& $Python .\data-tooling\annotation\calculate_agreement.py `
  $ControlAFile $ControlBFile `
  --output .\data\reports\m1\gold_control_agreement.json

& $Python .\data-tooling\annotation\calculate_agreement.py `
  $AssistedAFile $AssistedBFile `
  --output .\data\reports\m1\gold_assisted_agreement.json
```

这两个报告都不要增加 `--formal-second-round`；M1 正式 κ 只来自第 13 节。

`build_gold_dataset.py` 每侧只接收一个标注流，因此先把 A 的两个批次拼接，把 B 的两个批次拼接。原文件保持不动：

```powershell
function Join-AnnotationStreams {
  param(
    [Parameter(Mandatory=$true)][string[]]$InputPaths,
    [Parameter(Mandatory=$true)][string]$OutputPath
  )
  if (Test-Path -LiteralPath $OutputPath) { throw "拒绝覆盖：$OutputPath" }
  $builder = [Text.StringBuilder]::new()
  foreach ($path in $InputPaths) {
    $text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    [void]$builder.Append($text.Trim())
    [void]$builder.Append([Environment]::NewLine)
  }
  $parent = Split-Path -Parent $OutputPath
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  [IO.File]::WriteAllText($OutputPath, $builder.ToString(), [Text.UTF8Encoding]::new($false))
  Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256
}

$GoldWork = Join-Path $RepoRoot 'data\run_outputs\m1_annotations\gold_combined'
$GoldACombined = Join-Path $GoldWork 'A_gold_combined.json'
$GoldBCombined = Join-Path $GoldWork 'B_gold_combined.json'

Join-AnnotationStreams -InputPaths @($ControlAFile, $AssistedAFile) -OutputPath $GoldACombined
Join-AnnotationStreams -InputPaths @($ControlBFile, $AssistedBFile) -OutputPath $GoldBCombined
```

最后构建 Gold：

```powershell
$AdjudicationFile = Join-Path $RepoRoot 'data\reports\m1\adjudication.jsonl'
$GoldFile = Join-Path $RepoRoot 'data\gold\gold_v1.jsonl'
$GoldExcluded = Join-Path $RepoRoot 'data\reports\m1\gold_excluded.jsonl'
$GoldReport = Join-Path $RepoRoot 'data\reports\m1\gold_build_report.json'

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $GoldFile) | Out-Null

& $Python .\data-tooling\annotation\build_gold_dataset.py `
  $GoldACombined `
  $GoldBCombined `
  $AdjudicationFile `
  $GoldFile `
  --report $GoldReport `
  --excluded-output $GoldExcluded `
  --min-confidence 0.6

if ($LASTEXITCODE -ne 0) { throw 'Gold 构建失败。' }
Get-Content -LiteralPath $GoldReport -Encoding UTF8
```

固定输出：

```text
data/gold/gold_v1.jsonl
data/reports/m1/gold_build_report.json
```

通过条件：

- Gold 唯一 post_id `>= 1500`。
- 没有非法 annotation_method。
- 没有同一 annotator 配对。
- 排除原因统计完整。
- 随机抽 50 条能回溯 canonical record、A/B 标签和裁决。

---

## 17. 阶段 11：为创作者隔离切分补齐元数据（B 主责，A 复核，2–4 小时）

`build_gold_dataset.py` 的 Gold 输出不携带 `blogger_id` 和 `content_group_id`。直接切分会导致错误的“零泄漏”结论。因此必须按 `post_id` 把 Gold 标签回连到 canonical candidate。`blogger_id` 必须非空；没有检测到近重复关系时，`content_group_id=null` 是允许的。

### 17.1 在 PowerShell 定义回连函数

```powershell
function New-SplitInput {
  param(
    [Parameter(Mandatory=$true)][string]$GoldJsonl,
    [Parameter(Mandatory=$true)][string]$CanonicalJsonl,
    [Parameter(Mandatory=$true)][string]$OutputJsonl
  )

  $canonical = @{}
  Get-Content -LiteralPath $CanonicalJsonl -Encoding UTF8 | ForEach-Object {
    if ([string]::IsNullOrWhiteSpace($_)) { return }
    $row = $_ | ConvertFrom-Json
    $id = [string]$row.post_id
    if ($canonical.ContainsKey($id)) { throw "Canonical 重复 post_id：$id" }
    $canonical[$id] = $row
  }

  $seen = [System.Collections.Generic.HashSet[string]]::new()
  $lines = [System.Collections.Generic.List[string]]::new()

  Get-Content -LiteralPath $GoldJsonl -Encoding UTF8 | ForEach-Object {
    if ([string]::IsNullOrWhiteSpace($_)) { return }
    $gold = $_ | ConvertFrom-Json
    $id = [string]$gold.post_id
    if (-not $seen.Add($id)) { throw "Gold 重复 post_id：$id" }
    if (-not $canonical.ContainsKey($id)) { throw "Canonical 缺失 Gold post_id：$id" }

    $source = $canonical[$id]
    if ([string]::IsNullOrWhiteSpace([string]$source.blogger_id)) {
      throw "缺失 blogger_id：$id"
    }
    $record = [ordered]@{
      post_id = $id
      label = $gold.label
      blogger_id = $source.blogger_id
      content_group_id = $source.content_group_id
    }
    $lines.Add(($record | ConvertTo-Json -Compress -Depth 8))
  }

  if ($lines.Count -lt 1500) { throw "Split 输入少于 1500 条：$($lines.Count)" }
  $parent = Split-Path -Parent $OutputJsonl
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  [IO.File]::WriteAllLines($OutputJsonl, $lines, [Text.UTF8Encoding]::new($false))
  Get-FileHash -LiteralPath $OutputJsonl -Algorithm SHA256
  [pscustomobject]@{ Count = $lines.Count; Output = $OutputJsonl }
}
```

执行：

```powershell
$GoldFile = Join-Path $RepoRoot 'data\gold\gold_v1.jsonl'
$SplitInput = Join-Path $RepoRoot 'data\gold\gold_v1_with_groups.jsonl'

New-SplitInput `
  -GoldJsonl $GoldFile `
  -CanonicalJsonl $CandidateFile `
  -OutputJsonl $SplitInput
```

### 17.2 创作者与近重复隔离

```powershell
$SplitRoot = Join-Path $RepoRoot 'data\splits\m1'
New-Item -ItemType Directory -Force -Path $SplitRoot | Out-Null

& $Python .\data-tooling\annotation\split_by_blogger.py `
  $SplitInput `
  (Join-Path $SplitRoot 'train_ids.txt') `
  (Join-Path $SplitRoot 'dev_ids.txt') `
  (Join-Path $SplitRoot 'test_ids.txt') `
  --report .\data\reports\m1\split_report.json `
  --seed 42

if ($LASTEXITCODE -ne 0) { throw '创作者隔离切分失败。' }
Get-Content -LiteralPath .\data\reports\m1\split_report.json -Encoding UTF8
```

通过条件：

- 任一 `blogger_id` 只出现在一个 split。
- 任一 `content_group_id` 只出现在一个 split。
- train/validation/test 条数之和等于 Gold 条数。
- 报告不存在缺失 group 或静默丢行。

---

## 18. 阶段 12：Dataset Card 与最终 M1 Gate（D 终审，A/B 提供证据，2–4 小时）

### 18.1 Dataset Card 必须披露

- 候选数量、Gold 数量、平台分布、创作者数量。
- 数据获取日期和来源条款证据。
- 隐私扫描、人工审批范围和排除规则。
- Round 2 样本量、A/B 独立性、κ 数值。
- Gold 中 180 条纯人工对照、1,620 条 Qwen 辅助池的设计。
- Qwen 模型完整 tag、Ollama 版本、`think:false`、temperature 0、keep_alive。
- AI 只提供建议，`--auto-threshold 0`，所有 Gold 标签由两个人分别确认。
- `auto_accepted/system` 永不进入 Gold。
- 创作者隔离与 `content_group_id` 近重复隔离结果。
- 已知局限：共享 Qwen 建议可能产生锚定，因此保留 10% 无 AI 对照并单独报告。

### 18.2 更新状态的原则

文件：

```text
data/reports/m1/dataset_card_status.json
```

只有对应证据文件已经存在且 D 检查通过，才把布尔值改成 `true`。不能因为“计划完成”或“测试通过”提前修改。

### 18.3 最终门禁

```powershell
& $Python .\data-tooling\m1_readiness.py gate `
  --audit .\data\reports\m1\m1_data_audit.json `
  --guide .\docs\annotation_guide_v1.md `
  --agreement .\data\reports\m1\formal_second_round_agreement.json `
  --dataset-card-status .\data\reports\m1\dataset_card_status.json `
  --gold-report .\data\reports\m1\gold_build_report.json `
  --split-report .\data\reports\m1\split_report.json `
  --output .\data\reports\m1\m1_gate_report.json

$GateExitCode = $LASTEXITCODE
Get-Content -LiteralPath .\data\reports\m1\m1_gate_report.json -Encoding UTF8
$GateExitCode
if ($GateExitCode -ne 0) { throw 'M1 尚未通过；按 gate 报告逐项修复。' }
```

最终通过条件：退出码为 0，报告 `passed=true`，所有 gate 都有可追溯证据。

---

## 19. A/B/C/D 每日执行路线

### A：主负责人一，35–55 小时

1. 第 1 天：确认 `.venv`、安装 Ollama、设置 D 盘模型目录、拉取模型、API smoke。
2. 第 1–2 天：解压、schema、媒体、指纹审计。
3. 第 2–3 天：新增 120–150 条、增量合并、恢复 `>=3000`。
4. 第 2–3 天：完成平台官方条款证据，交 B 抽查。
5. 第 3 天：Round 1 A 侧纯人工盲标。
6. 第 4 天：Round 1 解盲、共同修订指南。
7. 第 4–5 天：Round 2 A 侧正式纯人工盲标。
8. 第 5–6 天：Gold control 180 条 A 侧纯人工。
9. 第 6–10 天：Gold assisted 1,620 条 A 侧逐条确认，每 300 条暂停检查。
10. 第 10–11 天：与 B 解盲裁决，抽查 Gold 与 split。

### B：主负责人二，35–55 小时

1. 第 1 天：复核环境，完成 50 条 Qwen 校准，决定 9B/4B。
2. 第 2–3 天：隐私扫描、Qwen 风险排序、人工审批。
3. 第 2–3 天：锁定四个互斥批次并导出 JSONL。
4. 第 3 天：Round 1 B 侧纯人工盲标。
5. 第 4 天：Round 1 解盲、冻结指南。
6. 第 4–5 天：Round 2 B 侧正式纯人工盲标并生成 κ 报告。
7. 第 5–6 天：Gold control 180 条 B 侧纯人工。
8. 第 6–10 天：Gold assisted 1,620 条 B 侧逐条确认，每 300 条暂停检查。
9. 第 10–11 天：共同裁决、构建 Gold、回连元数据、运行 split。
10. 第 11–12 天：整理所有 M1 报告交 D 终审。

### C：轻量审计，2–4 小时

1. 核对四个 manifest 的数量、时间、SHA-256。
2. 检查四批 post_id 交集为 0。
3. Round 1 后封存 annotation guide 哈希。
4. Gold 完成后随机抽查 30–50 条回溯链。
5. 只报告问题，不代替 A/B 全量裁决。

### D：轻量签字，2–4 小时

1. 检查来源条款证据、隐私审批、正式 κ、Gold、split 五类报告是否齐全。
2. 检查 Dataset Card 是否披露 AI 辅助与 10% 无 AI 对照。
3. 检查所有 `true` 都有证据文件。
4. 运行或见证最终 gate，签字确认退出码和 `passed=true`。

---

## 20. 常见错误与处理

### `ollama` 不是内部或外部命令

重新启动 PowerShell；确认官方安装完成；执行 `Get-Command ollama`。不要临时复制别的电脑路径。

### 9B 显存不足或非常慢

先关闭占 GPU 的其他应用，执行 `nvidia-smi`。仍不合格就切换 `qwen3.5:4b`，不要通过增大超时掩盖持续 OOM。

### 模型输出不是合法 JSON

确认使用提交后的代码、`think:false`、temperature 0；先跑 `data-tooling\annotation\tests\test_auto_judge.py`。故障记录进入 fallback 统计，不得自动接受。

### Flet 缺失

不影响核心命令行路线。只有团队明确需要 GUI 时才安装 `.[annotation]`。

### 标注中断

使用原命令、相同输出目录继续。先备份输出，不要删除或换 annotator_id。

### `auto_accepted` 出现在正式输出

立即停止该批，保留现场用于审计，重新用 `--auto-threshold 0` 从新的干净输出目录开始。不得手工把 `annotation_method` 改成 human。

### A/B 看到了对方答案

受影响批次失去独立性，不能用于正式 κ。锁定新批次重做。

### Gold 超过 1,500 但 gate 仍失败

检查：不同 annotator、人工方法、正式 κ、来源条款、隐私、Dataset Card、blogger/content_group 泄漏。数量不是唯一条件。

### split 报告显示 0 泄漏但没有 blogger_id

这是无效证据。必须先执行 `New-SplitInput`，确保每条都有真实 `blogger_id`，并携带规范化阶段生成的 `content_group_id` 字段；未检测到近重复时该字段可以为 null。

---

## 21. 最终证据清单

- [ ] 候选审计：有效唯一记录 `>=3000`。
- [ ] 媒体审计：引用缺失 0。
- [ ] 四个批次 manifest、JSONL、SHA-256 齐全且交集 0。
- [ ] Round 1 报告与冻结后的 annotation guide 哈希。
- [ ] Round 2 A/B 输出均为 human，正式 κ `>=0.60`。
- [ ] 180 条 Gold control 完成双人独立标注。
- [ ] 1,620 条 Gold assisted 完成双人逐条人工确认。
- [ ] `auto_accepted/system/model_calibration` 均未进入 Gold。
- [ ] Gold `>=1500`，排除与裁决记录完整。
- [ ] 来源条款证据含官方 URL、访问时间与双人核验。
- [ ] 正式数据隐私人工审批清单完整。
- [ ] split 中 creator overlap 为 0。
- [ ] split 中 content_group overlap 为 0。
- [ ] Dataset Card 披露模型、AI 辅助方式、对照组与局限。
- [ ] `m1_gate_report.json` 为 `passed=true`，命令退出码 0。

---

## 22. 不得做的事

- 不得把 Qwen 自动接受结果包装成人工 Gold。
- 不得用 AI 同时扮演两个独立 annotator。
- 不得在正式 Round 2 中打开 Qwen。
- 不得让 A/B 在解盲前共享单条答案。
- 不得用旧机器的速度或正确率替代本机 50 条校准。
- 不得覆盖原始 2,901 条数据目录。
- 不得为达到 1,500 条而纳入 uncertain、out_of_scope 或未审批记录。
- 不得在缺少 `blogger_id` 或没有运行 content-group 生成/回连流程时宣称无泄漏。
- 不得在证据未完成时把 Dataset Card 状态改为 `true`。
- 不得把工程单测绿色等同于 M1 正式验收通过。
