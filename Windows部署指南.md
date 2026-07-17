# 嘉剧荟 - Windows 服务器部署指南

## 一、环境概览

| 组件 | 说明 |
|------|------|
| Python | 3.11（conda 环境 `zscq`） |
| 数据库 | MySQL 8.0，端口 3306（可用 `.env` 覆盖），库名 `zscq` |
| scrcpy | 本机常见路径如 `D:\software\scrcpy-win64-v3.3.3\`（自带 ADB；`config` 会自动探测） |
| ffmpeg | 6.x full-build，需加入系统 PATH |
| ascript_mcp | 从开发机复制到 conda 环境 site-packages |
| 前端 | 构建后由 FastAPI 直接托管（无需 nginx） |

---

## 二、安装步骤

### 1. 安装 Miniconda

下载并安装 [Miniconda for Windows](https://docs.conda.io/en/latest/miniconda.html)，安装时勾选"Add to PATH"。

```powershell
# 创建 Python 3.11 环境
conda create -n zscq python=3.11 -y
conda activate zscq
```

### 2. 安装 MySQL 8.0

下载 [MySQL Community Server 8.0](https://dev.mysql.com/downloads/mysql/8.0.html) 安装。

安装时注意：
- 端口设为 **3306**（或与 `.env` 中 `PLATFORM_DATABASE_URL` 一致）
- root 密码设为 **root**（或同步改 `.env`）
- 字符集选 **utf8mb4**

安装完成后，用 MySQL 客户端（如 HeidiSQL、Navicat 或命令行）建库：

```sql
CREATE DATABASE zscq CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. 安装 ffmpeg

下载 [gyan.dev 的 full-build](https://www.gyan.dev/ffmpeg/builds/)，推荐 `ffmpeg-release-full.7z`。

解压到 `C:\ffmpeg\`，然后将 `C:\ffmpeg\bin\` 加入系统 PATH：

1. Win+R → `sysdm.cpl` → 高级 → 环境变量
2. 系统变量 Path → 新建 → `C:\ffmpeg\bin`
3. 确定保存

验证：
```powershell
ffmpeg -version
```

### 4. 安装 scrcpy + ADB

从开发机复制 scrcpy 目录到本机（示例路径 `D:\software\scrcpy-win64-v3.3.3\`，并在 `.env` 中设置 `PLATFORM_SCRCPY_DIR`）。

该目录包含：
- `scrcpy.exe` — 录屏工具
- `adb.exe` — Android 调试桥
- `scrcpy-server` — 推送到手机的服务端
- 相关 DLL

验证：
```powershell
& "$env:PLATFORM_SCRCPY_DIR\adb.exe" version
& "$env:PLATFORM_SCRCPY_DIR\scrcpy.exe" --version
```

### 5. 安装 Python 依赖

```powershell
conda activate zscq
cd <项目目录>\platform\backend

# 国内加速可选清华源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> **注意**：`paddlepaddle` 包约 500MB，安装较慢。如果失败，检查是否安装了 [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)。

### 6. 复制 ascript_mcp 模块

从开发机找到 `ascript_mcp` 目录并复制：

**开发机路径**：
```
C:\Users\<用户名>\AppData\Roaming\Python\Python311\site-packages\ascript_mcp\
```

**复制到服务器**：
```powershell
# 先找到服务器 conda 环境的 site-packages 路径
conda activate zscq
python -c "import site; print(site.getsitepackages()[0])"
# 输出类似: C:\Users\xxx\miniconda3\envs\zscq\Lib\site-packages

# 将 ascript_mcp 目录拷到该路径下
```

验证：
```powershell
conda activate zscq
python -m ascript_mcp.local
# 不报错即成功
```

### 7. 构建前端

```powershell
cd <项目目录>\platform\frontend
npm install
npm run build
```

构建产物在 `platform\frontend\dist\`，FastAPI 启动时会自动托管。

> 如果服务器没有 Node.js，在开发机 build 好，把 `dist` 目录拷过去也行。

### 8. 配置环境变量（可选）

项目所有配置都支持环境变量覆盖，不需要时可以跳过。需要改的常见项：

```powershell
# MySQL 连接串（默认已是 3306；密码按本机实际修改）
$env:PLATFORM_DATABASE_URL = "mysql+aiomysql://root:你的密码@127.0.0.1:3306/zscq"

# 手机 IP（不设则自动扫描 ADB 设备）
$env:PLATFORM_DEVICE_IP = "192.168.1.100"

# 录屏方式
$env:PLATFORM_PREFER_SCRCPY = "1"
```

完整配置项见 `backend/config.py`。

---

## 三、启动服务

```powershell
conda activate zscq
cd <项目目录>\platform\backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

首次启动会自动建表。

浏览器访问 `http://<服务器IP>:8000` 即可打开前端页面。

---

## 四、手机连接

### USB 连接

1. 手机开启**开发者选项** → **USB 调试**
2. USB 线连接服务器
3. 手机上弹出"允许 USB 调试"，勾选"始终允许"，点确定
4. 验证：

```powershell
& "D:\software\scrcpy-win64-v3.3.3\adb.exe" devices
# 应看到设备列表
```

### WiFi 连接（可选）

如果服务器和手机在同一 WiFi：

```powershell
# 先 USB 连接，然后
adb tcpip 5555
adb connect <手机IP>:5555
# 拔掉 USB 线，WiFi 连接继续工作
```

### AScript App

1. 手机安装 **AScript** App
2. 打开 App，MCP 服务端口保持默认 **9096**
3. 授予**悬浮窗权限**和**无障碍权限**

### 前置检查

启动后端后，在前端页面"设备管理"中可以看到设备列表。点击设备可以运行前置检查（ADB 连接、微信视频号是否前台、AScript 端口是否可达等）。

---

## 五、常见问题

### Q1: `paddlepaddle` 安装失败

先安装 [VC++ Redist](https://aka.ms/vs/17/release/vc_redist.x64.exe)，然后重试。

### Q2: scrcpy 录屏报 `file missing or empty`

- 确认手机 USB 调试已授权
- `adb devices` 能看到设备
- 只有一台手机连接时不需要额外配置；多台手机需要在任务中选择设备

### Q3: `python -m ascript_mcp.local` 报 No module

`ascript_mcp` 目录没有放到正确的 `site-packages` 路径。用 `python -c "import site; print(site.getsitepackages()[0])"` 确认路径。

### Q4: 前端页面空白

检查 `platform\frontend\dist\index.html` 是否存在。如果不存在，需要 `npm run build`。

### Q5: 数据库连接失败

- 确认 MySQL 服务已启动（`services.msc` 查看 MySQL80）
- 确认端口是 3306
- 确认 `zscq` 库已创建
- 检查防火墙是否放行 3306 端口
- 确认 `.env` 中账号密码与本机 MySQL 一致

### Q6: 如何后台运行

```powershell
# 方式一：使用 start /b（关闭终端会停）
start /b uvicorn main:app --host 0.0.0.0 --port 8000

# 方式二：使用 nssm 注册为 Windows 服务（推荐）
# 下载 https://nssm.cc/download
nssm install zscq-platform
# Application: C:\Users\xxx\miniconda3\envs\zscq\python.exe
# Arguments: -m uvicorn main:app --host 0.0.0.0 --port 8000
# Start directory: <项目目录>\platform\backend
nssm start zscq-platform
```

---

## 六、文件清单

部署时需要从开发机拷贝到服务器的文件：

| 源路径 | 目标路径 | 说明 |
|--------|----------|------|
| 整个项目 `platform\` | 同结构任意目录 | 后端代码 + 前端源码 |
| scrcpy 目录（如 `D:\software\scrcpy-win64-v3.3.3\`） | 同路径或任意路径 + `.env` 配置 | scrcpy + ADB |
| `site-packages\ascript_mcp\` | conda 环境的 `site-packages\` | AScript MCP 模块 |
| `platform\frontend\dist\` | （构建后自动生成） | 前端静态文件 |
