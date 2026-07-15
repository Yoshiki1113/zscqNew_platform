"""WebSocket — 任务实时日志推送"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import WS_HEARTBEAT_TIMEOUT
from engine import get_scheduler

router = APIRouter(tags=["WebSocket"])


@router.websocket("/tasks/{task_id}")
async def task_log_stream(websocket: WebSocket, task_id: int):
    """任务执行日志实时推送

    连接后：
    1. 先推送已积累的历史日志（回放）
    2. 然后持续推送新日志
    3. 客户端断开后自动清理
    """
    await websocket.accept()

    sched = get_scheduler()
    runner = sched.get_runner(task_id)

    # 回放历史日志
    if runner:
        for entry in runner.logs:
            try:
                await websocket.send_text(json.dumps(entry, ensure_ascii=False))
            except Exception:
                return

    # 注册到 runner 以接收实时推送
    if runner:
        runner.add_ws_client(websocket)
    else:
        # 任务不在运行中，发送完成状态
        await websocket.send_text(json.dumps({
            "timestamp": "",
            "level": "info",
            "message": "任务已结束或不存在",
            "type": "done",
        }, ensure_ascii=False))
        await websocket.close()
        return

    try:
        # 保持连接，接收客户端心跳
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=WS_HEARTBEAT_TIMEOUT)
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except asyncio.TimeoutError:
        pass  # 超时无操作，正常断开
    except WebSocketDisconnect:
        pass
    finally:
        if runner:
            runner.remove_ws_client(websocket)
