[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B")]
    [string]$Role,

    [Parameter(Mandatory = $true)]
    [ValidateSet("kappa", "control", "assisted", "human120", "ai384")]
    [string]$Wave,

    [string]$AnnotatorName = "",

    [ValidateRange(1, 65535)]
    [int]$Port = 8765,

    [string]$Model = "qwen3.5:9b",

    [switch]$NoAi,

    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LockedRoot = Join-Path $RepoRoot "data\reports\m1\locked_batches"
$Launcher = Join-Path $PSScriptRoot "start_html_annotator.ps1"

if (-not (Test-Path -LiteralPath $Launcher)) {
    throw "Launcher not found: $Launcher"
}

$waves = @{
    "kappa"    = @{ Dataset = "round2.jsonl";       Manifest = "waves\kappa_150.json";           BatchId = "m1_kappa_150";               AiAllowed = $false; Label = "正式 kappa 150 条（无 AI）" }
    "control"  = @{ Dataset = "gold_control.jsonl"; Manifest = "waves\gold_control_180.json";   BatchId = "m1_gold_control_180";        AiAllowed = $false; Label = "Gold 无 AI 对照 180 条" }
    "assisted" = @{ Dataset = "gold_assisted.jsonl"; Manifest = "waves\gold_assisted_w1_320.json"; BatchId = "m1_gold_assisted_w1_320"; AiAllowed = $true;  Label = "Gold AI 辅助 320 条" }
    "human120" = @{ Dataset = "gold_control.jsonl"; Manifest = "waves\gold_human_120.json"; BatchId = "m1_gold_human_120"; AiAllowed = $false; Label = "单人人工金标 120 条（无 AI）" }
    "ai384"    = @{ Dataset = "input_gold_remaining_384.jsonl"; DatasetRoot = "data\annotations\preannotated"; Manifest = "waves\gold_ai_384.json"; BatchId = "m1_gold_ai_384"; AiAllowed = $true; SuggestionDir = "data\annotations\preannotated\gold_ai_round2_346"; Label = "Gold AI 辅助 384 条（离线建议）" }
}

$config = $waves[$Wave]
$datasetRoot = $LockedRoot
if ($config.ContainsKey("DatasetRoot")) {
    $datasetRoot = Join-Path $RepoRoot $config.DatasetRoot
}
$datasetPath = Join-Path $datasetRoot $config.Dataset
$manifestPath = Join-Path $LockedRoot $config.Manifest

foreach ($required in @($datasetPath, $manifestPath)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file missing: $required`nRun the batch lock first: python data-tooling\m1_lock_batches.py ..."
    }
}

$suggestionFile = ""
if ($config.ContainsKey("SuggestionDir")) {
    $suggestionRoot = Join-Path $RepoRoot $config.SuggestionDir
    $audit = Get-ChildItem -LiteralPath $suggestionRoot -Filter 'audit_*.jsonl' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $audit) {
        throw "No offline suggestion file found in $suggestionRoot`nRun the batch pre-annotation first."
    }
    $suggestionFile = $audit.FullName
}

$mediaRoot = Join-Path $RepoRoot "data\run_outputs\merged_20260728"
if (-not (Test-Path -LiteralPath $mediaRoot)) {
    throw "Media root missing: $mediaRoot"
}

$effectiveNoAi = $NoAi -or (-not $config.AiAllowed)
if ((-not $config.AiAllowed) -and (-not $NoAi)) {
    Write-Host "[$Wave] 该波次强制关闭 AI 建议（对照组 / kappa 一致性要求）。"
}

$annotatorLabel = $Role
if ($AnnotatorName) { $annotatorLabel = "$Role ($AnnotatorName)" }

Write-Host "波次:     $($config.Label)"
Write-Host "标注人:   $annotatorLabel"
Write-Host "数据集:   $datasetPath"
Write-Host "清单:     $manifestPath"
Write-Host "批次 ID:  $($config.BatchId)"

$launcherArgs = @{
    Dataset     = $datasetPath
    DatasetId   = "m1_formal_3312_v2"
    BatchId     = $config.BatchId
    AnnotatorId = $Role
    MediaRoot   = $mediaRoot
    Manifest    = $manifestPath
    ManifestRole = "approved"
    Model       = $Model
    Port        = $Port
}

if ($suggestionFile) {
    Write-Host "离线建议: $suggestionFile"
    $launcherArgs["SuggestionFile"] = $suggestionFile
}

if ($effectiveNoAi) { $launcherArgs["NoAutoSuggest"] = $true }
if ($CheckOnly) { $launcherArgs["CheckOnly"] = $true }

& $Launcher @launcherArgs
exit $LASTEXITCODE
