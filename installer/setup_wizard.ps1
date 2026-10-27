# AI Vlog Maker V1.6 five-step Windows installer wizard.
# This installer is portable: no writes to registry, PATH or desktop shortcuts.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
. (Join-Path $PSScriptRoot 'installer_core.ps1')
$script:PackageRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script:Step=0
$script:Completed=$false
$script:Installing=$false
$script:DefaultInstall=Join-Path $env:USERPROFILE 'AI_Vlog_Maker'

$form=New-Object System.Windows.Forms.Form
$form.Text='AI Vlog Maker · Windows 安裝精靈 (V1.6)'
$form.Width=840;$form.Height=640;$form.MinimumSize=New-Object System.Drawing.Size(730,550)
$form.StartPosition='CenterScreen';$form.BackColor=[Drawing.Color]::FromArgb(18,25,36)
$form.ForeColor=[Drawing.Color]::FromArgb(231,236,244)
$form.Font=New-Object Drawing.Font('Microsoft JhengHei',10)
function Make-Label([string]$text,[int]$x,[int]$y,[int]$w,[int]$h,[int]$fontSize=10,[bool]$bold=$false) {
    $c=New-Object System.Windows.Forms.Label
    $c.Text=$text;$c.Location=New-Object Drawing.Point($x,$y);$c.Size=New-Object Drawing.Size($w,$h)
    $c.ForeColor=[Drawing.Color]::FromArgb(221,232,243)
    $style=if ($bold) {[Drawing.FontStyle]::Bold} else {[Drawing.FontStyle]::Regular}
    $c.Font=New-Object Drawing.Font('Microsoft JhengHei',$fontSize,$style)
    return $c
}
function Make-Panel([int]$top) {
    $c=New-Object System.Windows.Forms.Panel
    $c.Location=New-Object Drawing.Point(30,$top);$c.Size=New-Object Drawing.Size(760,430)
    $c.Anchor='Top,Bottom,Left,Right';return $c
}
function Make-TextArea([int]$x,[int]$y,[int]$w,[int]$h) {
    $c=New-Object System.Windows.Forms.TextBox
    $c.Multiline=$true;$c.ReadOnly=$true;$c.ScrollBars='Vertical'
    $c.BackColor=[Drawing.Color]::FromArgb(29,41,58);$c.ForeColor=[Drawing.Color]::FromArgb(219,235,245)
    $c.BorderStyle='FixedSingle';$c.Font=New-Object Drawing.Font('Consolas',9)
    $c.Location=New-Object Drawing.Point($x,$y);$c.Size=New-Object Drawing.Size($w,$h)
    $c.Anchor='Top,Bottom,Left,Right';return $c
}
$title=Make-Label 'AI Vlog Maker · 安裝精靈' 30 20 740 38 19 $true
$form.Controls.Add($title)
$subtitle=Make-Label '獨立安裝、缺什麼才下載、不修改系統 PATH' 32 65 740 22 10
$subtitle.ForeColor=[Drawing.Color]::FromArgb(139,159,178);$form.Controls.Add($subtitle)
$steps=Make-Label '' 33 102 740 30 12 $true;$form.Controls.Add($steps)
$line=New-Object System.Windows.Forms.Panel
$line.Location=New-Object Drawing.Point(30,137);$line.Size=New-Object Drawing.Size(760,2)
$line.BackColor=[Drawing.Color]::FromArgb(54,75,96);$line.Anchor='Top,Left,Right';$form.Controls.Add($line)

$pages=@()
for($i=0;$i -lt 5;$i++){ $pg=Make-Panel 150;$form.Controls.Add($pg);$pages+= $pg }
$pages[0].Controls.Add((Make-Label '1. 檢查目前環境' 0 6 700 31 15 $true))
$pages[0].Controls.Add((Make-Label '掃描現有安裝與安裝包內容，不下載任何東西。' 0 44 710 24))
$reportBox=Make-TextArea 0 82 750 290;$pages[0].Controls.Add($reportBox)

$pages[1].Controls.Add((Make-Label '2. 安裝項目清單' 0 6 700 31 15 $true))
$pages[1].Controls.Add((Make-Label '只有缺少的元件才會下載；你既有的程式與模型不會被移除。' 0 44 710 24))
$componentsBox=Make-TextArea 0 86 750 290;$pages[1].Controls.Add($componentsBox)

$pages[2].Controls.Add((Make-Label '3. 選擇安裝位置' 0 6 700 31 15 $true))
$pages[2].Controls.Add((Make-Label '程式、私有 Ollama 模型、快取與工作區均放在此資料夾下。' 0 50 710 27))
$pathBox=New-Object System.Windows.Forms.TextBox
$pathBox.Text=$script:DefaultInstall;$pathBox.Size=New-Object Drawing.Size(606,29);$pathBox.Location=New-Object Drawing.Point(2,95)
$pathBox.BackColor=[Drawing.Color]::FromArgb(29,41,58);$pathBox.ForeColor=[Drawing.Color]::White
$pages[2].Controls.Add($pathBox)
$browse=New-Object System.Windows.Forms.Button;$browse.Text='瀏覽…';$browse.Location=New-Object Drawing.Point(619,92)
$browse.Size=New-Object Drawing.Size(105,34);$pages[2].Controls.Add($browse)
$browse.Add_Click({
    $dlg=New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description='選擇 AI Vlog Maker 安裝資料夾'
    $dlg.SelectedPath=if(Test-Path $pathBox.Text){$pathBox.Text}else{$env:USERPROFILE}
    if($dlg.ShowDialog() -eq 'OK'){$pathBox.Text=Join-Path $dlg.SelectedPath 'AI_Vlog_Maker'}
})
$privacy=Make-Label '不寫入系統登錄、PATH 或桌面捷徑。Windows 本身可能使用系統暫存、記錄和快取，因此不能保證作業系統零外部寫入。' 0 146 720 100 10
$privacy.ForeColor=[Drawing.Color]::FromArgb(162,189,202);$pages[2].Controls.Add($privacy)

$pages[3].Controls.Add((Make-Label '4. 選擇 Ollama 模型' 0 6 700 31 15 $true))
$pages[3].Controls.Add((Make-Label '可複選。模型以現有服務優先；缺少模型時下載到你選擇的資料夾。' 0 45 700 50))
$model4=New-Object System.Windows.Forms.CheckBox;$model4.Text='Gemma 3 4B（快速初選，約 3 GB）';$model4.Checked=$true
$model4.Location=New-Object Drawing.Point(8,108);$model4.Size=New-Object Drawing.Size(690,37);$pages[3].Controls.Add($model4)
$model12=New-Object System.Windows.Forms.CheckBox;$model12.Text='Gemma 3 12B（高品質複審，約 8 GB）';$model12.Checked=$true
$model12.Location=New-Object Drawing.Point(8,151);$model12.Size=New-Object Drawing.Size(690,37);$pages[3].Controls.Add($model12)
$modelInfo=Make-Label '兩個模型都勾選，才有完整的「4B 初選 + 12B 複審」流程。CPU 電腦可以執行，但 12B 會比較慢。' 8 213 710 100
$pages[3].Controls.Add($modelInfo)

$pages[4].Controls.Add((Make-Label '5. 安裝與最終功能檢查' 0 6 700 31 15 $true))
$pages[4].Controls.Add((Make-Label '開始後會下載缺少的套件、安裝至指定路徑，再逐一測試功能。' 0 45 700 34))
$bar=New-Object System.Windows.Forms.ProgressBar
$bar.Location=New-Object Drawing.Point(0,85);$bar.Size=New-Object Drawing.Size(745,19)
$bar.Minimum=0;$bar.Maximum=100;$pages[4].Controls.Add($bar)
$logBox=Make-TextArea 0 114 750 260;$pages[4].Controls.Add($logBox)

$btnBack=New-Object System.Windows.Forms.Button;$btnBack.Text='上一步';$btnBack.Size=New-Object Drawing.Size(100,38)
$btnBack.Location=New-Object Drawing.Point(480,540);$btnBack.Anchor='Right,Bottom';$form.Controls.Add($btnBack)
$btnNext=New-Object System.Windows.Forms.Button;$btnNext.Text='下一步';$btnNext.Size=New-Object Drawing.Size(120,38)
$btnNext.Location=New-Object Drawing.Point(590,540);$btnNext.Anchor='Right,Bottom';$form.Controls.Add($btnNext)
$btnClose=New-Object System.Windows.Forms.Button;$btnClose.Text='取消';$btnClose.Size=New-Object Drawing.Size(85,38)
$btnClose.Location=New-Object Drawing.Point(717,540);$btnClose.Anchor='Right,Bottom';$form.Controls.Add($btnClose)
# Keep buttons visible at the bottom of the resized form.
$form.Add_Resize({
    $y=$form.ClientSize.Height-60;$btnBack.Top=$y;$btnNext.Top=$y;$btnClose.Top=$y
    $btnClose.Left=$form.ClientSize.Width-105;$btnNext.Left=$btnClose.Left-130;$btnBack.Left=$btnNext.Left-110
    foreach($pg in $pages){$pg.Height=$y-165;$pg.Width=$form.ClientSize.Width-60}
    foreach($c in @($reportBox,$componentsBox,$logBox)){$c.Width=$form.ClientSize.Width-85;$c.Height=[Math]::Max(110,$pages[0].Height-$c.Top-10)}
})
function Refresh-Report {
    $r=Get-PrerequisiteReport $script:PackageRoot $pathBox.Text
    $script:LastReport=$r
    $payloadStatus=if($r.PayloadReady){'OK'}else{'缺少可安裝的正式版 EXE / FFmpeg / FFprobe'}
    $reportBox.Text=( @(
        "64 位元 Windows：$($r.IsWindows64Bit)",
        "正式版安裝素材：$payloadStatus",
        "之前已安裝在目標路徑：$($r.InstalledApp)",
        "內含 FFmpeg / FFprobe：$($r.PayloadFFmpeg) / $($r.PayloadFFprobe)",
        "目標路徑內已有 VLC：$($r.InstalledVlc)",
        "系統已有 VLC：$(if($r.SystemVlc){$r.SystemVlc}else{'否'})",
        "目標路徑內已有 Ollama：$($r.InstalledOllama)",
        "系統有 Ollama 執行檔：$(if($r.SystemOllamaExe){$r.SystemOllamaExe}else{'否'})",
        "系統 Ollama 服務：$($r.SystemOllamaOnline)",
        "系統已下載模型：$($r.SystemModels -join ', ')",
        "獨立 Ollama 服務：$($r.LocalOllamaOnline)",
        "獨立 Ollama 模型：$($r.LocalModels -join ', ')"
    ) -join [Environment]::NewLine)
    $componentsBox.Text=( @(
        "AI Vlog Maker：$(if($r.PayloadReady){'由打包素材安裝 / 更新（不下載 Python）'}else{'缺少，請在開發電腦先 Build'})",
        "PySide6 / Python：包含在正式版 EXE，無須另外安裝。",
        "FFmpeg / FFprobe：由安裝包複製，無須另外下載。",
        "VLC：$(if($r.InstalledVlc -or $r.SystemVlc){'重用現有安裝'}else{'將下載官方免安裝 ZIP（約 83 MB）'})",
        "Ollama：$(if($r.SystemOllamaExe -or $r.InstalledOllama){'重用已存在的執行檔'}else{'需要官方獨立 ZIP（約 245 MB）'})",
        "模型：下一步選擇，只有缺少的模型會下載。",
        '',
        '注意：若現有系統 Ollama 缺少所選模型，為了遵守安裝位置限制，',
        '將在 11435 啟動隔離的 Ollama 實例，模型放在安裝資料夾內。'
    ) -join [Environment]::NewLine)
}
function Show-Step([int]$step) {
    $script:Step=$step
    for($i=0;$i -lt 5;$i++){$pages[$i].Visible=($i -eq $step)}
    $stepNames=@('檢查依賴','列出安裝項目','選擇路徑','選擇 AI 模型','安裝與驗證')
    $steps.Text="步驟 $($step+1) / 5　·　$($stepNames[$step])"
    $btnBack.Enabled=($step -gt 0 -and -not $script:Installing -and -not $script:Completed)
    $btnNext.Text=if($step -lt 4){'下一步'}elseif($script:Completed){'完成'}else{'開始安裝'}
    $btnClose.Enabled= -not $script:Installing
    if($step -eq 0 -or $step -eq 1){ Refresh-Report }
}
$script:OnLog={param($s)
    $logBox.AppendText("[$((Get-Date).ToString('HH:mm:ss'))] $s`r`n")
    [System.Windows.Forms.Application]::DoEvents()
}
$script:OnProgress={param($n)
    $bar.Value=[Math]::Min(100,[Math]::Max(0,$n))
    [System.Windows.Forms.Application]::DoEvents()
}
$btnBack.Add_Click({ if($script:Step -gt 0){Show-Step ($script:Step-1)} })
$btnClose.Add_Click({if(-not $script:Installing){$form.Close()}})
$btnNext.Add_Click({
    if($script:Completed){$form.Close();return}
    if($script:Installing){return}
    if($script:Step -eq 0 -and -not $script:LastReport.IsWindows64Bit){
        [System.Windows.Forms.MessageBox]::Show('目前的安裝包需要 Windows 64-bit。','系統不相容') | Out-Null
        return
    }
    if($script:Step -eq 0 -and -not $script:LastReport.PayloadReady){
        [System.Windows.Forms.MessageBox]::Show('安裝包還沒有正式版 EXE / FFmpeg。請先在開發電腦執行 build_windows.bat，再使用 dist\AI_Vlog_Maker_Setup 進行安裝。','缺少建置成果') | Out-Null
        return
    }
    if($script:Step -eq 2){
        try { $pathBox.Text=Assert-PathWritable $pathBox.Text } catch {
            [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'無法使用安裝路徑') | Out-Null;return
        }
    }
    if($script:Step -eq 3 -and -not ($model4.Checked -or $model12.Checked)){
        [System.Windows.Forms.MessageBox]::Show('請至少選擇一個模型。','尚未選擇模型') | Out-Null;return
    }
    if($script:Step -lt 4){ Show-Step ($script:Step+1);return }
    $chosen=@()
    if($model4.Checked){$chosen+='gemma3:4b'}
    if($model12.Checked){$chosen+='gemma3:12b'}
    $script:Installing=$true
    $btnNext.Enabled=$false;$btnBack.Enabled=$false;$btnClose.Enabled=$false
    try {
        Install-AIVlog $script:PackageRoot $pathBox.Text $chosen
        $script:Completed=$true
        [System.Windows.Forms.MessageBox]::Show("安裝與自動功能檢查通過。`n`n啟動：$($pathBox.Text)\Start_AI_Vlog_Maker.bat`n`n提醒：仍建議實際匯入一支影片測試剪輯輸出。",'安裝成功') | Out-Null
    } catch {
        Write-InstallLog ('ERROR: '+$_.Exception.Message)
        [System.Windows.Forms.MessageBox]::Show("安裝未完成：`n$($_.Exception.Message)`n`n已下載檔案保留在所選資料夾，可重新執行繼續安裝。",'安裝或驗證失敗') | Out-Null
    } finally {
        $script:Installing=$false;$btnNext.Enabled=$true;$btnClose.Enabled=$true
        Show-Step 4
    }
})
$form.Add_FormClosing({param($sender,$args)
    if($script:Installing){$args.Cancel=$true}
})
Show-Step 0
$null=$form.ShowDialog()
