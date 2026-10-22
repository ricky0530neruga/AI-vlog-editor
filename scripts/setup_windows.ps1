# Developer setup only. Does not install system applications or download AI models.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$root = (Get-Location).Path
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

function Try-Python($exe, [string[]]$prefix) {
    try {
        & $exe @prefix -c 'import sys; assert (3,10) <= sys.version_info[:2] < (3,16); print(sys.executable)' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

try {
    if (-not (Test-Path $venvPython)) {
        Write-Host 'Creating .venv...' -ForegroundColor Cyan
        if ((Get-Command py -ErrorAction SilentlyContinue) -and (Try-Python 'py' @('-3'))) {
            & py -3 -m venv '.venv'
        } elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Try-Python 'python' @())) {
            & python -m venv '.venv'
        } else {
            throw 'Python 3.10-3.15 not found. Install Python and retry.'
        }
        if ($LASTEXITCODE -ne 0) { throw 'Creating .venv failed.' }
    }
    & $venvPython -c 'import sys; assert (3,10) <= sys.version_info[:2] < (3,16)'
    if ($LASTEXITCODE -ne 0) { throw 'Unsupported .venv Python version.' }
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
    & $venvPython -m pip install -r 'requirements-windows.txt'
    if ($LASTEXITCODE -ne 0) { throw 'Installing Python packages failed.' }
    Write-Host 'Python setup completed. Run check_env.bat before using the editor.' -ForegroundColor Green
    Write-Host 'FFmpeg, VLC, Ollama, and models are managed separately.'
} catch {
    Write-Host "Setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
