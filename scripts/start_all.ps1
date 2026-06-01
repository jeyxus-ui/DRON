# Start virtual drone and backend
$base = "C:\Users\USUARIO\Downloads\back-mavlink"

Write-Host "Starting virtual drone..."
$p1 = Start-Process -PassThru -NoNewWindow -FilePath "python" -ArgumentList "$base\scripts\sim_drone.py"
Start-Sleep -Seconds 2
Write-Host "Virtual drone PID: $($p1.Id)"

Write-Host "Starting backend..."
$env:MAVLINK_DEVICE="tcp:127.0.0.1:14551"
$p2 = Start-Process -PassThru -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level warning" -WorkingDirectory $base
Start-Sleep -Seconds 4
Write-Host "Backend PID: $($p2.Id)"

Write-Host ""
Write-Host "Services running:"
Get-Process -Name "python" -ErrorAction SilentlyContinue | Format-Table Id
Write-Host ""
Write-Host "Health check:"
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing
    Write-Host $r.Content
} catch {
    Write-Host "Backend not ready yet"
}
