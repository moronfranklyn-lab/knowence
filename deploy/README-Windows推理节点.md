# Windows 推理节点部署指南（RTX 4060）

> 目标：让 Windows 上的 4060 承担 Qwen 推理，Mac 上的知微 Knowence 平台通过网络调用它。
> 架构：**推理节点（Windows）与平台节点（Mac）分离**，数据全部留在你的局域网内。

## 为什么要分两台机器

| 考虑 | 说明 |
| --- | --- |
| Mac 的瓶颈 | Docker VM 只分配了 8GB 内存，跑 7B 模型很勉强 |
| 4060 的优势 | 独立 8GB 显存 + CUDA，7B-Q4 实测可达 35-45 tok/s |
| 架构合理性 | 推理与平台分离是企业私有化的常见形态，便于独立扩容与升级 |

## 一、确认显卡驱动

在 Windows 上打开 PowerShell，执行：

```powershell
nvidia-smi
```

能看到显卡型号和 `CUDA Version` 即可。**若命令不存在**，先去 NVIDIA 官网装驱动：
<https://www.nvidia.cn/geforce/drivers/>

## 二、逐步执行（推荐：直接敲命令，不用传文件）

> **为什么不用脚本**：Windows 上运行 .ps1 要过执行策略、路径、文件传输三道坎；
> 直接粘贴命令更可靠。若坚持用脚本，见本节末尾。

### 先确认窗口正确

右键开始菜单 → **终端(管理员)** 或 **Windows PowerShell (管理员)**。
标题栏必须是 `PowerShell` 或 `终端`——**若是「命令提示符」则全部命令都会报
"不是内部或外部命令"**。自检：

```powershell
$PSVersionTable.PSVersion      # 能打印版本号即正确；CMD 里会报错
```

### 5 条命令依次执行

```powershell
# 1) 安装 Ollama（失败则手动下载 https://ollama.com/download/OllamaSetup.exe）
winget install Ollama.Ollama

# —— 装完关掉窗口，重新开一个管理员 PowerShell ——

# 2) 关键：让 Ollama 监听所有网卡（默认只听 127.0.0.1，外部永远连不上）
[Environment]::SetEnvironmentVariable("OLLAMA_HOST","0.0.0.0:11434","Machine")

# 3) 防火墙放行 11434
New-NetFirewallRule -DisplayName "Ollama 11434" -Direction Inbound -LocalPort 11434 -Protocol TCP -Action Allow

# 4) 重启 Ollama 并拉取模型（4.7GB，慢则等待）
Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" -WindowStyle Hidden
Start-Sleep 6
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen2.5:7b

# 5) 取本机局域网地址（把这个 IP 给 Mac 侧）
ipconfig | findstr /i "IPv4"
```

### 冒烟测试

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list
curl.exe http://localhost:11434/v1/models
```

### 备选：用脚本一键完成

拷 `windows-inference-node.ps1` 到桌面后：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd $env:USERPROFILE\Desktop
.\windows-inference-node.ps1      # 注意开头的 .\ 不能省
```

脚本依次完成：体检 → 安装 Ollama → **设置 OLLAMA_HOST** → 防火墙放行 →
拉取 Qwen → 冒烟测试 → 打印 Mac 侧地址。

## 三、手工验证（脚本跑完后）

```powershell
# 1. 确认模型在
ollama list

# 2. 确认真实推理可用
curl http://localhost:11434/v1/chat/completions -Method Post -ContentType "application/json" `
  -Body '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"你好"}],"stream":false}'
```

## 四、Mac 侧接线（由 Mac 上的助手完成）

拿到 Windows 的局域网地址（形如 `http://192.168.1.x:11434/v1`）后，Mac 侧需要：

1. 把该地址加入 app 容器的 `SSRF_WHITELIST_EXTRA`（否则会被平台的 SSRF 防护拒绝）
2. 新建一个对话模型记录：`type=KnowledgeQA`、`provider=generic`、`interface_type=openai`、`base_url=http://192.168.1.x:11434/v1`、`name=qwen2.5:7b`
3. 在对话里选用该模型，跑通一次带引用的问答
4. 记录真实的 **tok/s、首 token 延迟、显存占用**——这三个数字是面试弹药

## 五、注意事项

- **两台机器必须在同一网段**（都连着家里同一个路由器）
- Windows 不要休眠：设置 → 系统 → 电源 → 屏幕和睡眠 → 睡眠改为「从不」
- Ollama 默认开机自启；若没起，手动运行开始菜单里的 Ollama
- 模型量化选择：显存紧张用 `qwen2.5:3b`，够用则 `qwen2.5:7b`
- 端口 11434 只在内网开放，**不要**在路由器上做端口映射（那会让模型暴露到公网）

## 六、常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| **"不是内部或外部命令"** | 在 **CMD** 里执行了 PowerShell 命令，或漏了开头的 `.\` | 换成管理员 **PowerShell / 终端**；脚本要写 `.\xxx.ps1` |
| "无法加载文件，因为在此系统上禁止运行脚本" | 执行策略限制 | 先跑 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Mac 连不上，Windows 本机正常 | `OLLAMA_HOST` 未生效 | 确认环境变量已设并**重启 Ollama 进程** |
| 连接超时 | 防火墙未放行 | 检查入站规则 `Ollama 11434` |
| 拉模型极慢 | 官方源在国内较慢 | 可换 ModelScope 下的 GGUF + `ollama create` 导入 |
| 显存不足报错 | 模型过大 | 换 `qwen2.5:3b` 或更小量化 |
