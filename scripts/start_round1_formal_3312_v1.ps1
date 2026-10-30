param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('A', 'B')]
    [string]$AnnotatorId,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$BatchRoot = Join-Path $RepoRoot 'data\reports\m1\locked_batches\formal_3312_v1'
$InputFile = Join-Path $BatchRoot 'round1.jsonl'
$ManifestFile = Join-Path $BatchRoot 'round1_manifest.json'
$SummaryFile = Join-Path $BatchRoot 'batch_lock_summary.json'
$Guide = Join-Path $RepoRoot 'docs\annotation_guide_v1.md'
$OutputDir = Join-Path $RepoRoot "data\run_outputs\m1_annotations\formal_3312_v1\round1\$AnnotatorId"
$MediaBase = Get-ChildItem -LiteralPath $RepoRoot -Directory |
    ForEach-Object { Join-Path $_.FullName 'merged_20260728' } |
    Where-Object { Test-Path -LiteralPath (Join-Path $_ 'anonymized_posts.jsonl') } |
    Select-Object -First 1

foreach ($required in @($Python, $InputFile, $ManifestFile, $SummaryFile, $Guide, $MediaBase)) {
    if (-not $required -or -not (Test-Path -LiteralPath $required)) {
        throw "Missing formal_3312_v1 Round 1 dependency: $required"
    }
}

$Manifest = Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
$Summary = Get-Content -LiteralPath $SummaryFile -Raw -Encoding UTF8 | ConvertFrom-Json
$ActualHash = (Get-FileHash -LiteralPath $InputFile -Algorithm SHA256).Hash.ToLowerInvariant()
$ExpectedHash = ([string]$Summary.batches.round1.jsonl_sha256).ToLowerInvariant()
$InputCount = @(Get-Content -LiteralPath $InputFile -Encoding UTF8 | Where-Object { $_.Trim() }).Count

if ($Manifest.batch_id -ne 'm1_round1_100_formal_3312_v1') {
    throw 'Unexpected Round 1 batch ID.'
}
if ($Manifest.sample_count -ne 100 -or $InputCount -ne 100) {
    throw "Round 1 count mismatch: manifest=$($Manifest.sample_count), input=$InputCount"
}
if ($ActualHash -ne $ExpectedHash) {
    throw 'round1.jsonl does not match the locked batch summary.'
}

Write-Host "Round 1 $AnnotatorId cohort: formal_3312_v1"
Write-Host "Input: $InputFile"
Write-Host "Output: $OutputDir"
Write-Host "Verified: 100 records; SHA-256 $ActualHash"

if ($CheckOnly) {
    Write-Host 'PASS: startup checks completed; annotator was not launched.'
    return
}

Write-Host 'For each post: press v to inspect media, then n to annotate. Press q to save and quit.'

& $Python (Join-Path $RepoRoot 'data-tooling\annotation\manual_review_annotate.py') `
    --input $InputFile `
    --guide $Guide `
    --output-dir $OutputDir `
    --limit 100 `
    --no-llm `
    --no-supplement `
    --media-base $MediaBase `
    --annotator-id $AnnotatorId

if ($LASTEXITCODE -ne 0) {
    throw "Round 1 $AnnotatorId annotator exited with code $LASTEXITCODE"
}
