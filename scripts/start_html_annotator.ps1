[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Dataset,

    [Parameter(Mandatory = $true)]
    [string]$DatasetId,

    [string]$BatchId = "batch1",

    [Parameter(Mandatory = $true)]
    [string]$AnnotatorId,

    [Parameter(Mandatory = $true)]
    [string]$MediaRoot,

    [string]$Manifest = "",

    [ValidateSet("exploratory", "approved")]
    [string]$ManifestRole = "exploratory",

    [string]$SuggestionFile = "",

    [string]$OutputRoot = "",

    [string]$Guide = "",

    [string]$Model = "qwen3.5:9b",

    [string]$OllamaUrl = "http://127.0.0.1:11434",

    [ValidateRange(1, 3600)]
    [int]$TimeoutSec = 120,

    [ValidateRange(1, 32768)]
    [int]$NumPredict = 1536,

    [ValidateRange(0, 2000)]
    [int]$CommentLimit = 30,

    [ValidateRange(1, 65535)]
    [int]$Port = 8765,

    [switch]$NoAutoSuggest,

    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Entry = Join-Path $RepoRoot "data-tooling\annotation\html_annotator.py"
if (-not (Test-Path -LiteralPath $Entry)) {
    throw "Workbench entry not found: $Entry"
}

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    $Python = $VenvPython
}
else {
    $Python = "python"
}

# Keep relative paths anchored at the repository root.
Push-Location -LiteralPath $RepoRoot
try {
    $cliArgs = @(
        $Entry,
        "--dataset", $Dataset,
        "--dataset-id", $DatasetId,
        "--batch-id", $BatchId,
        "--annotator-id", $AnnotatorId,
        "--media-root", $MediaRoot,
        "--manifest-role", $ManifestRole,
        "--model", $Model,
        "--ollama-url", $OllamaUrl,
        "--timeout", "$TimeoutSec",
        "--num-predict", "$NumPredict",
        "--comment-limit", "$CommentLimit",
        "--port", "$Port"
    )

    if ($Manifest) { $cliArgs += @("--manifest", $Manifest) }
    if ($SuggestionFile) { $cliArgs += @("--suggestion-file", $SuggestionFile) }
    if ($OutputRoot) { $cliArgs += @("--output-root", $OutputRoot) }
    if ($Guide) { $cliArgs += @("--guide", $Guide) }
    if ($NoAutoSuggest) { $cliArgs += "--no-auto-suggest" }
    if ($CheckOnly) { $cliArgs += "--check-only" }

    Write-Host "Repository: $RepoRoot"
    Write-Host "Python:     $Python"
    if ($CheckOnly) {
        Write-Host "Mode:       validate dataset and manifest only"
    }
    else {
        if ($NoAutoSuggest) {
            Write-Host "Mode:       blind annotation (Ollama suggestions disabled)"
        }
        else {
            Write-Host "Mode:       local Ollama suggestions enabled"
        }
        Write-Host "Open the printed 127.0.0.1 URL including the token parameter."
    }

    & $Python @cliArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
