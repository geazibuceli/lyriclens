param(
    [switch]$InstallPrerequisites,
    [switch]$SkipModelDownload,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$frontendRoot = Join-Path $repoRoot 'lyriclens-app\frontend'

function Find-Runtime {
    foreach ($relative in @('.venv311\Scripts\python.exe', 'lyriclens-app\.venv\Scripts\python.exe', '.venv\Scripts\python.exe')) {
        $candidate = Join-Path $repoRoot $relative
        if (Test-Path -LiteralPath $candidate) {
            try {
                $version = & $candidate -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))"
                if ($LASTEXITCODE -eq 0 -and $version -eq '3.11') { return $candidate }
            } catch { continue }
        }
    }
    return $null
}

function Test-PythonLauncher {
    if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) { return $false }
    try {
        & py.exe -3.11 -c 'import sys; sys.exit(0)' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Test-Node {
    if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) { return $false }
    $version = & node.exe --version
    return ($LASTEXITCODE -eq 0 -and [int]$version.TrimStart('v').Split('.')[0] -ge 22 -and (Get-Command npm.cmd -ErrorAction SilentlyContinue))
}

function Require-Success([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed. Review the output above and run setup again." }
}

try {
    Set-Location -LiteralPath $repoRoot
    $runtime = Find-Runtime
    if ($CheckOnly) {
        $dependencies = $false
        $prepared = $false
        if ($runtime) {
            $dependencies = (& $runtime -c "import importlib.util; print(all(importlib.util.find_spec(m) is not None for m in ['fastapi', 'uvicorn', 'faster_whisper', 'imageio_ffmpeg']))") -eq 'True'
            if ($dependencies) {
                $model = & $runtime -m lyriclens.models status | ConvertFrom-Json
                $prepared = [bool]$model.prepared
            }
        }
        $nodeReady = [bool](Test-Node)
        $frontendReady = Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules\vite\bin\vite.js')
        $ready = [bool]($runtime -and $nodeReady -and $dependencies -and $frontendReady -and $prepared)
        [ordered]@{ ready = $ready; python = $runtime; node = $nodeReady; backend_dependencies = $dependencies; frontend_dependencies = $frontendReady; model_prepared = $prepared } | ConvertTo-Json
        if ($ready) { exit 0 } else { exit 1 }
    }

    if ($InstallPrerequisites) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            if ((-not $runtime -and -not (Test-PythonLauncher)) -or -not (Test-Node)) {
                throw 'Install Python 3.11 and Node.js 22+ first. Windows App Installer supplies winget for automatic setup.'
            }
        } else {
            if (-not $runtime -and -not (Test-PythonLauncher)) {
                & winget.exe install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements
                Require-Success 'Python installation'
            }
            if (-not (Test-Node)) {
                & winget.exe install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
                Require-Success 'Node.js installation'
            }
            $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:Path
        }
    }
    if (-not (Test-Node)) { throw 'Node.js 22+ is required. Run .\setup.cmd -InstallPrerequisites, or install Node.js and reopen the terminal.' }
    if (-not $runtime) {
        if (-not (Test-PythonLauncher)) { throw 'Python 3.11 is required. Run .\setup.cmd -InstallPrerequisites, or install Python and reopen the terminal.' }
        if (Test-Path -LiteralPath (Join-Path $repoRoot '.venv311')) {
            throw 'The existing .venv311 is not a working Python 3.11 environment. Rename it before running setup again.'
        }
        & py.exe -3.11 -m venv (Join-Path $repoRoot '.venv311')
        Require-Success 'Python environment creation'
        $runtime = Find-Runtime
        if (-not $runtime) { throw 'The Python 3.11 environment could not be found.' }
    }

    Write-Output 'Installing the local recognition service and bundled FFmpeg...'
    & $runtime -m pip install -e (Join-Path $repoRoot 'lyriclens-app\backend[inference,tools]')
    Require-Success 'Backend dependency installation'
    Write-Output 'Installing the interface...'
    & npm.cmd ci --prefix $frontendRoot
    Require-Success 'Frontend dependency installation'
    if (-not $SkipModelDownload) {
        Write-Output 'Preparing the Small recognition model (about 500 MB on first setup)...'
        & $runtime -m lyriclens.models download
        Require-Success 'Model preparation'
    }
    Write-Output 'Setup complete. Run .\start.cmd and open http://127.0.0.1:5181/.'
    if ($SkipModelDownload) { Write-Output 'Model download was skipped; prepare weights before transcription.' }
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
