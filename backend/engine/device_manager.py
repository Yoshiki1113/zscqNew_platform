"""设备管理器 — ADB 扫描、连接管理、状态心跳"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import SCRCPY_DIR, DEFAULT_PHONE_PORT


class DeviceInfo:
    """设备运行时信息（与 models.Device 互补）"""

    def __init__(self):
        self.serial: str = ""
        self.status: str = "offline"  # online | offline | busy
        self.ip_address: str = ""
        self.connection_mode: str = ""  # LocalIP | ADB | USB
        self.screen_width: int = 0
        self.screen_height: int = 0
        self.model: str = ""
        self.android_version: str = ""
        self.last_checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.serial,
            "name": self.model or self.serial,
            "status": self.status,
            "ip_address": self.ip_address,
            "connection_mode": self.connection_mode,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "model": self.model,
            "android_version": self.android_version,
            "last_checked_at": self.last_checked_at,
        }


class DeviceManager:
    """管理 ADB 设备连接、扫描、状态监控"""

    def __init__(self):
        self._adb_path: Optional[str] = None
        self._devices: dict[str, DeviceInfo] = {}
        self._lock = asyncio.Lock()
        self._monitoring = False

    @property
    def adb(self) -> str:
        """获取 adb 可执行文件路径"""
        import shutil

        if self._adb_path:
            return self._adb_path
        path = shutil.which("adb")
        if path:
            self._adb_path = path
            return path
        # Windows 回退到 .exe，Linux 不带后缀
        import platform as _platform
        name = "adb.exe" if _platform.system() == "Windows" else "adb"
        local = SCRCPY_DIR / name
        if local.exists():
            self._adb_path = str(local)
            return str(local)
        return "adb"

    # ── ADB 基础操作 ──

    async def _run_adb(self, *args, timeout: int = 10, device: Optional[str] = None) -> tuple[str, str, int]:
        """异步运行 adb 命令，返回 (stdout, stderr, returncode)
        
        Windows 下 asyncio.create_subprocess_exec 与 ProactorEventLoop 不兼容，
        因此通过线程池执行同步 subprocess.run。"""
        cmd = [self.adb]
        if device:
            cmd.extend(["-s", device])
        cmd.extend(args)

        def _run():
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
                return proc.stdout, proc.stderr, proc.returncode
            except FileNotFoundError:
                return "", f"'{self.adb}' 未找到", -1
            except subprocess.TimeoutExpired:
                return "", "timeout", -1

        return await asyncio.to_thread(_run)

    # ── 设备扫描 ──

    async def scan_devices(self) -> list[DeviceInfo]:
        """扫描所有 ADB 连接设备，获取分辨率、IP、型号等信息"""
        try:
            stdout, _, rc = await self._run_adb("devices", timeout=5)
        except Exception:
            return []
        if rc != 0:
            return []

        devices: list[DeviceInfo] = []
        for line in stdout.strip().split("\n")[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            if state != "device":
                continue

            info = DeviceInfo()
            info.serial = serial
            info.status = "online"
            info.last_checked_at = datetime.now().isoformat(timespec="seconds")

            # 获取分辨率
            try:
                stdout2, _, _ = await self._run_adb("shell", "wm", "size", device=serial, timeout=5)
                m = re.search(r"(\d+)x(\d+)", stdout2)
                if m:
                    info.screen_width = int(m.group(1))
                    info.screen_height = int(m.group(2))
            except Exception:
                pass

            # 获取 WiFi IP
            try:
                stdout2, _, _ = await self._run_adb("shell", "ip", "addr", "show", "wlan0", device=serial, timeout=5)
                m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", stdout2)
                if m:
                    info.ip_address = m.group(1)
                    info.connection_mode = "LocalIP"
            except Exception:
                pass

            # 获取设备型号
            try:
                stdout2, _, _ = await self._run_adb("shell", "getprop", "ro.product.model", device=serial, timeout=5)
                info.model = stdout2.strip()
            except Exception:
                pass

            # 获取 Android 版本
            try:
                stdout2, _, _ = await self._run_adb("shell", "getprop", "ro.build.version.release", device=serial, timeout=5)
                info.android_version = stdout2.strip()
            except Exception:
                pass

            devices.append(info)

        # 更新内部缓存
        async with self._lock:
            for d in devices:
                self._devices[d.serial] = d

        return devices

    def scan_devices_sync(self) -> list[DeviceInfo]:
        """同步版本的设备扫描（供初始化时使用）"""
        import subprocess as _subprocess

        adb = self.adb
        try:
            proc = _subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10)
        except Exception:
            return []

        devices: list[DeviceInfo] = []
        for line in proc.stdout.strip().split("\n")[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            if state != "device":
                continue

            info = DeviceInfo()
            info.serial = serial
            info.status = "online"
            info.last_checked_at = datetime.now().isoformat(timespec="seconds")

            # 获取分辨率
            try:
                p = _subprocess.run([adb, "-s", serial, "shell", "wm", "size"], capture_output=True, text=True, timeout=5)
                m = re.search(r"(\d+)x(\d+)", p.stdout)
                if m:
                    info.screen_width = int(m.group(1))
                    info.screen_height = int(m.group(2))
            except Exception:
                pass

            # IP
            try:
                p = _subprocess.run([adb, "-s", serial, "shell", "ip", "addr", "show", "wlan0"], capture_output=True, text=True, timeout=5)
                m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", p.stdout)
                if m:
                    info.ip_address = m.group(1)
                    info.connection_mode = "LocalIP"
            except Exception:
                pass

            # 型号
            try:
                p = _subprocess.run([adb, "-s", serial, "shell", "getprop", "ro.product.model"], capture_output=True, text=True, timeout=5)
                info.model = p.stdout.strip()
            except Exception:
                pass

            devices.append(info)

        self._devices = {d.serial: d for d in devices}
        return devices

    # ── 设备状态 ──

    async def get_device_info(self, serial: str) -> Optional[DeviceInfo]:
        """获取指定设备信息"""
        async with self._lock:
            return self._devices.get(serial)

    def get_all_devices(self) -> list[DeviceInfo]:
        """获取所有已知设备"""
        return list(self._devices.values())

    def mark_busy(self, serial: str):
        """标记设备为忙碌"""
        if serial in self._devices:
            self._devices[serial].status = "busy"

    def mark_online(self, serial: str):
        """标记设备为在线"""
        if serial in self._devices:
            self._devices[serial].status = "online"

    # ── 前置检查 ──

    async def run_pre_checks(self, serial: str) -> dict:
        """对指定设备执行前置环境检查，返回各项检查结果"""
        results = {}

        # 1. ADB 连接检查
        stdout, _, _ = await self._run_adb("shell", "echo", "OK", device=serial, timeout=5)
        results["adb_connected"] = "OK" in stdout

        # 2. 视频号是否在前台（用 dumpsys window 的 mCurrentFocus 检测焦点窗口）
        #    视频号是独立 Activity（FinderHomeAffinityUI），但 topResumedActivity 常误报
        #    为 LauncherUI；dumpsys window 的 mCurrentFocus 才准确反映当前焦点窗口。
        try:
            stdout, _, _ = await self._run_adb(
                "shell", "dumpsys", "window", device=serial, timeout=5
            )
            # 提取非 null 的 mCurrentFocus 行（过渡态可能为 null）
            focus_lines = [
                s for s in (line.strip() for line in stdout.splitlines())
                if s.startswith("mCurrentFocus=") and "null" not in s
            ]
            focus = focus_lines[-1] if focus_lines else ""
            # 视频号焦点窗口: com.tencent.mm/com.tencent.mm.plugin.finder.ui.FinderHomeAffinityUI
            results["wechat_running"] = "com.tencent.mm" in focus and "finder" in focus.lower()
        except Exception:
            results["wechat_running"] = False

        # 3. 存储空间检查
        try:
            stdout, _, _ = await self._run_adb("shell", "df", "/sdcard", device=serial, timeout=5)
            for line in stdout.split("\n"):
                parts = line.split()
                if len(parts) >= 4 and parts[-1] == "/sdcard":
                    used_pct = parts[3].replace("%", "")
                    results["storage_ok"] = int(used_pct) < 90 if used_pct.isdigit() else True
                    results["storage_used_pct"] = used_pct
                    break
            else:
                results["storage_ok"] = True
        except Exception:
            results["storage_ok"] = True

        # 4. 屏幕是否点亮
        try:
            stdout, _, _ = await self._run_adb("shell", "dumpsys", "power", device=serial, timeout=5)
            results["screen_on"] = "mWakefulness=Awake" in stdout or "Display Power: state=ON" in stdout
        except Exception:
            results["screen_on"] = False

        # 5. scrcpy 可用性
        import shutil, platform as _platform
        scrcpy_name = "scrcpy.exe" if _platform.system() == "Windows" else "scrcpy"
        scrcpy = SCRCPY_DIR / scrcpy_name
        if not scrcpy.exists():
            scrcpy_path = shutil.which("scrcpy")
            results["scrcpy_available"] = bool(scrcpy_path)
            results["scrcpy_path"] = scrcpy_path or ""
        else:
            results["scrcpy_available"] = True
            results["scrcpy_path"] = str(scrcpy)

        # 6. ffmpeg 可用性
        ffmpeg = shutil.which("ffmpeg")
        results["ffmpeg_available"] = bool(ffmpeg)
        results["ffmpeg_path"] = ffmpeg or ""

        # 7. AScript 端口可达性检查（快速 TCP 探测）
        #    录屏授权检查较慢（需 MCP 连接 + 截图），已拆分到独立方法 check_ascript_permission，
        #    由前端单独按钮触发，避免拖慢常规刷新检查。
        ip = self._devices.get(serial, DeviceInfo()).ip_address
        results["ascript_port_reachable"] = await self._check_port(ip, DEFAULT_PHONE_PORT) if ip else False

        # 汇总
        critical_checks = ["adb_connected", "wechat_running", "screen_on", "ascript_port_reachable"]
        results["all_checks_passed"] = all(results.get(k, False) for k in critical_checks)
        return results

    async def check_ascript_permission(self, serial: str) -> bool:
        """独立的 AScript 录屏授权检查：MCP 连接 + 截图，触发/验证 MediaProjection 权限。

        较慢（约 5-15 秒），与常规前置检查分离，由前端单独按钮触发。
        返回 True 表示权限已授予可正常截图，False 表示弹窗已弹出待用户授权或端口不可达。
        """
        ip = self._devices.get(serial, DeviceInfo()).ip_address
        if not ip:
            return False
        if not await self._check_port(ip, DEFAULT_PHONE_PORT):
            return False
        return await self._check_ascript_connect(ip, DEFAULT_PHONE_PORT)

    @staticmethod
    async def _check_port(host: str, port: int, timeout: float = 3.0) -> bool:
        """检查 TCP 端口是否可达"""
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    @staticmethod
    async def _check_ascript_connect(ip: str, port: int, timeout: float = 25.0) -> bool:
        """启动 MCP 会话连接设备并执行一次截图，触发手机端 AScript 录屏/投屏权限弹窗。

        connect_device 仅建立 socket 连接，不会触发 MediaProjection 权限弹窗；
        真正触发「要开始使用AScript录屏或投屏吗」弹窗的是 screen.capture_cv()
        等屏幕捕获操作（通过 deploy_and_run 在手机端运行）。
        因此在连接成功后额外执行一次最小截图请求，让权限弹窗在前置检查阶段
        就弹出，避免任务启动后才弹窗打断采集。
        """
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            sp = StdioServerParameters(
                command="python", args=["-m", "ascript_mcp.local"],
                env={**os.environ},
            )

            async def _do_connect_and_trigger():
                async with stdio_client(sp) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        # 1. 连接设备（仅建立 socket 连接，不触发权限弹窗）
                        result = await session.call_tool(
                            "connect_device",
                            {"ip": ip, "port": port, "connection_mode": "LocalIP"},
                        )
                        texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
                        merged = "\n".join(texts).lower()
                        failure_tokens = ("fail", "error", "失败", "错误", "未连接")
                        success_tokens = ("connected", "已连接", "success", "成功", "本地端口")
                        if any(token in merged for token in failure_tokens):
                            return False
                        if not any(token in merged for token in success_tokens):
                            return False

                        # 2. 执行一次截图，触发 MediaProjection 权限弹窗
                        #    screen.capture_cv() 首次调用会弹出系统授权对话框；
                        #    已授权则立即返回截图，未授权则阻塞等待用户操作。
                        #    log_seconds 到期后返回，弹窗留在屏幕上等用户点击。
                        trigger_code = (
                            "import base64, cv2\n"
                            "from ascript.android import screen\n"
                            "img = screen.capture_cv()\n"
                            "if img is not None:\n"
                            "    _, buf = cv2.imencode('.png', img)\n"
                            "    print(base64.b64encode(buf.tobytes()).decode('utf-8'))\n"
                        )
                        try:
                            shot_result = await session.call_tool(
                                "deploy_and_run",
                                {"project_name": "zscqAndroid", "code": trigger_code, "log_seconds": 5},
                            )
                            # 截图成功 = 权限已授予；无截图数据 = 弹窗已弹出但用户尚未授权
                            shot_text = "".join(
                                c.text for c in shot_result.content if getattr(c, "type", "") == "text"
                            )
                            return "iVBORw0KGgo" in shot_text or any(
                                getattr(c, "type", "") == "image" for c in shot_result.content
                            )
                        except Exception:
                            return False

            return await asyncio.wait_for(_do_connect_and_trigger(), timeout=timeout)
        except Exception:
            return False

    # ── 运行时环境检查 ──

    async def check_runtime(self) -> dict:
        """检查 PC 端运行时环境（ADB / scrcpy / ffmpeg）"""
        results = {}

        # ADB
        adb = self.adb
        stdout, _, rc = await self._run_adb("version", timeout=5)
        results["adb"] = {"available": rc == 0, "path": adb, "version": stdout.split("\n")[0] if rc == 0 else ""}

        # scrcpy
        import shutil, platform as _platform
        scrcpy_name = "scrcpy.exe" if _platform.system() == "Windows" else "scrcpy"
        scrcpy = SCRCPY_DIR / scrcpy_name
        if not scrcpy.exists():
            scrcpy = shutil.which("scrcpy") or ""
        results["scrcpy"] = {"available": bool(scrcpy) and Path(str(scrcpy)).exists(), "path": str(scrcpy)}

        # ffmpeg
        ffmpeg = shutil.which("ffmpeg")
        results["ffmpeg"] = {"available": bool(ffmpeg), "path": ffmpeg or ""}

        return results

    # ── 心跳监控 ──

    async def start_heartbeat(self, serial: str, interval: int = 30, callback=None):
        """启用心跳监控，定期检查设备在线状态"""
        if serial not in self._devices:
            return

        async def _beat():
            while serial in self._devices and self._devices[serial].status != "offline":
                try:
                    stdout, _, _ = await self._run_adb("shell", "echo", "OK", device=serial, timeout=5)
                    is_online = "OK" in stdout
                    if serial in self._devices:
                        self._devices[serial].status = "online" if is_online else "offline"
                        self._devices[serial].last_checked_at = datetime.now().isoformat(timespec="seconds")
                    if callback:
                        await callback(serial, self._devices.get(serial))
                except Exception:
                    if serial in self._devices:
                        self._devices[serial].status = "offline"
                await asyncio.sleep(interval)

        asyncio.create_task(_beat())


# 全局单例
_device_manager: Optional[DeviceManager] = None


def get_device_manager() -> DeviceManager:
    """获取全局 DeviceManager 单例"""
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager
