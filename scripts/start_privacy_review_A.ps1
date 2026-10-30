$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Reviewer = Join-Path $RepoRoot 'data-tooling\annotation\privacy_review_cli.py'
$Dataset = Join-Path $RepoRoot 'data\interim\m1_candidates_3312_terms_checked.jsonl'
$Sample = Join-Path $RepoRoot 'data\reports\m1\privacy\privacy_a_boundary_sample_30.json'
$Output = Join-Path $RepoRoot 'data\reports\m1\privacy\privacy_a_boundary_review.json'

foreach ($path in @($Python, $Reviewer, $Dataset, $Sample)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required file not found: $path"
    }
}

Set-Location -LiteralPath $RepoRoot
& $Python $Reviewer `
    --dataset $Dataset `
    --sample $Sample `
    --output $Output `
    --reviewer A

if ($LASTEXITCODE -ne 0) {
    throw "A privacy review exited with code $LASTEXITCODE"
}

Write-Host ''
Read-Host '复核窗口已结束，按 Enter 关闭'
