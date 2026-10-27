$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$built=Join-Path $root 'dist\AI_Vlog_Maker'
if (-not (Test-Path (Join-Path $built 'AI_Vlog_Maker.exe'))) {throw 'Run build_windows.bat first; compiled EXE is missing.'}
if (-not (Test-Path (Join-Path $built 'tools\ffmpeg.exe'))) {throw 'FFmpeg missing in release output.'}
if (-not (Test-Path (Join-Path $built 'tools\ffprobe.exe'))) {throw 'FFprobe missing in release output.'}
$setup=Join-Path $root 'dist\AI_Vlog_Maker_Setup'
$payload=Join-Path $setup 'payload\App'
New-Item -ItemType Directory -Force -Path $payload | Out-Null
Copy-Item -Path (Join-Path $built '*') -Destination $payload -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $setup 'installer') | Out-Null
Copy-Item (Join-Path $root 'installer\installer_core.ps1') (Join-Path $setup 'installer') -Force
Copy-Item (Join-Path $root 'installer\setup_wizard.ps1') (Join-Path $setup 'installer') -Force
Copy-Item (Join-Path $root 'installer\Setup_AI_Vlog_Maker.bat') (Join-Path $setup 'Setup_AI_Vlog_Maker.bat') -Force
Copy-Item (Join-Path $root 'installer\README_INSTALLER.md') (Join-Path $setup 'README_INSTALLER.md') -Force
$zip=Join-Path $root 'dist\AI_Vlog_Maker_Setup.zip'
if(Test-Path $zip){Remove-Item $zip -Force}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($setup,$zip,[IO.Compression.CompressionLevel]::Optimal,$false)
Write-Host "[OK] Installer kit: $setup" -ForegroundColor Green
Write-Host "[OK] Distributable ZIP: $zip" -ForegroundColor Green
