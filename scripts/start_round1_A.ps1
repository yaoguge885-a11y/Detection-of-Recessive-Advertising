$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$InputFile = Join-Path $RepoRoot 'data\reports\m1\locked_batches\round1.jsonl'
$ManifestFile = Join-Path $RepoRoot 'data\reports\m1\locked_batches\round1_manifest.json'
$Guide = Join-Path $RepoRoot 'docs\annotation_guide_v1.md'
$OutputDir = Join-Path $RepoRoot 'data\run_outputs\m1_annotations\round1\A'
$MediaBase = Get-ChildItem -LiteralPath $RepoRoot -Directory |
    ForEach-Object { Join-Path $_.FullName 'merged_20260728' } |
    Where-Object { Test-Path -LiteralPath (Join-Path $_ 'anonymized_posts.jsonl') } |
    Select-Object -First 1

if (-not $MediaBase) {
    throw 'Could not locate the extracted merged_20260728 dataset directory.'
}

foreach ($required in @($Python, $InputFile, $ManifestFile, $Guide, $MediaBase)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing Round 1 dependency: $required"
    }
}

$Manifest = Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
$ActualHash = (Get-FileHash -LiteralPath $InputFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne ([string]$Manifest.output_sha256).ToLowerInvariant()) {
    throw 'round1.jsonl does not match its locked manifest.'
}

Write-Host "Round 1 A input: $InputFile"
Write-Host "Round 1 A output: $OutputDir"
Write-Host 'For each post: press v to inspect media, then n to annotate. Press q to save and quit.'

& $Python (Join-Path $RepoRoot 'data-tooling\annotation\manual_review_annotate.py') `
    --input $InputFile `
    --guide $Guide `
    --output-dir $OutputDir `
    --limit 100 `
    --no-llm `
    --no-supplement `
    --media-base $MediaBase `
    --annotator-id A

if ($LASTEXITCODE -ne 0) {
    throw "Round 1 A annotator exited with code $LASTEXITCODE"
}
