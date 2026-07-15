# ADB vs AScript MCP 技术对比文档

> 微信视频号侵权取证平台 — 底层通信与控制技术

---

## 一、概述

平台通过 PC 控制 Android 手机完成微信视频号的自动化取证。控制层由两套完全不同的技术栈组成：

| 技术 | 性质 | 类比 |
|------|------|------|
| **ADB** | Android 系统调试桥 | 操作系统的"命令行遥控器" |
| **AScript MCP** | 手机端 App 自动化框架 | 用户操作的"智能机器人" |

两者协同工作、不可互相替代。以下是深度对比。

---

## 二、ADB（Android Debug Bridge）

### 2.1 本质

ADB 是 Android SDK 自带的命令行工具，由三部分组成：
- **PC 端**：`adb.exe` 客户端
- **手机端**：`adbd` 守护进程（系统级，开机自启）
- **通信**：PC ↔ 手机通过 USB 或 TCP/IP socket 通信

### 2.2 连接方式

```
方式1：USB 数据线
  PC ──USB── 手机 (adb devices 直接识别)
  优点：稳定、低延迟
  缺点：必须插线

方式2：WiFi TCP/IP
  ① USB 连一次 → adb tcpip 5555（开启手机端 TCP 调试端口）
  ② 拔线 → adb connect 192.168.x.x:5555（WiFi 连接）
  ③ 之后纯 WiFi 使用，无需再插线
  优点：无线自由
  缺点：需初次 USB 授权，WiFi 不稳定时断连

方式3：scrcpy 自带的 ADB
  scrcpy 内嵌 adb.exe，项目优先使用 scrcpy 目录下的 adb（版本兼容性保证）
```

项目中 `device_manager.py` 通过 `adb shell ip addr show wlan0` 获取手机 WiFi IP，判定为 `LocalIP` 模式。

### 2.3 能力范围

ADB 执行的是 **Android 系统级命令**，权限等同于手机的 shell 终端：

| 功能 | 命令 | 项目中的用途 |
|------|------|-------------|
| **设备扫描** | `adb devices` | 发现已连接手机（`device_manager.py`） |
| **获取分辨率** | `adb shell wm size` | 坐标自适应缩放基准（`main.py` `get_phone_screen_size_via_adb`） |
| **获取 WiFi IP** | `adb shell ip addr show wlan0` | 获取手机局域网 IP（`device_manager.py`、`main.py`） |
| **获取型号** | `adb shell getprop ro.product.model` | 设备信息展示（`device_manager.py`） |
| **截图（直出）** | `adb exec-out screencap -p` | **首选**截图方式，无中转文件，直接 stdout → 本地文件（`collector.py` `capture_single_via_adb_execout`） |
| **截图（中转）** | `adb shell screencap -p /sdcard/x.png` + `adb pull` | 备选截图方式，先存手机再拉取（`collector.py` `capture_single_via_adb`） |
| **模拟按键** | `adb shell input keyevent 4` | 返回键（`collector.py` `back_from_traffic_info`） |
| **录屏（方式1）** | `scrcpy --record` | **首选**录屏方式，PC 端直接录制，可带音频（`media_capture.py` `capture_with_scrcpy`） |
| **录屏（方式2）** | `adb shell screenrecord` | 备选录屏，手机端录制后传输（`media_capture.py` `capture_with_phone_screenrecord`） |
| **窗口检测** | `adb shell dumpsys window` | 检测微信视频号是否前台（`device_manager.py` `run_pre_checks`） |
| **存储检查** | `adb shell df /sdcard` | 手机存储空间检查（`device_manager.py`） |
| **屏幕状态** | `adb shell dumpsys power` | 屏幕是否点亮（`device_manager.py`） |
| **心跳检测** | `adb shell echo OK` | 设备在线状态监控（`device_manager.py`） |

### 2.4 局限

ADB **做不了**的事情：

| 做不到 | 原因 |
|--------|------|
| 点击屏幕上任意像素位置的按钮 | `adb shell input tap` 可以，但不知道"分享按钮"的准确位置——位置随分辨率、UI 状态变化 |
| 滑动视频列表 | `adb shell input swipe` 可以，但不知道滑动起点/终点 |
| 读写手机剪贴板 | ADB 不提供剪贴板 API |
| 识别 UI 控件 | 没有 UI 树解析能力 |
| 搜索微信内的文本 | 不属于 ADB 能力范围 |
| 读取微信视频号页面内容 | 微信是第三方 App，ADB 无法解析其界面 |

---

## 三、AScript MCP

### 3.1 本质

AScript 是一款 **运行在手机上的 Android 自动化 App**。它提供了一个 MCP（Model Context Protocol）通信桥，让 PC 端的 Python 程序可以：

1. 通过 MCP 协议发送 Python 脚本到手机
2. 手机端 AScript App 执行脚本（调用 Android 无障碍服务 API）
3. 返回执行结果（日志、截图、剪贴板内容、UI 树）

```
PC 端                               手机端
┌─────────────────┐               ┌─────────────────┐
│ python -m        │  MCP (stdio) │ AScript App     │
│ ascript_mcp.local│ ←──────────→ │                 │
│                 │               │ → action.click() │
│ 调用 MCP Tools: │               │ → Clipboard API  │
│ connect_device  │               │ → screen.capture │
│ deploy_and_run  │               │ → node.Selector  │
│ dump_ui_tree    │               │ → OCR 引擎      │
└─────────────────┘               └─────────────────┘
         │                               │
         └──── WiFi TCP/IP ──────────────┘
```

### 3.2 连接方式

```
方式1：LocalIP（WiFi 直连）
  PC → session.call_tool("connect_device", {"ip": "192.168.x.x", "port": 9096})
  手机端 AScript App 监听 9096 端口
  前提：手机已安装并运行 AScript，同一 WiFi 网络
  优点：无线，最常用

方式2：USB ADB
  PC → session.call_tool("connect_device", {"ip": serial, "connection_mode": "ADB"})
  通过 ADB 通道通信
  用于 WiFi IP 不可用时的兜底
```

项目的连接策略（`main.py` `connect_device_auto_v2`）：
1. 先尝试配置的 IP 直连
2. 若失败，通过 ADB 获取当前 WiFi IP 重试
3. 若仍失败，通过 `scan_devices` 扫描局域网
4. 最后尝试 USB ADB 模式

### 3.3 能力范围

AScript 通过手机端的 Python 运行时 + 无障碍服务，拥有 **类人操作能力**：

#### 3.3.1 触控操作（`ascript.android.action`）

| API | 用途 | 项目中的使用 |
|-----|------|-------------|
| `action.click(x, y)` | 点击屏幕坐标 | 点击分享按钮、复制链接按钮、博主资料卡（`collector.py`） |
| `action.swipe(x1, y1, x2, y2)` | 滑动屏幕 | 切换下一条视频（`collector.py`） |
| `action.long_press(x, y)` | 长按 | 长按复制博主名（`collector.py`） |

所有坐标基于 **1080×2400 基准**，通过 `scale_point()` 自适应缩放到实际分辨率。

**固定坐标示例**（`collector.py`）：
```python
# 分享面板中"复制链接"按钮的固定坐标（1080x2400 基准，经 scale_point 缩放）
COPY_LINK_X = 950
COPY_LINK_Y = 1900

# 点击分享面板右上角展开全部分享选项
SHARE_TRAY_SWIPE_START_X = 880
SHARE_TRAY_SWIPE_END_X = 140
SHARE_TRAY_Y = 1910
```

#### 3.3.2 剪贴板操作（`ascript.android.system.Clipboard`）

| API | 用途 |
|-----|------|
| `Clipboard.set(text)` | 设置剪贴板（先写入哨兵值，检测是否复制成功） |
| `Clipboard.get()` | 读取剪贴板（获取复制到的视频链接） |

**复制视频链接流程**（`collector.py` `copy_video_link`）：
```python
# 1. 先写哨兵值
Clipboard.set("__WEIXIN_COPY_PENDING_xxx__")

# 2. 点击"复制链接"按钮
action.click(COPY_LINK_X, COPY_LINK_Y)

# 3. 轮询读取剪贴板（最多5次）
for attempt in range(5):
    raw_link = Clipboard.get()
    if 哨兵值不在其中 and 包含 "weixin.qq.com":
        return raw_link
```

#### 3.3.3 UI 树查询（`ascript.android.node`）

| API | 用途 | 项目中的使用 |
|-----|------|-------------|
| `node.Selector().text("发现").find()` | 按文字查找控件 | 导航至发现页（`main.py`） |
| `node.Selector().text("视频号").find()` | 按文字查找控件 | 进入视频号（`main.py`） |
| `get_ui_tree(session)` | 获取完整 UI 树 JSON | 定位搜索框、确认视频页（`navigator.py`） |

UI 树解析示例（`main.py` `find_text_by_bounds`）：
```python
# 在 UI 树中按坐标区域查找指定文本
views = get_ui_tree()  # 返回层级 JSON
for view in traverse(views):
    if view["bounds"] 在指定区域内 and view["text"]:
        return view["text"]
```

#### 3.3.4 屏幕捕获（`ascript.android.screen`）

| API | 用途 |
|-----|------|
| `screen.capture_cv()` | 获取 OpenCV 格式的屏幕截图（用于实时 OCR 和视觉模型分析） |
| `screen.capture_and_save(path)` | 截图并保存到手机本地 |

**注意**：首次调用 `screen.capture_cv()` 会触发 Android MediaProjection 权限弹窗（"要开始使用 AScript 录屏或投屏吗？"），需用户点击"立即开始"。项目在 `device_manager.py` 的 `_check_ascript_connect` 中提前触发此弹窗，避免任务执行中被阻断。

#### 3.3.5 OCR 引擎（AScript 内置）

AScript App 内嵌 PaddleOCR 引擎，项目通过 `deploy_and_run` 下发 OCR 代码在手机上直接执行：

```python
# 在手机上运行 OCR（无需把图片传回 PC）
from ascript.android import screen, ocr
img = screen.capture_cv()
results = ocr.ocr(img)
```

**优势**：OCR 在手机端本地执行，无需传输大图，延迟低。

#### 3.3.6 豆包视觉模型（替代 PaddleOCR）

对于需要提取结构化字段的场景（博主资料卡、引流标记），项目使用火山引擎 Ark API 的豆包视觉模型：

```python
# collector.py 中
from weixin.core.doubao_vision import extract_profile_info
doubao_profile = extract_profile_info(profile_path)
# 返回 {"name": "XX影视", "account": "sphxxx", "subject_type": "企业", ...}
```

豆包视觉模型的图片仍通过 ADB 截图获取（PNG 文件），传给云端 API 做结构化提取。

### 3.4 通信协议

AScript MCP 使用 **MCP（Model Context Protocol）** 协议：

```
PC 端启动: python -m ascript_mcp.local
    ↓
MCP Server 启动（stdio 模式）
    ↓
提供 Tools: connect_device, deploy_and_run, dump_ui_tree, scan_devices, ...
    ↓
PC 端 FastAPI 通过 ClientSession 调用 Tools
    ↓
Tools 内部通过 WiFi/ADB socket 与手机端 AScript App 通信
    ↓
返回结果（text + image content）
```

**关键方法**：
```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sp = StdioServerParameters(
    command="python", args=["-m", "ascript_mcp.local"],
    env={**os.environ},
)

async with stdio_client(sp) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        
        # 连接设备
        await session.call_tool("connect_device", {
            "ip": "192.168.1.100", "port": 9096, "connection_mode": "LocalIP"
        })
        
        # 在手机端执行代码
        result = await session.call_tool("deploy_and_run", {
            "project_name": "zscqAndroid",
            "code": "from ascript.android import action; action.click(500, 1000)",
            "log_seconds": 5,
        })
        
        # 获取 UI 树
        await session.call_tool("dump_ui_tree", {"mode": 0})
```

---

## 四、对比总结

### 4.1 核心差异

| 维度 | ADB | AScript MCP |
|------|-----|-------------|
| **运行位置** | PC 端 `adb.exe` → 手机端 `adbd` 守护进程 | PC 端 MCP Client → 手机端 AScript App |
| **权限级别** | 系统级（shell 权限） | 应用级（无障碍服务权限） |
| **通信协议** | ADB 私有协议（USB/TCP socket） | MCP 协议（stdio + TCP socket） |
| **操作粒度** | 系统命令（截图、按键、录屏、设备信息） | UI 操作（点击坐标、滑动、剪贴板、UI 树） |
| **知道"按钮在哪"吗** | ❌ 不知道 | ✅ 通过固定坐标 + 分辨率自适应 |
| **能读剪贴板吗** | ❌ 不能 | ✅ 可以 |
| **能解析 UI 树吗** | ❌ 不能（dumpsys 只能看 Activity） | ✅ 可以（node.Selector + dump_ui_tree） |
| **能本地 OCR 吗** | ❌ 不能 | ✅ 内嵌 PaddleOCR |
| **截图方式** | stdout 直出（快，无中转文件） | OpenCV capture_cv()（慢，但可通过 deploy_and_run 执行后续 OCR） |
| **录屏方式** | scrcpy --record（PC 端录制，可带音频） | screenrecord（手机端录制，传 base64） |
| **依赖** | 仅需 ADB（Android SDK 或 scrcpy 自带） | 需安装 AScript App + Python MCP 包 |

### 4.2 项目中的分工

```
取证任务执行时的操作链：

┌──────────────────────────────────────────────┐
│                    ADB                        │
├──────────────────────────────────────────────┤
│  设备发现 & 状态监测                           │
│  前置检查（微信前台、存储、屏幕）               │
│  所有截图（采集速度快，关键路径）               │
│  录屏（scrcpy，可录制音频）                     │
│  模拟系统返回键                               │
│  坐标自适应缩放基准（获取真实分辨率）            │
└──────────────────────────────────────────────┘
         │
         │ 提供截图 + 设备信息
         ▼
┌──────────────────────────────────────────────┐
│                  AScript MCP                  │
├──────────────────────────────────────────────┤
│  点击分享按钮 → 打开分享面板                    │
│  点击"复制链接"→ 收集视频链接                   │
│  读写剪贴板 → 获取/验证链接                     │
│  滑动切换到下一条视频                           │
│  点击博主资料卡 → 获取博主信息                  │
│  OCR 识别（手机端本地）                        │
│  UI 树解析（定位搜索框、视频页确认）            │
│  微信导航（发现→视频号→搜索）                   │
└──────────────────────────────────────────────┘
```

### 4.3 为什么两者都需要

```
场景：要获取视频链接

如果只用 ADB：
  能截图 ✅ → 能看到分享面板
  不能点击 ❌ → 不知道按钮在哪，坐标不固定
  不能读剪贴板 ❌ → 链接复制了也拿不到

如果只用 AScript：
  能点击 ✅ → 可以点分享按钮
  能读剪贴板 ✅ → 可以获取链接
  能截图 ✅ → 但首次截图会弹权限窗，慢
  速度慢 ❌ → 采集大量视频时 AScript 截图比 ADB 慢 2-3 倍

结论：ADB 负责高速采集（截图、录屏），AScript 负责智能操作（点击、滑动、剪贴板、OCR）
```

### 4.4 截图策略的协作

项目使用了**两层截图策略**：

```python
# collector.py 的 capture_single_with_adb_fallback
async def capture_single_with_adb_fallback(session, path, tag):
    # 第一优先：ADB 直出截图
    if capture_single_via_adb_execout(path):
        return True
    
    # 第二优先：ADB server 截图（中转文件）
    if capture_single_via_adb(path, tag):
        return True
    
    # 第三优先：AScript 远程截图（deploy_and_run 在手机端执行并回传）
    # 仅在 ADB 完全不可用时启用
    return False
```

### 4.5 录屏的两种路径

| 方案 | 技术 | 音频 | 速度 | 使用场景 |
|------|------|------|------|----------|
| `capture_with_scrcpy` | ADB + scrcpy | ✅ 可录制 | 快 | **首选**，PC 端直接录制 |
| `capture_with_phone_screenrecord` | AScript + Android screenrecord | ❌ 通常无 | 慢 | 备选，scrcpy 不可用时 |

---

## 五、连接方式详解

### 5.1 ADB 的三种连接模式

```
① USB 数据线（初次必需）
  PC ──USB线── 手机
  adb devices → 显示设备序列号
  优点：稳定可靠，首次设置必须用
  缺点：有线缆束缚

② WiFi TCP/IP（日常使用）
  步骤：
    USB 连一次 → adb tcpip 5555
    查看手机 WiFi IP → adb connect IP:5555
  之后只要在同一 WiFi 下就能用
  项目自动获取 IP：adb shell ip addr show wlan0

③ scrcpy 内嵌 ADB（项目默认）
  scrcpy 自带 adb.exe，版本兼容性最好
  项目配置：SCRCPY_DIR = "C:\\scrcpy-win64-v3.3.3"
  优先使用此目录下的 adb
```

### 5.2 AScript MCP 的连接模式

```
AScript App 安装到手机后，提供两种连接模式：

① LocalIP（推荐默认）
  AScript App 在手机上监听 9096 端口
  PC 通过 WiFi IP:9096 直连
  前提：手机和 PC 在同一 WiFi 下

② USB ADB（备选）
  通过 ADB 通道转发
  connect_device(ip=serial, connection_mode="ADB")
  当 LocalIP 不通时兜底

项目连接策略（connect_device_auto_v2）：
  Step 1: LocalIP 直连（配置的 IP:PORT）
  Step 2: ADB 获取当前 WLAN IP，重试直连（处理 IP 变化）
  Step 3: scan_devices 扫描局域网设备
  Step 4: USB ADB 模式兜底
```

### 5.3 完整连接拓扑

```
┌──────────────────────────────────────────────────┐
│                      PC                          │
│                                                  │
│  ┌──────────┐          ┌──────────────────┐     │
│  │ adb.exe  │          │ ascript_mcp.local│     │
│  │          │          │  (MCP Server)    │     │
│  └────┬─────┘          └────────┬─────────┘     │
│       │                         │                │
│       │ ADB Protocol            │ MCP Protocol   │
│       │ (TCP 5555 / USB)       │ (stdio)         │
└───────┼─────────────────────────┼────────────────┘
        │                         │
   ─────┼─────────────────────────┼────────────
   WiFi │                         │
   ─────┼─────────────────────────┼────────────
        │                         │
┌───────┼─────────────────────────┼────────────────┐
│       ▼                         ▼                │
│  ┌──────────┐          ┌──────────────────┐     │
│  │  adbd    │          │   AScript App    │     │
│  │  (守护)  │          │   (监听 9096)    │     │
│  └──────────┘          └──────────────────┘     │
│                                                  │
│                  Android 手机                    │
└──────────────────────────────────────────────────┘
```

### 5.4 前置检查的 7 项

| 检查项 | 使用的技术 | 说明 |
|--------|-----------|------|
| ① ADB 连接 | `adb shell echo OK` | 基础通信验证 |
| ② 微信视频号前台 | `adb shell dumpsys window` | 检查焦点窗口是否是 `FinderHomeAffinityUI` |
| ③ 存储空间 | `adb shell df /sdcard` | 剩余空间 ≥10% |
| ④ 屏幕点亮 | `adb shell dumpsys power` | 检查 `mWakefulness=Awake` |
| ⑤ scrcpy 可用 | 文件系统检查 | scrcpy.exe 是否存在 |
| ⑥ ffmpeg 可用 | PATH 检查 | 音频提取需要 ffmpeg |
| ⑦ AScript 端口 | TCP `connect()` | 检查 9096 端口是否可达 |

---

## 六、总结

| | ADB | AScript MCP |
|----|-----|------------|
| **一句话** | 能控制手机系统，但不知道屏幕上有什么 | 能理解屏幕内容，但需要 ADB 做底层支撑 |
| **独立性** | 可以独立使用 | 依赖 ADB（截图、连接） |
| **速度** | 快（系统级调用） | 慢（需 app 层解析 + 代码传输） |
| **智能化** | 低（执行死命令） | 高（UI 树、OCR、剪贴板） |
| **连接** | USB 或 WiFi TCP/IP | WiFi（LocalIP）或 ADB 通道 |

**项目中的设计原则**：ADB 做底层、高速的事（截图、录屏、设备管理），AScript 做智能、灵活的事（点击、滑动、剪贴板、OCR）。两者在各取所长、互不替代。
