"""API 路由 — 设备管理"""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine import get_device_manager

router = APIRouter(tags=["设备管理"])


class DeviceOut(BaseModel):
    id: str = ""
    name: str = ""
    status: str = "offline"
    ip_address: str = ""
    connection_mode: str = ""
    screen_width: int = 0
    screen_height: int = 0
    model: str = ""
    android_version: str = ""
    last_checked_at: str = ""

    model_config = {"from_attributes": True}


class PreCheckOut(BaseModel):
    adb_connected: bool = False
    wechat_running: bool = False
    storage_ok: bool = True
    storage_used_pct: str = ""
    screen_on: bool = False
    scrcpy_available: bool = False
    scrcpy_path: str = ""
    ffmpeg_available: bool = False
    ffmpeg_path: str = ""
    ascript_port_reachable: bool = False
    all_checks_passed: bool = False


class RuntimeCheckOut(BaseModel):
    adb: dict = {}
    scrcpy: dict = {}
    ffmpeg: dict = {}


# ── 设备列表 ──

@router.get("/devices", response_model=list[DeviceOut])
async def list_devices():
    """扫描并返回当前 ADB 连接的设备列表（含分辨率、IP、型号）"""
    mgr = get_device_manager()
    devices = await mgr.scan_devices()
    return [DeviceOut(**d.to_dict()) for d in devices]


# ── 设备详情 ──

@router.get("/devices/{serial}", response_model=DeviceOut)
async def get_device(serial: str):
    """获取指定设备详情"""
    mgr = get_device_manager()
    info = await mgr.get_device_info(serial)
    if not info:
        raise HTTPException(status_code=404, detail=f"设备 {serial} 不存在或已离线")
    return DeviceOut(**info.to_dict())


# ── 前置检查 ──

@router.get("/devices/{serial}/check", response_model=PreCheckOut)
async def check_device(serial: str):
    """
    对指定设备执行完整前置检查：
    ADB 连接、微信状态、存储空间、屏幕点亮、scrcpy/ffmpeg/AScript
    """
    mgr = get_device_manager()
    # 先确保设备存在
    info = await mgr.get_device_info(serial)
    if not info:
        # 尝试扫描
        await mgr.scan_devices()
        info = await mgr.get_device_info(serial)
        if not info:
            raise HTTPException(status_code=404, detail=f"设备 {serial} 未连接或不存在")
    results = await mgr.run_pre_checks(serial)
    return PreCheckOut(**results)


# ── AScript 录屏授权检查（独立，较慢，前端单独按钮触发） ──

@router.get("/devices/{serial}/check-ascript")
async def check_ascript_permission(serial: str):
    """独立的 AScript 录屏授权检查：MCP 连接 + 截图，触发/验证 MediaProjection 权限。

    返回 {"ascript_connected": true} 表示权限已授予；false 表示弹窗已弹出待用户授权。
    """
    mgr = get_device_manager()
    info = await mgr.get_device_info(serial)
    if not info:
        await mgr.scan_devices()
        info = await mgr.get_device_info(serial)
        if not info:
            raise HTTPException(status_code=404, detail=f"设备 {serial} 未连接或不存在")
    connected = await mgr.check_ascript_permission(serial)
    return {"ascript_connected": connected}


# ── 运行时环境检查 ──

@router.get("/devices/check-runtime", response_model=RuntimeCheckOut)
async def check_runtime():
    """检查 PC 端运行时环境（ADB / scrcpy / ffmpeg）"""
    mgr = get_device_manager()
    results = await mgr.check_runtime()
    return RuntimeCheckOut(**results)


# ── 扫描设备（异步触发） ──

@router.post("/devices/scan", response_model=list[DeviceOut])
async def scan_devices():
    """重新扫描并刷新设备列表"""
    mgr = get_device_manager()
    devices = await mgr.scan_devices()
    return [DeviceOut(**d.to_dict()) for d in devices]


# ── ADB 连接/断开 ──

class AdbConnectRequest(BaseModel):
    host: str   # IP 地址，如 192.168.1.105
    port: int = 5555  # ADB 端口，默认 5555


class AdbDisconnectRequest(BaseModel):
    host: str   # 设备地址，如 192.168.1.105:5555 或 127.0.0.1:7555


@router.post("/devices/connect")
async def adb_connect(body: AdbConnectRequest):
    """通过 ADB 连接指定 IP 的设备（WiFi 调试模式）"""
    mgr = get_device_manager()
    target = f"{body.host}:{body.port}"
    stdout, stderr, rc = await mgr._run_adb("connect", target, timeout=10)
    if rc != 0 or "cannot connect" in (stdout + stderr).lower():
        raise HTTPException(status_code=400, detail=f"连接失败: {stderr or stdout}")
    # 连接成功后重新扫描，让设备出现在列表中
    devices = await mgr.scan_devices()
    return {
        "message": f"已连接 {target}",
        "devices": [DeviceOut(**d.to_dict()) for d in devices],
    }


@router.post("/devices/disconnect")
async def adb_disconnect(body: AdbDisconnectRequest):
    """断开指定 ADB 设备"""
    mgr = get_device_manager()
    stdout, stderr, rc = await mgr._run_adb("disconnect", body.host, timeout=10)
    if rc != 0:
        raise HTTPException(status_code=400, detail=f"断开失败: {stderr or stdout}")
    devices = await mgr.scan_devices()
    return {
        "message": f"已断开 {body.host}",
        "devices": [DeviceOut(**d.to_dict()) for d in devices],
    }
