$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $appRoot 'frontend')
try { & npm.cmd run dev } finally { Pop-Location }
