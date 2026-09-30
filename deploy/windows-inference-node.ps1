# ============================================================
#  Knowence 推理节点安装脚本（Windows + NVIDIA 4060）
#  作用：装 Ollama → 开放局域网访问 → 拉取 Qwen → 打印连接信息
#  用法：右键「以管理员身份运行 PowerShell」，然后执行本脚本
#        （若提示执行策略限制，先运行：
#          Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass）
# ============================================================

$ErrorActionPreference = 'Stop'
Write-Host "=== Knowence 推理节点安装 ===" -ForegroundColor Cyan

# ---------- 0. 环境体检 ----------
Write-Host "`n[0/5] 环境体检" -ForegroundColor Yellow
try {
    $gpu = nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    Write-Host "  GPU: $gpu" -ForegroundColor Green
} catch {
    Write-Host "  未检测到 nvidia-smi。若显卡驱动未装，请先装 NVIDIA 驱动再继续。" -ForegroundColor Red
}
$os = (Get-CimInstance Win32_OperatingSystem)
$ramGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
Write-Host "  内存: $ramGB GB"

# ---------- 1. 安装 Ollama ----------
Write-Host "`n[1/5] 安装 Ollama" -ForegroundColor Yellow
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaExe) {
    Write-Host "  已安装，跳过下载" -ForegroundColor Green
} else {
    $installer = "$env:TEMP\OllamaSetup.exe"
    if (-not (Test-Path $installer)) {
        Write-Host "  下载安装包（约 700MB，请稍候）..."
        Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $installer -UseBasicParsing
    }
    Write-Host "  静默安装..."
    Start-Process -FilePath $installer -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
    Start-Sleep -Seconds 5
    if (Test-Path $ollamaExe) { Write-Host "  安装完成" -ForegroundColor Green }
    else { Write-Host "  未找到 $ollamaExe，请手动安装后重跑本脚本" -ForegroundColor Red; exit 1 }
}

# ---------- 2. 开放局域网访问（关键步骤）----------
Write-Host "`n[2/5] 开放局域网访问" -ForegroundColor Yellow
# Ollama 默认只监听 127.0.0.1，外部机器连不上，必须改成 0.0.0.0
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "Machine")
Write-Host "  已设置 OLLAMA_HOST=0.0.0.0:11434（需重启 Ollama 生效）"

# 防火墙放行 11434
$rule = Get-NetFirewallRule -DisplayName "Ollama 11434" -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -DisplayName "Ollama 11434" -Direction Inbound -LocalPort 11434 `
        -Protocol TCP -Action Allow -Profile Private | Out-Null
    Write-Host "  已添加防火墙入站规则（仅专用网络）" -ForegroundColor Green
} else {
    Write-Host "  防火墙规则已存在" -ForegroundColor Green
}

# 重启 Ollama 让环境变量生效
Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
Start-Process $ollamaExe -WindowStyle Hidden
Start-Sleep -Seconds 6
Write-Host "  Ollama 已重启"

# ---------- 3. 拉取 Qwen 模型 ----------
Write-Host "`n[3/5] 拉取 Qwen 模型" -ForegroundColor Yellow
Write-Host "  可选：qwen2.5:7b（4.7GB，推荐）/ qwen2.5:3b（2GB，显存紧张时用）"
$model = Read-Host "  请输入要拉取的模型（直接回车 = qwen2.5:7b）"
if ([string]::IsNullOrWhiteSpace($model)) { $model = "qwen2.5:7b" }
Write-Host "  开始拉取 $model ...（首次较慢，取决于网速）"
& $ollamaExe pull $model
Write-Host "  拉取完成" -ForegroundColor Green

# ---------- 4. 冒烟测试 ----------
Write-Host "`n[4/5] 冒烟测试" -ForegroundColor Yellow
$body = @{
    model    = $model
    messages = @(@{ role = 'user'; content = '用一句话说明什么是向量检索。' })
    stream   = $false
} | ConvertTo-Json -Depth 5

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$resp = Invoke-RestMethod -Uri "http://localhost:11434/v1/chat/completions" `
    -Method Post -ContentType "application/json; charset=utf-8" `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
$sw.Stop()
Write-Host "  模型回答: $($resp.choices[0].message.content)" -ForegroundColor Green
Write-Host "  耗时: $([math]::Round($sw.Elapsed.TotalSeconds,1)) 秒"

# ---------- 5. 输出连接信息（Mac 侧要用）----------
Write-Host "`n[5/5] 连接信息 —— 请把下面这行发给 Mac 上的助手" -ForegroundColor Cyan
$ips = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
        Select-Object -ExpandProperty IPAddress)
foreach ($ip in $ips) {
    Write-Host "  推理节点地址: http://${ip}:11434/v1" -ForegroundColor White
}
Write-Host "`n  自检命令（Windows 本机）: curl http://localhost:11434/v1/models"
Write-Host "  完成。保持 Ollama 运行，不要关机或休眠。" -ForegroundColor Green
