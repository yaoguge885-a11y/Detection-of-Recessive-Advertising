$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Reviewer = Join-Path $RepoRoot 'data-tooling\annotation\qwen_calibration_review_cli.py'
$InputFile = Join-Path $RepoRoot 'data\run_outputs\m1_calibration_50\human_reasonableness_review_20.json'
$OutputFile = Join-Path $RepoRoot 'data\run_outputs\m1_calibration_50\human_reasonableness_review_20_A.json'

foreach ($path in @($Python, $Reviewer, $InputFile)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required file not found: $path"
    }
}

Set-Location -LiteralPath $RepoRoot
& $Python $Reviewer `
    --input $InputFile `
    --output $OutputFile `
    --reviewer A

if ($LASTEXITCODE -ne 0) {
    throw "A Qwen calibration review exited with code $LASTEXITCODE"
}

Write-Host ''
Read-Host '复核窗口已结束，按 Enter 关闭'
