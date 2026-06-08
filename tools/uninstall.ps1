# =============================================================================
# 桌面便签 卸载脚本 (PowerShell)
# 
# 功能：
#   1. 移除开机自启注册表项
#   2. 移除桌面快捷方式
#   3. 移除开始菜单快捷方式
#   4. 可选：删除用户数据（便签、设置、备份）
#   5. 可选：删除程序目录（便携版）
#
# 使用方式：
#   - 手动运行: powershell -ExecutionPolicy Bypass -File uninstall.ps1
#   - MSI 卸载时作为自定义操作调用: powershell -ExecutionPolicy Bypass -File uninstall.ps1 -CleanData -WaitAppExit
# =============================================================================

param(
    [switch]$CleanData,      # 是否删除用户数据
    [switch]$Silent,         # 静默模式（不弹确认框）
    [switch]$WaitAppExit,    # 等待应用退出再清理
    [int]$WaitTimeout = 10   # 等待超时秒数
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "桌面便签 卸载"

# ---- 颜色输出函数 ----
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[ OK ] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# ---- 检查管理员权限 ----
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warning "建议以管理员身份运行以获得完整清理权限。"
    Write-Warning "当前将以当前用户权限继续..."
    Write-Host ""
}

# ---- 确认卸载 ----
if (-not $Silent) {
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "     桌面便签 卸载程序" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""
    
    if ($CleanData) {
        Write-Warning "将删除所有用户数据（便签内容、设置、备份等），此操作不可恢复！"
    } else {
        Write-Info "用户数据将保留（便签内容、设置等不会被删除）。"
        Write-Info "如需彻底清理，请运行: uninstall.ps1 -CleanData"
    }
    Write-Host ""
    
    $confirm = Read-Host "确认卸载？(输入 YES 继续)"
    if ($confirm -ne "YES") {
        Write-Info "卸载已取消。"
        exit 0
    }
}

Write-Info "开始卸载桌面便签..."

# ---- 等待应用退出 ----
if ($WaitAppExit) {
    Write-Info "等待应用退出..."
    $timeout = Get-Date
    while ($true) {
        $process = Get-Process -Name "StickyNote" -ErrorAction SilentlyContinue
        if (-not $process) {
            Write-Success "应用已退出。"
            break
        }
        if (((Get-Date) - $timeout).TotalSeconds -gt $WaitTimeout) {
            Write-Warning "等待超时，强制终止进程..."
            $process | ForEach-Object { 
                try { $_.Kill() } catch { }
            }
            Start-Sleep -Seconds 2
            break
        }
        Start-Sleep -Seconds 1
    }
} else {
    # 尝试结束运行中的进程
    $process = Get-Process -Name "StickyNote" -ErrorAction SilentlyContinue
    if ($process) {
        Write-Info "发现运行中的进程，正在关闭..."
        $process | ForEach-Object { 
            try { $_.CloseMainWindow() } catch { }
        }
        Start-Sleep -Seconds 2
        $process = Get-Process -Name "StickyNote" -ErrorAction SilentlyContinue
        if ($process) {
            Write-Warning "进程未响应，强制终止..."
            $process | ForEach-Object { 
                try { $_.Kill() } catch { }
            }
            Start-Sleep -Seconds 1
        }
        Write-Success "进程已关闭。"
    }
}

# ---- 1. 移除开机自启注册表项 ----
Write-Info "移除开机自启注册表项..."
try {
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    if (Test-Path $runKey) {
        $prop = Get-ItemProperty -Path $runKey -Name "StickyNoteApp" -ErrorAction SilentlyContinue
        if ($prop) {
            Remove-ItemProperty -Path $runKey -Name "StickyNoteApp" -ErrorAction Stop
            Write-Success "开机自启注册表项已移除。"
        } else {
            Write-Info "未找到开机自启注册表项，跳过。"
        }
    }
} catch {
    Write-Warning "移除注册表项失败: $_"
}

# ---- 2. 移除桌面快捷方式 ----
Write-Info "移除桌面快捷方式..."
$desktopPaths = @(
    [Environment]::GetFolderPath("Desktop"),
    [Environment]::GetFolderPath("CommonDesktopDirectory")
)
foreach ($deskPath in $desktopPaths) {
    $shortcutPath = Join-Path $deskPath "桌面便签.lnk"
    if (Test-Path $shortcutPath) {
        Remove-Item -Path $shortcutPath -Force -ErrorAction SilentlyContinue
        Write-Success "已移除桌面快捷方式: $shortcutPath"
    }
}

# ---- 3. 移除开始菜单快捷方式 ----
Write-Info "移除开始菜单快捷方式..."
$startMenuPaths = @(
    [Environment]::GetFolderPath("StartMenu"),
    [Environment]::GetFolderPath("CommonStartMenu")
)
foreach ($smPath in $startMenuPaths) {
    $programsPath = Join-Path $smPath "Programs"
    $shortcutPath = Join-Path $programsPath "桌面便签.lnk"
    if (Test-Path $shortcutPath) {
        Remove-Item -Path $shortcutPath -Force -ErrorAction SilentlyContinue
        Write-Success "已移除开始菜单快捷方式: $shortcutPath"
    }
    # 也检查 StickyNote 文件夹
    $folderPath = Join-Path $programsPath "桌面便签"
    if (Test-Path $folderPath) {
        Remove-Item -Path $folderPath -Recurse -Force -ErrorAction SilentlyContinue
        Write-Success "已移除开始菜单文件夹: $folderPath"
    }
}

# ---- 4. 删除用户数据（如果指定） ----
if ($CleanData) {
    Write-Info "清理用户数据..."
    
    # 获取脚本所在目录（程序所在目录）
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $userDataDir = $scriptDir  # 便携版数据在程序目录
    
    # 检查并删除 notes 目录
    $notesDir = Join-Path $userDataDir "notes"
    if (Test-Path $notesDir) {
        Remove-Item -Path $notesDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Success "已删除便签数据: $notesDir"
    }
    
    # 检查并删除 backups 目录
    $backupsDir = Join-Path $userDataDir "backups"
    if (Test-Path $backupsDir) {
        Remove-Item -Path $backupsDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Success "已删除备份数据: $backupsDir"
    }
    
    # 删除 settings.json
    $settingsFile = Join-Path $userDataDir "settings.json"
    if (Test-Path $settingsFile) {
        Remove-Item -Path $settingsFile -Force -ErrorAction SilentlyContinue
        Write-Success "已删除配置文件: $settingsFile"
    }
    
    # 删除 window_positions.json
    $windowPosFile = Join-Path $userDataDir "window_positions.json"
    if (Test-Path $windowPosFile) {
        Remove-Item -Path $windowPosFile -Force -ErrorAction SilentlyContinue
        Write-Success "已删除窗口位置记录: $windowPosFile"
    }
} else {
    Write-Info "用户数据已保留（使用 -CleanData 参数可彻底清理）。"
}

# ---- 5. 删除程序目录（仅便携版调用时） ----
# 注意：此脚本位于程序目录的 tools/ 下，如果是从程序目录内部调用
# 需要特殊处理：先复制脚本到临时目录再执行
$scriptParentDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# 检查是否在项目根目录（开发环境）还是便携版目录
$isPackaged = (Test-Path (Join-Path $scriptParentDir "StickyNote.exe")) -or `
              (Test-Path (Join-Path $scriptParentDir "python313.dll"))

if (-not $Silent) {
    Write-Host ""
    if ($isPackaged) {
        Write-Warning "检测到此脚本位于程序安装目录内。"
        Write-Info "卸载后需要删除程序目录。"
        
        $deleteProgram = Read-Host "是否删除程序目录 ($scriptParentDir)？(输入 YES 确认)"
        if ($deleteProgram -eq "YES") {
            Write-Info "程序目录将在此窗口关闭后自动删除..."
            # 创建一个调度任务在脚本退出后删除目录
            $tempScript = [System.IO.Path]::GetTempFileName() + ".ps1"
            @"
Start-Sleep -Seconds 3
Remove-Item -Path "$scriptParentDir" -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path "$scriptParentDir") {
    # 如果还在，尝试通过 cmd 延迟删除
    cmd /c "timeout /t 5 /nobreak >nul && rd /s /q `"$scriptParentDir`""
}
Remove-Item -Path "$tempScript" -Force -ErrorAction SilentlyContinue
"@ | Out-File -FilePath $tempScript -Encoding UTF8
            
            Start-Process -FilePath "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tempScript`"" -NoNewWindow
        }
    }
}

# ---- 完成 ----
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Success "桌面便签 卸载完成！"
Write-Host "========================================" -ForegroundColor Green

# 暂停以显示结果
if (-not $Silent) {
    Write-Host ""
    Write-Host "按任意键关闭..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
