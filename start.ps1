param([switch]$Gpu)
$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$frontendRoot = Join-Path $repoRoot 'lyriclens-app\frontend'
$logRoot = Join-Path $repoRoot '.runtime'

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.ConnectAsync('127.0.0.1', $Port)
        return ($pending.Wait(500) -and $client.Connected)
    } catch { return $false } finally { $client.Dispose() }
}

function Test-Backend {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8011/api/health' -TimeoutSec 2
        $schema = Invoke-RestMethod 'http://127.0.0.1:8011/openapi.json' -TimeoutSec 2
        return ($health.worker_alive -and $schema.info.title -eq 'LyricLens')
    } catch { return $false }
}

function Test-Frontend {
    try {
        $response = Invoke-WebRequest 'http://127.0.0.1:5181/' -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -eq 200 -and $response.Content -match '<title>LyricLens')
    } catch { return $false }
}

function Wait-Service($Process, [scriptblock]$Check, [string]$Name, [string]$ErrorLog) {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (& $Check) { return }
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "$Name stopped during startup. Check $ErrorLog"
        }
        Start-Sleep -Milliseconds 300
    }
    throw "$Name was not ready after 30 seconds. Check $ErrorLog"
}

try {
    $backendRunning = Test-Backend
    $frontendRunning = Test-Frontend
    if (-not $backendRunning -and (Test-Port 8011)) { throw 'Port 8011 is occupied by another or unready service. No process was stopped.' }
    if (-not $frontendRunning -and (Test-Port 5181)) { throw 'Port 5181 is occupied by another or unready service. No process was stopped.' }
    $candidates = @(
        (Join-Path $repoRoot '.venv311\Scripts\python.exe'),
        (Join-Path $repoRoot 'lyriclens-app\.venv\Scripts\python.exe'),
        (Join-Path $repoRoot '.venv\Scripts\python.exe')
    )
    $runtime = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $vite = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
    if (-not $backendRunning -and -not $runtime) { throw 'Create the Python environment in the setup guide before starting the app.' }
    if (-not $frontendRunning -and -not (Test-Path -LiteralPath $vite)) { throw 'Frontend dependencies are missing. Run npm.cmd ci in lyriclens-app/frontend first.' }
    $node = if (-not $frontendRunning) { (Get-Command node.exe -ErrorAction Stop).Source } else { $null }
    New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
    if (-not $backendRunning) {
        if ($Gpu) { $env:LYRICLENS_DEVICE = 'cuda'; $env:LYRICLENS_COMPUTE = 'float16' }
        $errorLog = Join-Path $logRoot 'backend-error.log'
        $backendProcess = Start-Process -FilePath $runtime -ArgumentList @('-m','uvicorn','lyriclens.api:app','--host','127.0.0.1','--port','8011','--no-access-log') -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'backend.log') -RedirectStandardError $errorLog -PassThru
        Wait-Service $backendProcess { Test-Backend } 'Backend' $errorLog
        Write-Output "Backend started (PID $($backendProcess.Id))."
    } else { Write-Output 'Backend is already running; reused the existing service.' }
    if (-not $frontendRunning) {
        $errorLog = Join-Path $logRoot 'frontend-error.log'
        $frontendProcess = Start-Process -FilePath $node -ArgumentList @(('"' + $vite + '"'),'--host','127.0.0.1','--port','5181','--strictPort') -WorkingDirectory $frontendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'frontend.log') -RedirectStandardError $errorLog -PassThru
        Wait-Service $frontendProcess { Test-Frontend } 'Frontend' $errorLog
        Write-Output "Frontend started (PID $($frontendProcess.Id))."
    } else { Write-Output 'Frontend is already running; reused the existing service.' }
    $proxy = Invoke-RestMethod 'http://127.0.0.1:5181/api/health' -TimeoutSec 5
    if (-not $proxy.worker_alive) { throw 'Frontend is running but its backend connection is not ready.' }
    Write-Output 'LyricLens is ready: http://127.0.0.1:5181/'
    try {
        $checks = Invoke-RestMethod 'http://127.0.0.1:8011/api/diagnostics' -TimeoutSec 20
        foreach ($check in $checks.checks) {
            if (-not $check.ok) { Write-Output "Setup notice - $($check.name): $($check.detail)" }
        }
        Write-Output "Recognition device: $($checks.device)/$($checks.compute_type). Optional features can need separate setup."
    } catch { Write-Output 'Environment checks unavailable; open Environment checks in the workspace or consult the setup guide.' }
    Write-Output "Local logs: $logRoot"
    Write-Output 'Model preparation is separate; this command does not download weights or install packages.'
    exit 0
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
