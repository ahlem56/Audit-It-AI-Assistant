$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $repoRoot "backend"
$python = (Get-Command python).Source
$hostAddress = "0.0.0.0"
$port = "8765"

Write-Host "Starting Windows PowerPoint export service on http://$hostAddress`:$port"
Write-Host "Keep this window open while exporting PPTX/PDF from the Docker app."
Write-Host "Health check: http://127.0.0.1:$port/health"
Write-Host ""

& $python -c "import pythoncom, win32com.client; print('PowerPoint COM dependencies: OK')"

while ($true) {
    & $python -m uvicorn app.export_host_service:app --app-dir $backendPath --host $hostAddress --port $port --lifespan off
    $exitCode = $LASTEXITCODE
    Write-Host ""
    Write-Host "Export service stopped with exit code $exitCode." -ForegroundColor Yellow
    Write-Host "Restarting in 3 seconds. Press Ctrl+C to stop it permanently." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}
