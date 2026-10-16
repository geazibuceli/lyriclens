param([int]$Port = 8011)
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $appRoot
$candidates = @(
    (Join-Path $repoRoot '.venv311\Scripts\python.exe'),
    (Join-Path $appRoot '.venv\Scripts\python.exe'),
    (Join-Path $repoRoot '.venv\Scripts\python.exe')
)
$runtime = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $runtime) { throw 'Create the Python environment described in README.md first.' }
& $runtime -m uvicorn lyriclens.api:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
