# AI Vlog Maker V1.6 installer backend. Windows PowerShell 5.1, .NET 4.5+.
# All application-controlled new files are under the selected install directory.
$ErrorActionPreference = 'Stop'
$script:OllamaZipUrl = 'https://github.com/ollama/ollama/releases/download/v0.40.7/ollama-windows-amd64.zip'
$script:OllamaZipSHA = 'e6527768c53e85ec4596495fb0f035ef07f437b4b591ebc3581684699a4668f4'
$script:VlcZipUrl = 'https://download.videolan.org/pub/videolan/vlc/3.0.24/win64/vlc-3.0.24-win64.zip'
$script:VlcZipSHA = 'fcf30850371ad10c9373cc4f0f4501e7dee49e3e9ae9f20c72fb2661a1ca6323'
$script:LocalOllamaUrl = 'http://127.0.0.1:11435'
$script:SystemOllamaUrl = 'http://127.0.0.1:11434'
$script:Models = @('gemma3:4b','gemma3:12b')

function Get-OllamaTags([string]$url) {
    try {
        $tags = Invoke-RestMethod -Uri ($url.TrimEnd('/') + '/api/tags') -TimeoutSec 3 -ErrorAction Stop
        return @($tags.models | ForEach-Object { $_.name })
    } catch { return @() }
}
function Test-OllamaApi([string]$url) {
    try {
        $null = Invoke-RestMethod -Uri ($url.TrimEnd('/') + '/api/tags') -TimeoutSec 3 -ErrorAction Stop
        return $true
    } catch { return $false }
}
function Get-ExistingVlc {
    foreach ($folder in @("$env:ProgramFiles\VideoLAN\VLC")) {
        if ($folder -and (Test-Path (Join-Path $folder 'libvlc.dll'))) { return $folder }
    }
    return ''
}
function Get-ExistingOllama {
    $command = Get-Command ollama.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and (Test-Path $command.Source)) { return $command.Source }
    foreach ($folder in @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe")) {
        if (Test-Path $folder) { return $folder }
    }
    return ''
}
function Get-PrerequisiteReport([string]$packageRoot,[string]$installPath) {
    $payload = Join-Path $packageRoot 'payload\App'
    $exe = Join-Path $payload 'AI_Vlog_Maker.exe'
    $ffmpeg = Join-Path $payload 'tools\ffmpeg.exe'
    $ffprobe = Join-Path $payload 'tools\ffprobe.exe'
    $localVlc = Join-Path $installPath 'Runtime\VLC\libvlc.dll'
    $localOllama = Join-Path $installPath 'Runtime\Ollama\ollama.exe'
    $systemTags = Get-OllamaTags $script:SystemOllamaUrl
    $localTags = Get-OllamaTags $script:LocalOllamaUrl
    return [pscustomobject]@{
        IsWindows64Bit = [Environment]::Is64BitOperatingSystem
        PayloadReady = (Test-Path $exe) -and (Test-Path $ffmpeg) -and (Test-Path $ffprobe)
        PayloadExe = $exe
        PayloadFFmpeg = (Test-Path $ffmpeg)
        PayloadFFprobe = (Test-Path $ffprobe)
        InstalledApp = Test-Path (Join-Path $installPath 'App\AI_Vlog_Maker.exe')
        InstalledVlc = Test-Path $localVlc
        SystemVlc = Get-ExistingVlc
        InstalledOllama = Test-Path $localOllama
        SystemOllamaExe = Get-ExistingOllama
        SystemOllamaOnline = Test-OllamaApi $script:SystemOllamaUrl
        SystemModels = @($systemTags)
        LocalOllamaOnline = Test-OllamaApi $script:LocalOllamaUrl
        LocalModels = @($localTags)
    }
}
function Assert-PathWritable([string]$path) {
    if ([string]::IsNullOrWhiteSpace($path)) { throw '請選擇安裝資料夾。' }
    $full=[IO.Path]::GetFullPath($path)
    if ($full -match '^[A-Za-z]:\\$') { throw '不能直接安裝在磁碟根目錄。' }
    if ($full.StartsWith('\\')) { throw '請選擇本機磁碟資料夾，不支援網路共享資料夾。' }
    $null=New-Item -ItemType Directory -Force -Path $full
    $probe=Join-Path $full ('.write-test-'+[guid]::NewGuid().ToString('N'))
    try { [IO.File]::WriteAllText($probe,'test') } finally { Remove-Item $probe -Force -ErrorAction SilentlyContinue }
    return $full
}
function Write-InstallLog([string]$message) {
    if ($script:OnLog) { & $script:OnLog $message }
}
function Update-InstallProgress([int]$percent) {
    if ($script:OnProgress) { & $script:OnProgress $percent }
}
function Receive-VerifiedZip([string]$url,[string]$sha,[string]$dest) {
    $dir=Split-Path -Parent $dest
    if (-not (Test-Path $dir)) { $null=New-Item -ItemType Directory -Path $dir -Force }
    if (Test-Path $dest) {
        $actual=(Get-FileHash -Path $dest -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -eq $sha.ToLowerInvariant()) { Write-InstallLog "重用下載快取：$(Split-Path $dest -Leaf)";return }
        Remove-Item $dest -Force
    }
    Write-InstallLog "正在下載：$url"
    # Read chunks on the WinForms thread. Avoid PowerShell event handlers on .NET
    # ThreadPool threads (which can lack an active PowerShell runspace).
    [Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $request=[Net.HttpWebRequest]::Create($url)
    $request.Timeout=90000;$request.ReadWriteTimeout=90000
    $request.UserAgent='AI-Vlog-Maker-Installer/1.6'
    $response=$null;$inputStream=$null;$outputStream=$null
    try {
        $response=$request.GetResponse()
        $inputStream=$response.GetResponseStream()
        $outputStream=[IO.File]::Create($dest)
        $bytes=New-Object byte[] 131072
        $total=[long]$response.ContentLength
        $count=[long]0;$lastShown=[long]0
        while (($n=$inputStream.Read($bytes,0,$bytes.Length)) -gt 0) {
            $outputStream.Write($bytes,0,$n)
            $count+=$n
            if($count-$lastShown -ge 8388608) {
                if($total -gt 0) { Write-InstallLog ("下載進度：{0:N0}% ({1:N1} / {2:N1} MB)" -f (($count/$total)*100),($count/1MB),($total/1MB)) }
                else { Write-InstallLog ("已下載：{0:N1} MB" -f ($count/1MB)) }
                $lastShown=$count
            }
            [System.Windows.Forms.Application]::DoEvents()
        }
        $outputStream.Flush()
        $outputStream.Close();$outputStream=$null
        $actual=(Get-FileHash -Path $dest -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $sha.ToLowerInvariant()) { throw 'SHA256 驗證失敗，檔案可能損毀或遭修改。' }
        Write-InstallLog "SHA256 驗證通過：$(Split-Path $dest -Leaf)"
    } catch {
        if($outputStream){$outputStream.Close();$outputStream=$null}
        Remove-Item $dest -Force -ErrorAction SilentlyContinue
        throw
    } finally {
        if($inputStream){$inputStream.Close()}
        if($response){$response.Close()}
        if($outputStream){$outputStream.Close()}
    }
}

function Expand-PortableZip([string]$zip,[string]$target,[string]$sentinel) {
    if (Test-Path (Join-Path $target $sentinel)) { Write-InstallLog "已安裝：$target";return }
    $staging=Join-Path (Split-Path $target -Parent) ('_unpack_'+[guid]::NewGuid().ToString('N'))
    $null=New-Item -ItemType Directory -Path $staging -Force
    try {
        Write-InstallLog "解壓縮：$(Split-Path $zip -Leaf)"
        Expand-Archive -LiteralPath $zip -DestinationPath $staging -Force
        $match=Get-ChildItem -LiteralPath $staging -Filter $sentinel -Recurse -File | Select-Object -First 1
        if (-not $match) { throw "壓縮檔中找不到 $sentinel" }
        if (-not (Test-Path $target)) { $null=New-Item -ItemType Directory -Path $target -Force }
        Copy-Item -Path (Join-Path $match.DirectoryName '*') -Destination $target -Recurse -Force
        if (-not (Test-Path (Join-Path $target $sentinel))) { throw "安裝失敗：$sentinel" }
    } finally { Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue }
}
function Start-LocalOllama([string]$install,[string]$ollamaExe) {
    if (Test-OllamaApi $script:LocalOllamaUrl) { return }
    $models=Join-Path $install 'Runtime\Models'
    $home=Join-Path $install 'Data\OllamaHome'
    $temp=Join-Path $install 'Temp'
    $logs=Join-Path $install 'Logs'
    foreach ($dir in @($models,$home,$temp,$logs)) { $null=New-Item -ItemType Directory -Path $dir -Force }
    $names=@('OLLAMA_MODELS','OLLAMA_HOST','OLLAMA_TMPDIR','HOME','USERPROFILE','TEMP','TMP')
    $old=@{}
    foreach ($name in $names) { $old[$name]=[Environment]::GetEnvironmentVariable($name,'Process') }
    try {
        $env:OLLAMA_MODELS=$models
        $env:OLLAMA_HOST='127.0.0.1:11435'
        $env:OLLAMA_TMPDIR=$temp
        $env:HOME=$home
        $env:USERPROFILE=$home
        $env:TEMP=$temp;$env:TMP=$temp
        Write-InstallLog '啟動獨立 Ollama，連接埠 11435（不修改系統服務）'
        $null=Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $install -PassThru -RedirectStandardOutput (Join-Path $logs 'ollama.stdout.log') -RedirectStandardError (Join-Path $logs 'ollama.stderr.log')
    } finally {
        foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$old[$name],'Process') }
    }
    for ($i=0;$i -lt 70;$i++) {
        if (Test-OllamaApi $script:LocalOllamaUrl) { return }
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 500
    }
    throw 'Ollama 未能啟動，請查看 Logs\ollama.stderr.log（或連接埠 11435 是否被占用）。'
}
function Receive-OllamaModel([string]$ollamaExe,[string]$model,[string]$baseUrl,[string]$install) {
    $tags=Get-OllamaTags $baseUrl
    if ($tags -contains $model) { Write-InstallLog "模型已存在，跳過下載：$model";return }
    Write-InstallLog "下載 AI 模型：$model（可能需要數 GB）"
    $oldHost=$env:OLLAMA_HOST; $oldModels=$env:OLLAMA_MODELS
    $out=Join-Path $install ('Logs\pull-'+$model.Replace(':','-')+'.stdout.log')
    $err=Join-Path $install ('Logs\pull-'+$model.Replace(':','-')+'.stderr.log')
    try {
        $env:OLLAMA_HOST=([Uri]$baseUrl).Authority
        $env:OLLAMA_MODELS=Join-Path $install 'Runtime\Models'
        $process=Start-Process -FilePath $ollamaExe -ArgumentList @('pull',$model) -WindowStyle Hidden -WorkingDirectory $install -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        $lastMessage='';$lastUpdate=(Get-Date).AddSeconds(-15)
        do {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 400
            $process.Refresh()
            if (((Get-Date)-$lastUpdate).TotalSeconds -ge 5 -and (Test-Path $err)) {
                try {
                    $txt=[IO.File]::ReadAllText($err,[Text.Encoding]::UTF8)
                    $parts=@($txt -split "[\r\n]+" | Where-Object { $_.Trim() })
                    if ($parts.Count) {
                        $line=($parts[-1] -replace '[\x00-\x1F]','').Trim()
                        if($line -and $line -ne $lastMessage){
                            Write-InstallLog ("$model - "+$line.Substring(0,[Math]::Min($line.Length,150)))
                            $lastMessage=$line
                        }
                    }
                } catch { } # Log file may be locked briefly by Ollama.
                $lastUpdate=Get-Date
            }
        } while (-not $process.HasExited)
        if ($process.ExitCode -ne 0) { throw "模型下載失敗：$model（Exit $($process.ExitCode)）。請檢查 $err" }
    } finally { $env:OLLAMA_HOST=$oldHost; $env:OLLAMA_MODELS=$oldModels }
    if (-not ((Get-OllamaTags $baseUrl) -contains $model)) { throw "模型驗證失敗：$model" }
}

function Write-InstalledLauncher([string]$install,[string]$vlcPath,[string]$url,[bool]$privateServer) {
    $models=Join-Path $install 'Runtime\Models'
    $batch=@'
@echo off
setlocal
set "VLOG_ROOT=%~dp0"
set "AI_VLOG_PORTABLE=1"
set "AI_VLOG_OLLAMA_URL=__API__"
set "AI_VLOG_REQUIRED_MODELS=__MODELS__"
set "AI_VLOG_DEFAULT_MODEL=__DEFAULT_MODEL__"
set "AI_VLOG_DEFAULT_MODE=__DEFAULT_MODE__"
set "OLLAMA_MODELS=%VLOG_ROOT%Runtime\Models"
set "VLC_DIR=__VLC__"
set "TEMP=%VLOG_ROOT%Temp"
set "TMP=%VLOG_ROOT%Temp"
if not exist "%TEMP%" mkdir "%TEMP%"
__START_SERVER__
start "" "%VLOG_ROOT%App\AI_Vlog_Maker.exe" %*
'@
    $batch=$batch.Replace('__API__',$url).Replace('__VLC__',$vlcPath)
    $batch=$batch.Replace('__MODELS__',($script:ChosenModels -join ','))
    $defaultModel=if ($script:ChosenModels -contains 'gemma3:12b') {'gemma3:12b'} else {'gemma3:4b'}
    $defaultMode=if (($script:ChosenModels -contains 'gemma3:12b') -and ($script:ChosenModels -contains 'gemma3:4b')) {'balanced'} else {'quality'}
    $batch=$batch.Replace('__DEFAULT_MODEL__',$defaultModel).Replace('__DEFAULT_MODE__',$defaultMode)
    if ($privateServer) {
        $batch=$batch.Replace('__START_SERVER__','powershell -NoProfile -ExecutionPolicy Bypass -File "%VLOG_ROOT%Runtime\start_ollama.ps1"' + "`r`n" + 'if errorlevel 1 (echo [ERROR] Ollama could not start. Check Logs. & pause & exit /b 1)')
        $start=@'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$api='http://127.0.0.1:11435/api/tags'
try { $null=Invoke-RestMethod $api -TimeoutSec 2; exit 0 } catch {}
$exeFile=Get-Content -LiteralPath (Join-Path $root 'Runtime\ollama_exe.txt') -Raw -Encoding UTF8
$exeFile=$exeFile.Trim()
if (-not (Test-Path $exeFile)) { exit 2 }
$env:OLLAMA_HOST='127.0.0.1:11435'
$env:OLLAMA_MODELS=Join-Path $root 'Runtime\Models'
$env:OLLAMA_TMPDIR=Join-Path $root 'Temp'
$env:HOME=Join-Path $root 'Data\OllamaHome'
$env:USERPROFILE=$env:HOME
$env:TEMP=Join-Path $root 'Temp';$env:TMP=$env:TEMP
foreach ($dir in @($env:OLLAMA_MODELS,$env:HOME,$env:TEMP,(Join-Path $root 'Logs'))) { $null=New-Item -ItemType Directory -Path $dir -Force }
$null=Start-Process -FilePath $exeFile -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $root -PassThru -RedirectStandardOutput (Join-Path $root 'Logs\ollama.stdout.log') -RedirectStandardError (Join-Path $root 'Logs\ollama.stderr.log')
for($i=0;$i -lt 40;$i++) {
    try { $null=Invoke-RestMethod $api -TimeoutSec 2; exit 0 } catch { Start-Sleep -Milliseconds 500 }
}
exit 3
'@
        [IO.File]::WriteAllText((Join-Path $install 'Runtime\start_ollama.ps1'),$start,(New-Object System.Text.UTF8Encoding($true)))
    } else { $batch=$batch.Replace('__START_SERVER__','rem Reuse existing Ollama service') }
    # cmd.exe on Windows 10/11 handles UTF-8 BOM poorly; these paths are UTF-16 by Windows file system,
    # so write BAT with the system's current ANSI code page. The commands are ASCII-only except paths.
    [IO.File]::WriteAllText((Join-Path $install 'Start_AI_Vlog_Maker.bat'),$batch,[Text.Encoding]::Default)
}
function Invoke-ApplicationSelfTest([string]$install,[string]$url,[string]$vlcPath,[string[]]$models) {
    $exe=Join-Path $install 'App\AI_Vlog_Maker.exe'
    $report=Join-Path $install 'Logs\selftest.json'
    $old=@{}
    foreach ($key in @('AI_VLOG_PORTABLE','AI_VLOG_OLLAMA_URL','AI_VLOG_REQUIRED_MODELS','VLC_DIR','OLLAMA_MODELS','TEMP','TMP')) {
        $old[$key]=[Environment]::GetEnvironmentVariable($key,'Process')
    }
    try {
        $env:AI_VLOG_PORTABLE='1';$env:AI_VLOG_OLLAMA_URL=$url
        $env:AI_VLOG_REQUIRED_MODELS=($models -join ',')
        $env:VLC_DIR=$vlcPath
        $env:OLLAMA_MODELS=Join-Path $install 'Runtime\Models'
        $env:TEMP=Join-Path $install 'Temp';$env:TMP=$env:TEMP
        $p=Start-Process -FilePath $exe -ArgumentList @('--self-test',('"'+$report+'"')) -WorkingDirectory (Join-Path $install 'App') -WindowStyle Hidden -Wait -PassThru
        if ($p.ExitCode -ne 0 -or -not (Test-Path $report)) { throw "程式自我檢測失敗（Exit $($p.ExitCode)）。" }
        $json=Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($check in $json.checks) {
            Write-InstallLog ("[{0}] {1}: {2}" -f $(if ($check.ok) {'OK'} else {'FAIL'}),$check.name,$check.detail)
        }
        if (-not $json.ok) { throw '至少有一個功能檢查未通過，請查看 Logs\selftest.json。' }
    } finally {
        foreach ($key in $old.Keys) { [Environment]::SetEnvironmentVariable($key,$old[$key],'Process') }
    }
}
function Install-AIVlog([string]$packageRoot,[string]$install,[string[]]$models) {
    $install=Assert-PathWritable $install
    $script:ChosenModels=@($models)
    if (-not $models -or $models.Count -eq 0) { throw '至少選擇一個 Ollama 模型。' }
    $status=Get-PrerequisiteReport $packageRoot $install
    if (-not $status.PayloadReady) { throw '安裝媒體缺少已建置的 App/FFmpeg/FFprobe。請先在開發電腦執行 build_windows.bat。' }
    $rootApp=Join-Path $install 'App'
    foreach ($folder in @('Runtime','Runtime\Models','Data','Data\OllamaHome','Workspaces','Cache','Temp','Logs','App')) {
        $null=New-Item -ItemType Directory -Path (Join-Path $install $folder) -Force
    }
    Update-InstallProgress 6
    Write-InstallLog '安裝主程式（保留既有 Data、Workspaces、Models）'
    Copy-Item -Path (Join-Path $packageRoot 'payload\App\*') -Destination $rootApp -Recurse -Force
    Update-InstallProgress 18
    $vlc=Get-ExistingVlc
    $localVlc=Join-Path $install 'Runtime\VLC'
    if (Test-Path (Join-Path $localVlc 'libvlc.dll')) { $vlc=$localVlc }
    if (-not $vlc) {
        $zip=Join-Path $install 'Cache\vlc-3.0.24-win64.zip'
        Receive-VerifiedZip $script:VlcZipUrl $script:VlcZipSHA $zip
        Expand-PortableZip $zip $localVlc 'libvlc.dll'
        $vlc=$localVlc
    } else { Write-InstallLog "重用現有 VLC：$vlc" }
    Update-InstallProgress 35
    # Use existing Ollama service only when *all* requested models are already available.
    $existingTags=Get-OllamaTags $script:SystemOllamaUrl
    $canUseSystem=(Test-OllamaApi $script:SystemOllamaUrl)
    foreach ($model in $models) { if ($existingTags -notcontains $model) { $canUseSystem=$false } }
    $privateServer= -not $canUseSystem
    if ($canUseSystem) {
        Write-InstallLog '系統 Ollama 已含所選模型：不另下載、不修改既有模型資料。'
        $url=$script:SystemOllamaUrl
    } else {
        $url=$script:LocalOllamaUrl
        $ollama=Join-Path $install 'Runtime\Ollama\ollama.exe'
        if (-not (Test-Path $ollama)) {
            $existing=Get-ExistingOllama
            if ($existing) { $ollama=$existing;Write-InstallLog "重用現有 Ollama 執行檔：$ollama" }
            else {
                $zip=Join-Path $install 'Cache\ollama-windows-amd64-v0.40.7.zip'
                Receive-VerifiedZip $script:OllamaZipUrl $script:OllamaZipSHA $zip
                Expand-PortableZip $zip (Join-Path $install 'Runtime\Ollama') 'ollama.exe'
            }
        } else { Write-InstallLog '重用安裝目錄內的 Ollama。' }
        if (-not (Test-Path $ollama)) { throw '找不到 Ollama 執行檔。' }
        [IO.File]::WriteAllText((Join-Path $install 'Runtime\ollama_exe.txt'),$ollama,(New-Object System.Text.UTF8Encoding($true)))
        Start-LocalOllama $install $ollama
        foreach ($model in $models) { Receive-OllamaModel $ollama $model $url $install }
    }
    Update-InstallProgress 85
    Write-InstalledLauncher $install $vlc $url $privateServer
    Write-InstallLog '執行程式自我檢測（Qt、FFmpeg、VLC、Ollama、模型）'
    Invoke-ApplicationSelfTest $install $url $vlc $models
    $receipt=[ordered]@{
        version='1.6-installer-alpha'; installed_at=(Get-Date).ToString('o');path=$install
        ollama_api=$url; models=@($models);vlc_path=$vlc
        private_ollama=$privateServer;app='App\AI_Vlog_Maker.exe'
    }
    $receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $install 'Data\installation.json') -Encoding UTF8
    Write-InstallLog '安裝及自我檢測完成。'
    Update-InstallProgress 100
}
