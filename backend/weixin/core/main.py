"""
Weixin video monitor.

Flow:
1. Assume the user is already on the Weixin video page.
2. Search the target keyword.
3. Switch to the "视频" tab in the search results.
4. Open the first video in the top-left.
5. Collect evidence from the current video page.
6. Open author info by avatar -> three dots -> more info.
7. Return to the video page and swipe to the next video.
"""
import sys
from pathlib import Path

# 注意：此文件已迁移到 platform/backend/weixin/core/，
# 通过 weixin 包导入，不再需要 sys.path hack。

import asyncio
import base64
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
from datetime import datetime

import builtins as _builtins

_emit_callback = None


def _log(*args, **kwargs):
    """同 print 并可选推送到平台前端。"""
    msg = " ".join(str(a) for a in args)
    _builtins.print(msg, **kwargs)
    if _emit_callback and msg:
        # 只转发日志类消息，过滤协议数据
        if msg.startswith(("[", "  [", "[OK]")) and not msg.startswith(
            ("OCR_START", "OCR_END")
        ):
            try:
                _emit_callback(msg)
            except Exception:
                pass


# 替换本模块内所有 print 调用为 _log
print = _log

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding="utf-8")
sys.modules.setdefault("main", sys.modules[__name__])

# ── 从平台配置读取默认值（运行时可由 engine 覆盖）──
try:
    from config import (
        DEFAULT_DEVICE_IP,
        DEFAULT_PHONE_PORT,
        WECHAT_ACTIVITY as _WECHAT_ACTIVITY,
        SCREENSHOTS_DIR as _SCREENSHOT_DIR,
        JSONS_DIR as _JSONS_DIR,
        SCREEN_BASE_WIDTH,
        SCREEN_BASE_HEIGHT,
        DEFAULT_KEYWORD as _DEFAULT_KEYWORD,
        SCRCPY_DIR,
    )
    PHONE_IP = DEFAULT_DEVICE_IP  # 空字符串 = 自动扫描，由 engine 运行时注入具体 IP
    PHONE_PORT = DEFAULT_PHONE_PORT
    WECHAT_ACTIVITY = _WECHAT_ACTIVITY
    SCREENSHOT_DIR = str(_SCREENSHOT_DIR)
    JSONS_DIR = str(_JSONS_DIR)
    BASE_SCREEN_WIDTH = SCREEN_BASE_WIDTH
    BASE_SCREEN_HEIGHT = SCREEN_BASE_HEIGHT
    DEFAULT_KEYWORD = _DEFAULT_KEYWORD
    DEFAULT_SCRCPY_DIR = str(SCRCPY_DIR)
except ImportError:
    PHONE_IP = "172.16.0.214"
    PHONE_PORT = 9096
    WECHAT_ACTIVITY = "com.tencent.mm/.ui.LauncherUI"
    SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
    JSONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jsons")
    BASE_SCREEN_WIDTH = 1080
    BASE_SCREEN_HEIGHT = 2400
    DEFAULT_KEYWORD = "弃子归来震万城"
    DEFAULT_SCRCPY_DIR = os.environ.get("PLATFORM_SCRCPY_DIR", "/usr/bin")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SCREEN_SIZE_CACHE: dict[str, tuple[int, int]] = {}  # key: device_serial, value: (w, h)


def find_adb():
    path = shutil.which("adb")
    if path:
        return path
    # Windows 回退到 .exe，Linux 不带后缀
    import platform as _platform
    name = "adb.exe" if _platform.system() == "Windows" else "adb"
    local = os.path.join(DEFAULT_SCRCPY_DIR, name)
    return local if os.path.exists(local) else "adb"


def get_phone_wlan_ip_via_adb():
    proc = subprocess.run(
        _adb_args() + ["shell", "ip", "addr", "show", "wlan0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        return ""
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", proc.stdout)
    return match.group(1) if match else ""


def get_phone_screen_size_via_adb(force_refresh: bool = False) -> tuple[int, int]:
    global _SCREEN_SIZE_CACHE
    cache_key = _CURRENT_DEVICE_SERIAL or "__default__"
    if cache_key in _SCREEN_SIZE_CACHE and not force_refresh:
        return _SCREEN_SIZE_CACHE[cache_key]

    proc = subprocess.run(
        _adb_args() + ["shell", "wm", "size"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode == 0:
        match = re.search(r"Physical size:\s*(\d+)x(\d+)", proc.stdout)
        if not match:
            match = re.search(r"Override size:\s*(\d+)x(\d+)", proc.stdout)
        if match:
            _SCREEN_SIZE_CACHE[cache_key] = (int(match.group(1)), int(match.group(2)))
            return _SCREEN_SIZE_CACHE[cache_key]

    _SCREEN_SIZE_CACHE[cache_key] = (BASE_SCREEN_WIDTH, BASE_SCREEN_HEIGHT)
    return _SCREEN_SIZE_CACHE[cache_key]


def scale_x(x: int, width: int | None = None) -> int:
    width = width or get_phone_screen_size_via_adb()[0]
    return int(round(x * width / BASE_SCREEN_WIDTH))


def scale_y(y: int, height: int | None = None) -> int:
    height = height or get_phone_screen_size_via_adb()[1]
    return int(round(y * height / BASE_SCREEN_HEIGHT))


def scale_point(x: int, y: int) -> tuple[int, int]:
    width, height = get_phone_screen_size_via_adb()
    return scale_x(x, width), scale_y(y, height)


def scale_rect(left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int]:
    width, height = get_phone_screen_size_via_adb()
    return (
        scale_x(left, width),
        scale_y(top, height),
        scale_x(right, width),
        scale_y(bottom, height),
    )


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def iso_duration_seconds(started_at: str, ended_at: str) -> int:
    return max(
        1,
        int(
            (
                datetime.fromisoformat(ended_at)
                - datetime.fromisoformat(started_at)
            ).total_seconds()
        ),
    )


def env_int(name, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"[配置] 忽略无效 {name}={raw!r}，使用默认值 {default}")
        return default
    return value if value > 0 else default


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


async def run_on_phone(session, code, log_sec=10):
    """Run a short script on the phone and return combined logs/images."""
    r = await session.call_tool(
        "deploy_and_run",
        {"project_name": "zscqAndroid", "code": code, "log_seconds": log_sec},
    )
    out = {"log": "", "images": []}
    for item in r.content:
        if item.type == "text":
            out["log"] += item.text.encode("utf-8", "replace").decode("utf-8") + "\n"
        elif item.type == "image":
            out["images"].append(item.data)
    return out


async def get_ui_tree(session):
    r = await session.call_tool("dump_ui_tree", {"mode": 0})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}


def walk_ui(data, keyword=None, id_sub=None, clickable=None):
    results = []
    views = data.get("data", {}).get("views", []) if isinstance(data, dict) else data

    def walk(nodes):
        for n in nodes:
            match = True
            text = n.get("text", "") or ""
            desc = n.get("desc", "") or ""
            if keyword and keyword not in text and keyword not in desc:
                match = False
            if id_sub and id_sub not in (n.get("id", "") or ""):
                match = False
            if clickable is not None and n.get("clickable") != clickable:
                match = False
            if match:
                results.append(
                    {
                        "x": n.get("center_x", 0),
                        "y": n.get("center_y", 0),
                        "id": n.get("id", ""),
                        "text": text,
                    }
                )
            walk(n.get("childs", []))

    walk(views)
    return results


async def connect_device_auto(session):
    print(f"[连接] 尝试直连 {PHONE_IP}:{PHONE_PORT} ...")
    r = await session.call_tool(
        "connect_device",
        {"ip": PHONE_IP, "port": PHONE_PORT, "connection_mode": "LocalIP"},
    )
    ok = any(
        "失败" not in c.text and "fail" not in c.text.lower()
        for c in r.content
        if c.type == "text"
    )
    if ok:
        print("[连接] 直连成功")
        return True

    adb_ip = get_phone_wlan_ip_via_adb()
    if adb_ip and adb_ip != PHONE_IP:
        print(f"[连接] 尝试 ADB 发现的当前 IP {adb_ip}:{PHONE_PORT} ...")
        r = await session.call_tool(
            "connect_device",
            {"ip": adb_ip, "port": PHONE_PORT, "connection_mode": "LocalIP"},
        )
        ok = any(
            "失败" not in c.text and "fail" not in c.text.lower()
            for c in r.content
            if c.type == "text"
        )
        if ok:
            print(f"[连接] ADB 当前 IP 直连成功: {adb_ip}:{PHONE_PORT}")
            return True

    print("[连接] 直连失败，扫描设备中...")
    r = await session.call_tool("scan_devices", {"port": PHONE_PORT})
    for item in r.content:
        if item.type != "text":
            continue
        for line in item.text.split("\n"):
            m = re.search(r"IP:\s*([\d.]+):(\d+)", line)
            if not m:
                continue
            ip2, port2 = m.group(1), int(m.group(2))
            await session.call_tool(
                "connect_device",
                {"ip": ip2, "port": port2, "connection_mode": "LocalIP"},
            )
            print(f"[连接] 扫描发现设备 {ip2}:{port2}")
            return True
    return False


def _tool_call_succeeded(result) -> bool:
    texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
    merged = "\n".join(texts).lower()
    if not merged.strip():
        return False
    failure_tokens = ("fail", "error", "失败", "错误", "未连接")
    success_tokens = ("connected", "已连接", "success", "成功", "本地端口")
    if any(token in merged for token in failure_tokens):
        return False
    return any(token in merged for token in success_tokens)


async def connect_device_auto_v2(session):
    print(f"[连接] 尝试直连 LocalIP {PHONE_IP}:{PHONE_PORT} ...")
    result = await session.call_tool(
        "connect_device",
        {"ip": PHONE_IP, "port": PHONE_PORT, "connection_mode": "LocalIP"},
    )
    if _tool_call_succeeded(result):
        print("[连接] LocalIP 直连成功")
        return True

    adb_ip = get_phone_wlan_ip_via_adb()
    if adb_ip and adb_ip != PHONE_IP:
        print(f"[连接] 尝试当前 ADB WLAN IP {adb_ip}:{PHONE_PORT} ...")
        result = await session.call_tool(
            "connect_device",
            {"ip": adb_ip, "port": PHONE_PORT, "connection_mode": "LocalIP"},
        )
        if _tool_call_succeeded(result):
            print(f"[连接] 当前 WLAN IP 直连成功: {adb_ip}:{PHONE_PORT}")
            return True

    # LocalIP 不可用时优先走 ADB 反向隧道（部分机型 WiFi 端口通但 MCP 协议不可用）
    adb_targets: list[str] = []
    if _CURRENT_DEVICE_SERIAL:
        adb_targets.append(_CURRENT_DEVICE_SERIAL)
    # USB serial / WiFi adb 地址
    try:
        proc = subprocess.run(
            [*_adb_args(), "devices"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        for line in (proc.stdout or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device" and parts[0] not in adb_targets:
                adb_targets.append(parts[0])
    except Exception as e:
        print(f"[连接] 枚举 ADB 设备失败: {e}")

    for target in adb_targets:
        print(f"[连接] 尝试 ADB 模式连接 {target} ...")
        adb_result = await session.call_tool(
            "connect_device",
            {"ip": target, "connection_mode": "ADB"},
        )
        if _tool_call_succeeded(adb_result):
            print(f"[连接] ADB 连接成功: {target}")
            return True

    print("[连接] LocalIP/ADB 直连失败，开始扫描设备 ...")
    result = await session.call_tool("scan_devices", {"port": PHONE_PORT})
    for item in result.content:
        if getattr(item, "type", "") != "text":
            continue
        for line in item.text.splitlines():
            if "USB(ADB)" in line:
                prefix = line.split("USB(ADB)", 1)[0]
                serial_match = re.search(r":\s*([A-Za-z0-9._:-]+)\s*$", prefix)
                if serial_match:
                    serial = serial_match.group(1)
                    print(f"[连接] 发现 USB ADB 设备，尝试 serial {serial} ...")
                    adb_result = await session.call_tool(
                        "connect_device",
                        {"ip": serial, "connection_mode": "ADB"},
                    )
                    if _tool_call_succeeded(adb_result):
                        print(f"[连接] USB ADB 连接成功: {serial}")
                        return True

            lan_match = re.search(r"IP:\s*([\d.]+):(\d+)", line)
            if not lan_match:
                continue
            ip2, port2 = lan_match.group(1), int(lan_match.group(2))
            print(f"[连接] 尝试扫描到的 LocalIP {ip2}:{port2} ...")
            lan_result = await session.call_tool(
                "connect_device",
                {"ip": ip2, "port": port2, "connection_mode": "LocalIP"},
            )
            if _tool_call_succeeded(lan_result):
                print(f"[连接] 扫描到的 LocalIP 连接成功: {ip2}:{port2}")
                return True
    return False


async def ensure_wechat_home(session):
    await run_on_phone(
        session,
        f"""
import subprocess, time
subprocess.run(['am', 'start', '-n', '{WECHAT_ACTIVITY}'], timeout=5)
time.sleep(2.0)
print("[OK] WECHAT_LAUNCHED")
""",
        log_sec=5,
    )


async def navigate_to_discover(session):
    await run_on_phone(
        session,
        f"""
import time
from ascript.android import action, node
discover = node.Selector().text("发现").find()
if discover:
    discover.click()
else:
    action.click(810, 2730)
time.sleep(1.0)
print("[OK] DISCOVER")
""",
        log_sec=4,
    )


async def navigate_to_video_channel(session):
    await run_on_phone(
        session,
        """
import time
from ascript.android import action, node
vc = node.Selector().text("视频号").find()
if vc:
    vc.click()
else:
    action.click(620, 980)
time.sleep(1.5)
print("[OK] VIDEO_CHANNEL")
""",
        log_sec=4,
    )


# 当前连接的设备 serial，由 engine 层注入（用于多设备场景下指定 ADB 目标）
_CURRENT_DEVICE_SERIAL = os.environ.get("PLATFORM_DEVICE_SERIAL", "")


def _adb_args() -> list[str]:
    """构建 ADB 命令前缀，如果指定了设备则加 -s serial"""
    adb = find_adb()
    if _CURRENT_DEVICE_SERIAL:
        return [adb, "-s", _CURRENT_DEVICE_SERIAL]
    return [adb]


async def go_back(session):
    subprocess.run(
        _adb_args() + ["shell", "input", "keyevent", "4"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    await asyncio.sleep(1.6)
    print("[OK] ADB_BACK")


async def swipe_up(session):
    x1, y1 = scale_point(540, 2000)
    x2, y2 = scale_point(540, 400)
    proc = subprocess.run(
        _adb_args() + ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "300"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        print(f"[滑动] ADB 滑动失败: {proc.stderr.strip()}")
    else:
        print("[滑动] ADB 滑动已发送")
    await asyncio.sleep(1.2)


# ── Intent / 浏览器 → 微信 导航函数 ──


async def go_home(session=None):
    """按 Home 键回到桌面，清空当前应用状态"""
    subprocess.run(
        _adb_args() + ["shell", "input", "keyevent", "KEYCODE_HOME"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    await asyncio.sleep(0.8)
    print("[HOME] 已回到桌面")


async def open_video_via_intent(session, url: str) -> bool:
    """通过 ADB intent 打开视频链接，触发系统浏览器弹出"前往微信"弹窗

    Returns:
        True 表示 intent 发送成功（浏览器已打开）
    """
    proc = subprocess.run(
        _adb_args() + ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    msg = (proc.stdout + proc.stderr).strip()
    # QQ浏览器等已在后台运行时，intent 不会新启 Activity，而是把已有任务切到前台并加载链接，
    # 此时返回 "Activity not started, its current task has been brought to the front" 属于正常成功
    ok = proc.returncode == 0 and "Error" not in msg
    if ok:
        print(f"[INTENT] 已发送: {url[:80]}")
    else:
        print(f"[INTENT] 发送失败: {msg[:200]}")
    return ok


def screenshot_via_adb(path: str) -> bool:
    """通过 ADB screencap + pull 截图（独立于 MCP session，可用于浏览器等场景）

    Returns:
        True 表示截图成功
    """
    import os as _os
    tag = _os.path.splitext(_os.path.basename(path))[0] or "adbshot"
    remote = f"/sdcard/{tag}.png"
    _os.makedirs(_os.path.dirname(path), exist_ok=True)

    adb_prefix = _adb_args()
    shot = subprocess.run(
        adb_prefix + ["shell", "screencap", "-p", remote],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if shot.returncode != 0:
        return False

    pull = subprocess.run(
        adb_prefix + ["pull", remote, path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    subprocess.run(adb_prefix + ["shell", "rm", "-f", remote], check=False)
    return pull.returncode == 0 and _os.path.exists(path)


async def click_goto_weixin_button(session, slug: str = "") -> bool:
    """直接使用固定坐标点击浏览器弹窗中的"前往微信"按钮

    同一手机同一浏览器弹窗位置固定，使用 GOTO_WEIXIN_FALLBACK_X/Y 坐标
    （1080x2400 基准，运行时自动缩放到实际分辨率）

    Returns:
        True 表示已发送点击
    """
    from config import GOTO_WEIXIN_FALLBACK_X, GOTO_WEIXIN_FALLBACK_Y

    tap_x, tap_y = scale_point(GOTO_WEIXIN_FALLBACK_X, GOTO_WEIXIN_FALLBACK_Y)
    subprocess.run(
        _adb_args() + ["shell", "input", "tap", str(tap_x), str(tap_y)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    print(f"[INTENT] 已点击前往微信: ({tap_x},{tap_y})")
    return True


async def ocr_recognize(session, engine="paddle"):
    """OCR the current phone screen."""
    code = f'''
from ascript.android.screen import Ocr
import json
Ocr.set_engine("{engine}")
results = Ocr.ocr()
output = []
for item in results:
    if isinstance(item, dict):
        text = item.get("text", "")
        if "box" in item:
            box = item["box"]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x, y = int(sum(xs)/len(xs)), int(sum(ys)/len(ys))
            w, h = max(xs) - min(xs), max(ys) - min(ys)
        else:
            x = item.get("x", item.get("center_x", 0))
            y = item.get("y", item.get("center_y", 0))
            w = item.get("w", 0)
            h = item.get("h", 0)
    elif isinstance(item, (list, tuple)) and len(item) >= 2:
        box = item[0]
        text_info = item[1]
        text = str(text_info[0] if isinstance(text_info, (list, tuple)) else text_info)
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, y = int(sum(xs)/len(xs)), int(sum(ys)/len(ys))
        w, h = max(xs) - min(xs), max(ys) - min(ys)
    else:
        text = str(item)
        x = y = w = h = 0
    output.append({{"text": text, "x": x, "y": y, "w": w, "h": h}})
print("OCR_START")
print(json.dumps(output, ensure_ascii=False))
print("OCR_END")
'''
    out = await run_on_phone(session, code, log_sec=15)
    log = out["log"]
    s = log.find("OCR_START")
    e = log.find("OCR_END")
    if s >= 0 and e > s:
        return json.loads(log[s + 9 : e].strip())
    return []


async def capture_to_local(session, count=5, interval=0.8, prefix="cap"):
    paths = []
    for i in range(count):
        ts = datetime.now().strftime("%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"{prefix}_{ts}_{i}.png")
        ok = await capture_single(session, path)
        if ok:
            paths.append(path)
        await asyncio.sleep(interval)
    return paths


async def capture_series(session, keyword, blogger_name, screenshot_dir, count=10, interval=1.0):
    safekey = re.sub(r'[\\/:*?"<>|]', "_", keyword)[:20]
    safename = re.sub(r'[\\/:*?"<>|]', "_", blogger_name)[:20]
    ts = datetime.now().strftime("%m%d_%H%M")
    subdir = os.path.join(screenshot_dir, f"{ts}_{safekey}_{safename}")
    os.makedirs(subdir, exist_ok=True)
    paths = []
    for i in range(count):
        path = os.path.join(subdir, f"{i:02d}.png")
        ok = await capture_single(session, path)
        if ok:
            paths.append(path)
        await asyncio.sleep(interval)
    return subdir, paths


def find_visible_by_id(nodes, target_id, min_y=500, max_y=2800):
    results = []

    def walk(nodes_):
        for n in nodes_:
            nid = n.get("id", "") or ""
            cy = n.get("center_y", 0)
            if target_id in nid and min_y < cy < max_y:
                results.append(n)
            walk(n.get("childs", []))

    walk(nodes)
    return results


async def wait_for_search_results(session, keyword, timeout=8):
    for i in range(timeout):
        await asyncio.sleep(1)
        ocr = await ocr_recognize(session)
        texts = "".join(x.get("text", "") for x in ocr)
        if keyword in texts and ("视频号" in texts or "搜索" not in texts):
            print(f"  [校验] 第{i + 1}s 检测到结果页")
            return True
        if any("拼音" in x.get("text", "") or "空格" in x.get("text", "") for x in ocr):
            print(f"  [校验] 第{i + 1}s 仍在输入态")
            continue
        print(f"  [校验] 第{i + 1}s 等待中...")
    print(f"  [校验] × 超时 {timeout}s 未进入结果页")
    return False


async def click_first_video_result(session):
    print("[结果页] 点击左上角第一个视频...")
    await run_on_phone(
        session,
        f"""
import time
from ascript.android import action
# Search results page: click inside the first video card body.
action.click({scale_point(266, 964)[0]}, {scale_point(266, 964)[1]})
time.sleep(1.8)
print("[OK] FIRST_VIDEO_OPENED")
""",
        log_sec=5,
    )
    await asyncio.sleep(2.0)


async def search_keyword(session, keyword):
    """Fixed-coordinate search path with slightly slower pacing for stability."""
    print(f"[搜索] {keyword}")
    escaped = keyword.replace("'", "\\'")
    header_safe_x, header_safe_y = scale_point(540, 100)
    open_search_x, open_search_y = scale_point(885, 180)
    focus_input_x, focus_input_y = scale_point(300, 210)
    clear_input_x, clear_input_y = scale_point(957, 1703)
    submit_x, submit_y = scale_point(950, 215)
    video_tab_x, video_tab_y = scale_point(302, 350)

    await run_on_phone(
        session,
        f"""
import time
from ascript.android import action
action.click({header_safe_x}, {header_safe_y})
time.sleep(0.5)
action.click({open_search_x}, {open_search_y})
time.sleep(1.0)
action.click({focus_input_x}, {focus_input_y})
time.sleep(0.35)
action.input('{escaped}')
time.sleep(0.8)
action.click({submit_x}, {submit_y})
time.sleep(2.0)
action.click({video_tab_x}, {video_tab_y})
time.sleep(1.8)
print("[OK] SEARCH_SUBMITTED")
""",
        log_sec=5,
    )

    await asyncio.sleep(1.5)
    print("[搜索] 已提交；跳过慢速 OCR 结果页校验")
    return True


def is_likely_link(text: str) -> bool:
    """判断文本是否像链接，避免 OCR 把链接当成博主名称。"""
    return bool(re.search(r"https?://|weixin\.qq\.com|chuangkit\.com", text))


async def build_current_video_candidate(session, keyword, index):
    ocr = await ocr_recognize(session)
    items = ocr if isinstance(ocr, list) else ocr.get("items", [])

    title_text = ""
    author_name = ""
    publish_time = ""

    for it in items:
        txt = (it.get("text", "") or "").strip()
        y = it.get("y", 0)
        if not txt:
            continue
        if not title_text and len(txt) >= 6 and 500 <= y <= 2200:
            title_text = txt
        if ("关注" in txt or "+关注" in txt) and not author_name:
            candidate = txt.replace("+关注", "").replace("关注", "").strip()
            if candidate and not is_likely_link(candidate):
                author_name = candidate
        if not publish_time and re.search(r"(刚刚|\d+分钟前|\d+小时前|\d+天前|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", txt):
            publish_time = txt

    # 去掉标题末尾的 #标签
    if title_text:
        title_text = re.sub(r'\s*#\S+', '', title_text).strip()

    if not title_text:
        # OCR 无法读取标题时，用搜索结果页 OCR 文本片段 + 采集时间作为唯一标识
        # 取前两条非空 OCR 文本拼接，确保不同视频有不同指纹
        text_snippets = [
            (it.get("text", "") or "").strip()
            for it in items if (it.get("text", "") or "").strip()
        ][:2]
        if text_snippets:
            title_text = "|".join(text_snippets)
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            title_text = f"{keyword}_{ts}"

    # 指纹：基于标题 + 作者名，OCR 失败时标题已含时间戳，天然唯一
    stable_title = title_text
    if stable_title and re.match(rf"^{re.escape(keyword)}_\d+$", stable_title):
        stable_title = keyword  # 兼容旧格式：{keyword}_{index}
    raw = f"weixin|{keyword}|{author_name}|{stable_title[:60]}"
    fp = hashlib.md5(raw.encode("utf-8")).hexdigest()

    return {
        "keyword": keyword,
        "hit_text": title_text,
        "title_text": title_text,
        "author_name": author_name,
        "publish_time": publish_time,
        "fingerprint": fp,
        "score": 1,
        "click_x": 0,
        "click_y": 0,
        "_index": index,
    }


async def capture_single(session, path):
    code = """
import base64, cv2, time
from ascript.android import screen
for _ in range(3):
    img = screen.capture_cv()
    if img is not None:
        break
    time.sleep(1)
if img is not None:
    _, buf = cv2.imencode('.png', img)
    print(base64.b64encode(buf.tobytes()).decode('utf-8'))
"""
    out = await run_on_phone(session, code, log_sec=8)
    log = out.get("log", "")
    lines = log.splitlines()
    chunks = []
    for ln in lines:
        if len(ln) >= 31 and ln.startswith("["):
            ln = ln[31:]
        chunks.append(ln)
    raw = "".join(chunks)
    hpos = raw.find("iVBORw0KGgo")
    if hpos < 0:
        return False
    raw = raw[hpos:]
    raw = re.sub(r"[^A-Za-z0-9+/]", "", raw)
    while len(raw) % 4 != 0:
        raw += "="
    data = base64.b64decode(raw)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return True


def attach_recording_media(record, video_path: str, started_at: str, ended_at: str):
    from weixin.core.media_capture import extract_audio, probe_audio

    record.media_info["recording_video_path"] = str(video_path)
    record.media_info["recording_started_at"] = started_at
    record.media_info["recording_ended_at"] = ended_at
    record.media_info["recording_duration_seconds"] = iso_duration_seconds(started_at, ended_at)

    has_audio = False
    try:
        has_audio = probe_audio(video_path)
    except Exception as exc:
        print(f"[录屏] 音频检测失败: {exc}")
    record.media_info["has_audio"] = has_audio

    if has_audio:
        try:
            wav_path = extract_audio(video_path)
        except Exception as exc:
            print(f"[录屏] 音频提取失败: {exc}")
        else:
            if wav_path:
                record.media_info["recording_audio_path"] = str(wav_path)
                # --- ASR 延后到全部采集结束后统一触发 ---
                from weixin.core.store import build_video_identifier
                vid = build_video_identifier(record.to_dict())
                record.candidate["video_identifier"] = vid


async def run():
    print("=" * 60)
    print("weixin video monitor main flow")
    print("=" * 60)

    sp = StdioServerParameters(
        command="python", args=["-m", "ascript_mcp.local"],
        env={**os.environ},  # 传递完整环境变量，避免 conda 包找不到
    )
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 已初始化")

            if not await connect_device_auto_v2(session):
                print("[✗] 设备未连接")
                return
            print("[✓] 设备已连接")

            keyword = DEFAULT_KEYWORD
            if not await search_keyword(session, keyword):
                print("[✗] 搜索失败")
                return

            from weixin.core.collector import collect_current_video
            from weixin.core.media_capture import start_capture_session, stop_capture_session
            from weixin.core.store import clear_seen, save_record
            from weixin.core.navigator import wait_for_video_page

            capture_method = os.environ.get("WEIXIN_CAPTURE_METHOD", "auto").strip().lower() or "auto"
            capture_prefer_scrcpy = env_bool("WEIXIN_PREFER_SCRCPY", True)
            hold_seconds = env_int("WEIXIN_POST_EVIDENCE_HOLD_SECONDS", 240)
            max_videos = env_int("WEIXIN_MAX_VIDEOS", 2)
            verify_video_page = env_bool("WEIXIN_VERIFY_VIDEO_PAGE", False)
            write_db = env_bool("WEIXIN_WRITE_DB", False)
            realtime_ocr = env_bool("WEIXIN_REALTIME_OCR", False)
            realtime_traffic_ocr = env_bool("WEIXIN_REALTIME_TRAFFIC_OCR", True)
            print(
                f"[config] max_videos={max_videos}, hold_seconds={hold_seconds}, "
                f"capture_method={capture_method}, prefer_scrcpy={capture_prefer_scrcpy}, "
                f"realtime_ocr={realtime_ocr}, realtime_traffic_ocr={realtime_traffic_ocr}"
            )

            segment = None
            collected_records: list = []
            record_json_paths: dict = {}  # weixin standalone 模式下记录 JS文件路径
            try:
                segment = start_capture_session(
                    method=capture_method,
                    prefer_scrcpy=capture_prefer_scrcpy,
                )
                print(f"[录屏] 第一段录屏已开始: {segment.local_path}")

                await click_first_video_result(session)
                if verify_video_page and not await wait_for_video_page(session, timeout=5):
                    print("[✗] 首个视频页未确认")
                    return

                seen = set()
                duplicate_rounds = 0
                max_duplicate_rounds = int(os.environ.get("PLATFORM_MAX_DUPLICATE_ROUNDS", "3"))

                for index in (range(1, max_videos + 1) if max_videos > 0 else itertools.count(1)):
                    print(f"\n{'=' * 50}\n[视频] 第 {index} 条 {'(全量采集模式)' if max_videos <= 0 else ''}")
                    candidate = await build_current_video_candidate(session, keyword, index)

                    if candidate["fingerprint"] in seen:
                        duplicate_rounds += 1
                        print(
                            f"[视频] 重复指纹 {duplicate_rounds}/{max_duplicate_rounds}: "
                            f"{candidate['fingerprint']}"
                        )
                        if duplicate_rounds >= max_duplicate_rounds:
                            print("[流程] 连续重复过多，停止采集")
                            break
                    else:
                        duplicate_rounds = 0

                    record = await collect_current_video(session, keyword, candidate, seen)

                    print(f"[录屏] 停止前停留 {hold_seconds}s")
                    await asyncio.sleep(hold_seconds)

                    ended_at = now_iso()
                    video_path = stop_capture_session(segment)
                    attach_recording_media(record, str(video_path), segment.started_at, ended_at)
                    print(f"[录屏] 录屏段已保存: {video_path}")
                    segment = None

                    json_path = save_record(record)
                    collected_records.append(record)
                    record_json_paths[len(collected_records) - 1] = json_path
                    if write_db:
                        # platform 独立模式下 WEIXIN_WRITE_DB=0，此分支不会执行
                        # insert_evidence_record 依赖 MySQL（未迁移），由平台 engine 替代实现
                        print("[数据库] WEIXIN_WRITE_DB=1 但 MySQL 后端未迁移，跳过")
                        # row_id = insert_evidence_record(record)

                    if max_videos > 0 and index >= max_videos:
                        print("[流程] 达到最大采集数，当前段结束后停止")
                        break

                    next_segment = start_capture_session(
                        method=capture_method,
                        prefer_scrcpy=capture_prefer_scrcpy,
                    )
                    print(f"[录屏] 下一段录屏在滑动前已开始: {next_segment.local_path}")

                    try:
                        await swipe_up(session)
                        await asyncio.sleep(2.0)
                        if verify_video_page:
                            ok = await wait_for_video_page(session, timeout=5)
                            if ok:
                                print("[流程] 滑动完成，已检测到下一个视频页")
                            else:
                                print("[流程] 滑动已发送但未确认下一个视频页")
                                stop_capture_session(next_segment)
                                break
                    except Exception:
                        stop_capture_session(next_segment)
                        raise

                    segment = next_segment
            finally:
                if segment is not None:
                    try:
                        stop_capture_session(segment)
                    except Exception as exc:
                        print(f"[录屏] 最后段清理失败: {exc}")

                # --- 批量 ASR + 剧本比对（全部采集结束后统一触发） ---
                if collected_records:
                    print(f"\n{'=' * 60}")
                    print(f"[批量 ASR] 开始处理，共 {len(collected_records)} 条视频")
                    print(f"{'=' * 60}")
                    from weixin.asr.pipeline import run_asr_pipeline
                    from weixin.core.store import save_record as _save
                    for idx, rec in enumerate(collected_records, 1):
                        wav = rec.media_info.get("recording_audio_path")
                        if not wav:
                            print(f"[批量 ASR] [{idx}/{len(collected_records)}] 无音频，跳过")
                            continue
                        if rec.media_info.get("asr_text"):
                            print(f"[批量 ASR] [{idx}/{len(collected_records)}] 已有 ASR，跳过")
                            continue
                        vid = rec.candidate.get("video_identifier", "")
                        print(f"[批量 ASR] [{idx}/{len(collected_records)}] vid={vid[:16]}...")
                        try:
                            run_asr_pipeline(rec, str(wav), vid)
                            # 覆盖原有 JSON + HTML，不产生新文件
                            orig = record_json_paths.get(idx - 1, "")
                            if orig:
                                _save(rec, overwrite_json_path=orig)
                            else:
                                _save(rec)
                            print(f"[批量 ASR] [{idx}/{len(collected_records)}] 已更新")
                        except Exception as e:
                            print(f"[批量 ASR] [{idx}/{len(collected_records)}] ASR 失败: {e}")
                    print(f"[批量 ASR] 处理完成")

    print("\n[done]")


if __name__ == "__main__":
    asyncio.run(run())
