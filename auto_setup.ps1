# AI Vlog Maker V4 - Windows self setup and packaging
# Execute only after inspecting this script and trusting its sources.
param([switch]$SkipOllama, [switch]$SkipModel)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location $PSScriptRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
function Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function FindPython {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += 'py' }
    if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += 'python' }
    foreach ($root in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python312", "$env:ProgramFiles\Python313")) {
        if (Test-Path $root) { $candidates += @(Get-ChildItem $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName) }
    }
    foreach ($candidate in $candidates) {
        try {
            if ($candidate -eq 'py') { $out = & py -3 -c 'import sys; print(sys.executable)' 2>$null; if ($LASTEXITCODE -eq 0 -and $out) { return ($out | Select-Object -First 1) } }
            else { & $candidate -c 'import sys; assert sys.version_info >= (3,10)' 2>$null; if ($LASTEXITCODE -eq 0) { return $candidate } }
        } catch {}
    }
    return $null
}
function FindOllama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $path = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $path) { return $path }
    return $null
}
function InstallWinget($id) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "找不到 winget。請手動安裝 $id（參考 man.txt）後重新執行。" }
    & winget install --id $id --exact --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE -ne 0) { throw "winget 安裝 $id 失敗，代碼 $LASTEXITCODE。請參考 man.txt。" }
}
try {
    Step '檢查 Python 3.10+'
    $python = FindPython
    if (-not $python) {
        Step '安裝 Python 3.12（官方 winget 套件）'
        InstallWinget 'Python.Python.3.12'
        $python = FindPython
    }
    if (-not $python) { throw 'Python 已安裝但目前找不到 python.exe。請重開終端機後重試。' }
    Write-Host "Python: $python"

    Step '準備 FFmpeg + FFprobe'
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'tools') | Out-Null
    $f1 = Join-Path $PSScriptRoot 'tools\ffmpeg.exe'
    $f2 = Join-Path $PSScriptRoot 'tools\ffprobe.exe'
    if (-not ((Test-Path $f1) -and (Test-Path $f2))) {
        $tempDir = Join-Path $env:TEMP ('vlog_ffmpeg_' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tempDir | Out-Null
        try {
            $zip = Join-Path $tempDir 'ffmpeg.zip'
            Write-Host '下載 FFmpeg essentials（gyan.dev Windows builds）...'
            Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $zip
            Expand-Archive -Path $zip -DestinationPath (Join-Path $tempDir 'extract') -Force
            foreach ($name in @('ffmpeg.exe','ffprobe.exe')) {
                $source = Get-ChildItem (Join-Path $tempDir 'extract') -Recurse -File -Filter $name | Select-Object -First 1
                if (-not $source) { throw "FFmpeg 壓縮檔缺少 $name" }
                Copy-Item $source.FullName (Join-Path $PSScriptRoot "tools\$name") -Force
            }
        } finally { Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
    }
    & $f1 -version | Select-Object -First 1 | Out-Host
    & $f2 -version | Select-Object -First 1 | Out-Host

    if (-not $SkipOllama) {
        Step '檢查 Ollama'
        $ollama = FindOllama
        if (-not $ollama) { InstallWinget 'Ollama.Ollama'; $ollama = FindOllama }
        if (-not $ollama) { throw 'Ollama 已安裝但尚未找到 ollama.exe。請重新登入 Windows 或參考 man.txt。' }
        Write-Host "Ollama: $ollama"
        if (-not $SkipModel) {
            Step '準備 AI 模型 gemma3:12b（首次需下載數 GB）'
            try { & $ollama list *> $null } catch {}
            if ($LASTEXITCODE -ne 0) {
                $ollamaApp = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\Ollama app.exe'
                if (Test-Path $ollamaApp) { Start-Process $ollamaApp | Out-Null }
                else { Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Minimized | Out-Null }
                Start-Sleep -Seconds 8
            }
            & $ollama pull 'gemma3:4b'
            if ($LASTEXITCODE -ne 0) { throw 'Gemma 4B 下載失敗。' }
            & $ollama pull 'gemma3:12b'
            if ($LASTEXITCODE -ne 0) { throw '模型下載失敗；請確認 Ollama 已啟動與網路連線。' }
        }
    }

    Step '準備內建 VLC 播放器'
    $vlcDll1 = Join-Path $env:ProgramFiles 'VideoLAN\VLC\libvlc.dll'
    $vlcDll2 = Join-Path ${env:ProgramFiles(x86)} 'VideoLAN\VLC\libvlc.dll'
    if (-not ((Test-Path $vlcDll1) -or (Test-Path $vlcDll2))) {
        InstallWinget 'VideoLAN.VLC'
    }
    Step '安裝 PyInstaller / python-vlc'

    & $python -m pip install --upgrade pyinstaller python-vlc
    if ($LASTEXITCODE -ne 0) { throw 'pip / PyInstaller 安裝失敗。' }
    Step '打包 Windows EXE'
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --hidden-import vlc --hidden-import video_preview --hidden-import cinematic_editor --name AI_Vlog_Maker app.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失敗。' }
    $dest = Join-Path $PSScriptRoot 'dist\AI_Vlog_Maker'
    if (-not (Test-Path (Join-Path $dest 'AI_Vlog_Maker.exe'))) { throw '找不到打包後的 EXE。' }
    New-Item -ItemType Directory -Force -Path (Join-Path $dest 'tools') | Out-Null
    Copy-Item $f1 (Join-Path $dest 'tools\ffmpeg.exe') -Force
    Copy-Item $f2 (Join-Path $dest 'tools\ffprobe.exe') -Force
    Copy-Item (Join-Path $PSScriptRoot 'man.txt') (Join-Path $dest 'man.txt') -Force
    Step '打包成功！'
    Write-Host "EXE: $dest\AI_Vlog_Maker.exe" -ForegroundColor Green
    Write-Host '要搬到別台電腦，請複製整個 dist\AI_Vlog_Maker 資料夾。新電腦仍需要 Ollama 與模型。'
} catch {
    Write-Host "`n安裝／打包未完成：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host '請查看 man.txt 的故障排除；已下載的程式或資料不會自動解除安裝。'
    exit 1
}
