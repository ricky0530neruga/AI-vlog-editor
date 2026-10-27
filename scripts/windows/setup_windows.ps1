# Uses installed PySide6 when available; does not create another env unnecessarily.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $root
function Test-Python([string]$exe) {
    try {
        & $exe -c 'import sys; assert (3,10) <= sys.version_info[:2] < (3,16)' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
function Has-Gui([string]$exe) {
    try {
        & $exe -c 'from PySide6.QtWidgets import QApplication; import vlc' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
$candidates = @()
$venv = Join-Path $root '.venv\Scripts\python.exe'
if (Test-Path $venv) {$candidates += $venv}
if (Get-Command py -ErrorAction SilentlyContinue) {$candidates += 'py'}
if (Get-Command python -ErrorAction SilentlyContinue) {$candidates += 'python'}
$valid = @($candidates | Where-Object {Test-Python $_})
if (-not $valid.Count) {Write-Host '[ERROR] Python 3.10-3.15 required.' -ForegroundColor Red;exit 1}
$ready = @($valid | Where-Object {Has-Gui $_})
if ($ready.Count) {
    Write-Host "[OK] Dependencies already installed for $($ready[0]); no download required." -ForegroundColor Green
    Write-Host 'Run start_gui.bat to launch.'
    exit 0
}
$python = $valid[0]
Write-Host "[INFO] Installing only essential GUI dependencies for: $python" -ForegroundColor Cyan
& $python -m pip install -r 'config\requirements-windows.txt'
if ($LASTEXITCODE -ne 0) {Write-Host '[ERROR] pip install failed.' -ForegroundColor Red;exit 1}
if (-not (Has-Gui $python)) {Write-Host '[ERROR] PySide6/VLC dependency check failed.' -ForegroundColor Red;exit 1}
Write-Host '[OK] Python GUI dependencies installed. VLC player, FFmpeg and Ollama are managed separately.' -ForegroundColor Green
exit 0
