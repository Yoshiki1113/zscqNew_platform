"""任务调度器 — asyncio 任务队列 + 状态机"""
from __future__ import annotations

import asyncio
import json
import os
import queue
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from config import TASK_LOG_MAX_LINES, TASK_CLEANUP_DELAY_SECONDS
from database import async_session
from models import Task


def _unwrap_error(e: BaseException) -> str:
    """展开 ExceptionGroup，获取底层真实错误信息"""
    if isinstance(e, BaseExceptionGroup) and e.exceptions:
        return "; ".join(_unwrap_error(sub) for sub in e.exceptions)
    return str(e)


def _num(v) -> float:
    """安全转 float，失败返回 0.0"""
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _json_dump(v) -> str:
    try:
        return json.dumps(v, ensure_ascii=False) if v else "[]"
    except Exception:
        return "[]"


class TaskRunner:
    """单个任务运行实例，管理一条任务的完整生命周期"""

    def __init__(self, task_id: int, collector_kwargs: dict):
        self.task_id = task_id
        self.collector_kwargs = collector_kwargs
        self._collector = None
        self._logs: list[dict] = []
        self._ws_clients: list = []
        self._log_queue: queue.Queue = queue.Queue()
        self._queue_pumper: Optional[asyncio.Task] = None
        self._collector_task: Optional[asyncio.Task] = None

    @property
    def logs(self) -> list[dict]:
        return self._logs

    def add_ws_client(self, ws):
        if ws not in self._ws_clients:
            self._ws_clients.append(ws)

    def remove_ws_client(self, ws):
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    async def broadcast(self, entry: dict):
        """向所有 WebSocket 客户端广播日志（必须在主事件循环中调用）"""
        self._logs.append(entry)
        if len(self._logs) > TASK_LOG_MAX_LINES:
            self._logs = self._logs[-TASK_LOG_MAX_LINES:]
        # 异步发送，不阻塞调用方（用于批量消费场景）
        asyncio.create_task(self._send_to_all(entry))

    async def _send_to_all(self, entry: dict):
        """向所有 WebSocket 客户端发送单条日志。"""
        payload = json.dumps(entry, ensure_ascii=False)
        disconnected = []
        for ws in self._ws_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._ws_clients.remove(ws)

    async def _pump_log_queue(self):
        """主事件循环任务：从线程安全队列中取出日志并广播。
        
        采用异步发送模式：消费队列时不等待每条日志的 WebSocket send 完成，
        而是用 create_task 并发发送，确保队列消费速度远大于网络 IO 速度。
        """
        while True:
            try:
                while True:
                    entry = self._log_queue.get_nowait()
                    # 异步广播，不阻塞队列消费
                    await self.broadcast(entry)
                    self._log_queue.task_done()
            except queue.Empty:
                pass
            await asyncio.sleep(0.1)

    def _enqueue_log(self, entry: dict):
        """线程安全：将日志放入队列（可从任意线程调用）"""
        self._log_queue.put(entry)

    def enqueue_log_sync(self, level: str, message: str):
        """同步入队：直接放入线程安全队列，不经过事件循环。

        这是为 _emit_callback 设计的同步入口 — 采集线程内的 print 会被拦截，
        调用此方法直接入队，避免 asyncio.create_task 在同步代码块中延迟执行。
        """
        from datetime import datetime as _dt
        self._log_queue.put({
            "timestamp": _dt.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        })

    async def run(self):
        """启动采集任务，阻塞直到采集完成或失败"""
        from engine.weixin_collector import WeixinCollector

        # 启动队列泵
        self._queue_pumper = asyncio.create_task(self._pump_log_queue())

        async def log_callback(log_entry):
            try:
                self._enqueue_log(log_entry.to_dict())
            except Exception:
                pass

        collector = WeixinCollector(
            log_callback=log_callback,
            sync_log_callback=self.enqueue_log_sync,
            **self.collector_kwargs,
        )
        self._collector = collector

        # 在线程池中运行采集器，等待完成
        try:
            await self._update_task_status("running", started_at=datetime.now())

            records = await collector.run()

            await self._update_task_status("links_collected", finished_at=datetime.now())

            if records:
                await self._link_records(collector)

            await self.broadcast({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "success",
                "message": f"任务完成: {len(records)} 条证据",
                "type": "done",
                "records": len(records),
            })

        except asyncio.CancelledError:
            await self._update_task_status("stopped", error_message="用户手动停止")
            await self.broadcast({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "warning",
                "message": "任务已被停止",
                "type": "done",
            })
        except Exception as e:
            msg = _unwrap_error(e)
            await self._update_task_status("failed", error_message=msg)
            await self.broadcast({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "error",
                "message": f"任务异常: {msg}",
                "type": "done",
            })
        finally:
            if self._queue_pumper and not self._queue_pumper.done():
                self._queue_pumper.cancel()

    async def _update_task_status(self, status: str, **kwargs):
        async with async_session() as session:
            task = (await session.execute(select(Task).where(Task.id == self.task_id))).scalar_one_or_none()
            if task:
                task.status = status
                for key, value in kwargs.items():
                    setattr(task, key, value)
                await session.commit()

    async def _link_records(self, collector):
        """关联证据记录到当前任务（仅 Phase 2 调用，Phase 1 已直接写入正确 task_id）"""
        db_ids = getattr(collector, '_db_record_ids', [])
        async with async_session() as session:
            if db_ids:
                from models import EvidenceRecord
                for rid in db_ids:
                    rec = (await session.execute(select(EvidenceRecord).where(EvidenceRecord.id == rid))).scalar_one_or_none()
                    if rec:
                        rec.task_id = self.task_id
            await session.commit()

    async def _update_asr_in_db(self, weixin_record, video_identifier: str):
        """ASR 完成后更新平台数据库中的 ASR/剧本字段，并覆盖原有 JSON+HTML 文件"""
        d = weixin_record.to_dict() if hasattr(weixin_record, 'to_dict') else weixin_record
        media = d.get("media_info", {})
        script_match = media.get("script_match", {})

        # 更新数据库
        from models import EvidenceRecord
        original_json_path = ""
        async with async_session() as session:
            row = (await session.execute(
                select(EvidenceRecord).where(
                    EvidenceRecord.task_id == self.task_id,
                    EvidenceRecord.video_identifier == video_identifier,
                ).order_by(EvidenceRecord.id.desc())
            )).scalars().first()
            if row:
                row.asr_text = media.get("asr_text", "") or row.asr_text
                row.asr_model = media.get("asr_model", "") or row.asr_model
                row.script_match_status = script_match.get("status", "pending") or row.script_match_status
                best = script_match.get("best_match", {}) or {}
                if best:
                    row.script_match_similarity = _num(best.get("similarity_score")) or _num(best.get("score")) or row.script_match_similarity
                    row.script_match_pinyin_score = _num(best.get("pinyin_score")) or row.script_match_pinyin_score
                    row.script_match_char_score = _num(best.get("char_score")) or row.script_match_char_score
                    row.script_match_episode = best.get("episode", "") or row.script_match_episode
                    row.script_match_scene = best.get("scene", "") or row.script_match_scene
                    row.script_match_character = best.get("character", "") or row.script_match_character
                    row.script_match_location = best.get("location", "") or row.script_match_location
                    row.script_match_script_text = best.get("script_text", "") or row.script_match_script_text
                # 分段匹配字段
                if script_match.get("status") == "matched":
                    row.script_match_similarity = _num(script_match.get("coverage")) or row.script_match_similarity
                row.script_match_segments_matched = script_match.get("segments_matched", 0) or row.script_match_segments_matched
                row.script_match_segments_total = script_match.get("segments_total", 0) or row.script_match_segments_total
                row.script_match_segments_json = _json_dump(script_match.get("segments", []))

                # 计算侵权评分
                _coverage = _num(script_match.get("coverage")) if script_match.get("status") == "matched" else 0.0
                _best_pinyin = _num(best.get("pinyin_score")) if best else 0.0
                _best_char = _num(best.get("char_score")) if best else 0.0
                _best_score = _best_pinyin * 0.55 + _best_char * 0.45
                _segments = script_match.get("segments_matched", 0) or 0
                _seg_score = min(_segments / 5, 1.0)
                row.infringement_score = round(_coverage * 0.35 + _best_score * 0.40 + _seg_score * 0.25, 4)
                if row.infringement_score >= 0.70:
                    row.infringement_level = "高度疑似"
                elif row.infringement_score >= 0.50:
                    row.infringement_level = "疑似"
                elif row.infringement_score >= 0.30:
                    row.infringement_level = "待观察"
                else:
                    row.infringement_level = "无"

                original_json_path = row.json_path or ""
                await session.commit()

        # 覆盖原有 JSON+HTML 文件（不产生新文件）
        if original_json_path:
            from config import EVIDENCE_DATA_DIR
            abs_path = EVIDENCE_DATA_DIR / original_json_path
            try:
                from weixin.core.store import save_record
                save_record(weixin_record, overwrite_json_path=str(abs_path))
            except Exception:
                pass

    async def stop(self):
        """停止任务"""
        if self._collector:
            self._collector.stop()
        if self._collector_task and not self._collector_task.done():
            self._collector_task.cancel()
        if self._queue_pumper and not self._queue_pumper.done():
            self._queue_pumper.cancel()


class TaskScheduler:
    """任务调度器"""

    def __init__(self):
        self._runners: dict[int, TaskRunner] = {}
        self._lock = asyncio.Lock()

    @property
    def active_tasks(self) -> list[int]:
        return list(self._runners.keys())

    def get_runner(self, task_id: int) -> Optional[TaskRunner]:
        return self._runners.get(task_id)

    async def start_task(self, task_id: int, **collector_kwargs):
        """启动任务，返回后任务在后台运行"""
        collector_kwargs["task_id"] = task_id
        async with self._lock:
            if task_id in self._runners:
                raise RuntimeError(f"任务 #{task_id} 已在运行中")
            runner = TaskRunner(task_id, collector_kwargs)
            self._runners[task_id] = runner

        # 在后台运行任务，完成后自动清理（延迟5分钟保留日志）
        async def _run_and_cleanup():
            try:
                await runner.run()
            finally:
                await asyncio.sleep(TASK_CLEANUP_DELAY_SECONDS)  # 完成后保留供回放
                async with self._lock:
                    self._runners.pop(task_id, None)

        runner._collector_task = asyncio.create_task(_run_and_cleanup())

    async def stop_task(self, task_id: int) -> bool:
        async with self._lock:
            runner = self._runners.get(task_id)
        if runner:
            await runner.stop()
            return True
        return False

    async def start_phase2(self, task_id: int, **collector_kwargs):
        """启动阶段二：从 video_links 表读取待处理链接，逐条完整取证

        此方法为 link_first 模式的第二阶段，在阶段一完成（links_collected）后调用。
        创建一个新的 WeixinCollector 实例，调用 run_phase2() 处理链接。
        """
        # 复用一个已有的 runner，仅更新 collector
        async with self._lock:
            runner = self._runners.get(task_id)
            if not runner:
                # 阶段一已完成并被清理（TASK_CLEANUP_DELAY_SECONDS 过期），
                # 创建新的 runner
                runner = TaskRunner(task_id, collector_kwargs)
                self._runners[task_id] = runner

        from engine.weixin_collector import WeixinCollector

        # 清空阶段一的历史日志，避免 WS 回放时两阶段混在一起
        runner._logs = []

        async def _run_and_cleanup():
            runner._queue_pumper = asyncio.create_task(runner._pump_log_queue())

            async def log_callback(log_entry):
                try:
                    runner._enqueue_log(log_entry.to_dict())
                except Exception:
                    pass

            collector = WeixinCollector(
                task_id=task_id,
                log_callback=log_callback,
                sync_log_callback=runner.enqueue_log_sync,
                **collector_kwargs,
            )
            runner._collector = collector

            try:
                await runner._update_task_status("running", started_at=datetime.now())

                records = await collector.run_phase2()

                await runner._update_task_status("completed", finished_at=datetime.now())

                if records:
                    await runner._link_records(collector)

                await runner.broadcast({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "level": "success",
                    "message": f"阶段二完成: {len(records)} 条证据",
                    "type": "done",
                    "records": len(records),
                })

            except asyncio.CancelledError:
                await runner._update_task_status("stopped", error_message="用户手动停止")
            except Exception as e:
                msg = _unwrap_error(e)
                await runner._update_task_status("failed", error_message=msg)
                await runner.broadcast({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "level": "error",
                    "message": f"阶段二异常: {msg}",
                    "type": "done",
                })
            finally:
                if runner._queue_pumper and not runner._queue_pumper.done():
                    runner._queue_pumper.cancel()
                await asyncio.sleep(TASK_CLEANUP_DELAY_SECONDS)
                async with self._lock:
                    self._runners.pop(task_id, None)

        runner._collector_task = asyncio.create_task(_run_and_cleanup())

    def get_task_logs(self, task_id: int) -> list[dict]:
        runner = self._runners.get(task_id)
        return runner.logs if runner else []

    def is_running(self, task_id: int) -> bool:
        return task_id in self._runners


_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler
