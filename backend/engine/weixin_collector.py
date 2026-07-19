"""微信采集器 — 封装 weixin/core/ 采集流程"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


def _unwrap_group(e: BaseException) -> str:
    """展开 ExceptionGroup，获取底层真实错误"""
    if isinstance(e, BaseExceptionGroup) and e.exceptions:
        return "; ".join(_unwrap_group(sub) for sub in e.exceptions)
    return str(e)


from config import (
    EVIDENCE_DIR, SCREENSHOTS_DIR, RECORDINGS_DIR, JSONS_DIR, TEMP_DIR,
    DEFAULT_PHONE_PORT, DEFAULT_MAX_VIDEOS, DEFAULT_HOLD_SECONDS,
)


class CollectionLog:
    """采集日志条目"""
    def __init__(self, timestamp: str, level: str, message: str):
        self.timestamp = timestamp
        self.level = level  # info | success | warning | error
        self.message = message

    def to_dict(self) -> dict:
        return {"timestamp": self.timestamp, "level": self.level, "message": self.message}


class WeixinCollector:
    """
    微信视频号取证采集器

    封装 weixin/core/ 的完整采集流程：
    设备连接 → 搜索关键词 → 逐条视频取证 → 证据落盘 → 批量 ASR
    """

    _MCP_INITIALIZED = False

    def __init__(
        self,
        keyword: str,
        device_ip: str = "",
        device_port: int = DEFAULT_PHONE_PORT,
        device_serial: str = "",
        max_videos: int = DEFAULT_MAX_VIDEOS,
        hold_seconds: int = DEFAULT_HOLD_SECONDS,
        capture_method: str = "scrcpy",
        prefer_scrcpy: bool = True,
        write_db: bool = True,
        enable_asr: bool = True,
        skip_search: bool = False,
        task_id: Optional[int] = None,
        work_order_id: Optional[int] = None,
        log_callback: Optional[Callable] = None,
        sync_log_callback: Optional[Callable] = None,
    ):
        self.keyword = keyword
        self.device_ip = device_ip
        self.device_port = device_port
        self.device_serial = device_serial
        self.max_videos = max_videos
        self.hold_seconds = hold_seconds
        self.capture_method = capture_method
        self.prefer_scrcpy = prefer_scrcpy
        self.enable_asr = enable_asr
        self.skip_search = skip_search
        self.task_id = task_id
        self.work_order_id = work_order_id
        self.write_db = write_db
        self.log_callback = log_callback  # async callback(log_entry: CollectionLog)
        self._sync_log_callback = sync_log_callback  # sync callback(level: str, message: str) — 线程安全

        self._running = False
        self._stopped = False
        self._collected_records: list = []  # weixin EvidenceRecord 对象
        self._db_record_ids: list[int] = []  # 平台数据库行 ID

        # 设置环境变量供 weixin/core/ 使用
        os.environ["WEIXIN_MAX_VIDEOS"] = str(max_videos)
        os.environ["WEIXIN_POST_EVIDENCE_HOLD_SECONDS"] = str(hold_seconds)
        os.environ["WEIXIN_CAPTURE_METHOD"] = capture_method
        os.environ["WEIXIN_PREFER_SCRCPY"] = "1" if prefer_scrcpy else "0"
        os.environ["WEIXIN_WRITE_DB"] = "0"  # 平台自己写 DB，不让 weixin 写 MySQL
        os.environ["WEIXIN_REALTIME_OCR"] = "1"  # 开启实时 OCR 提取博主/标题/视频号ID
        os.environ["WEIXIN_REALTIME_TRAFFIC_OCR"] = "1"  # 开启实时引流 OCR

    # ── 日志 ──

    async def _emit(self, level: str, message: str):
        """发送日志到回调"""
        ts = datetime.now().strftime("%H:%M:%S")
        entry = CollectionLog(ts, level, message)
        if self.log_callback:
            try:
                await self.log_callback(entry)
            except Exception:
                pass

    def info(self, msg: str):
        print(f"[collector] {msg}")
        if self._running:
            asyncio.ensure_future(self._emit("info", msg))

    def success(self, msg: str):
        print(f"[collector] ✅ {msg}")
        if self._running:
            asyncio.ensure_future(self._emit("success", msg))

    def warning(self, msg: str):
        print(f"[collector] ⚠️ {msg}")
        if self._running:
            asyncio.ensure_future(self._emit("warning", msg))

    def error(self, msg: str):
        print(f"[collector] ❌ {msg}")
        if self._running:
            asyncio.ensure_future(self._emit("error", msg))

    # ── 核心采集流程 ──

    async def run(self) -> list[dict]:
        """
        执行采集流程

        二阶段模式：先 run() 执行阶段一（收集链接），再 run_phase2() 逐条取证
        """
        self._running = True
        self._stopped = False
        phase1_done = False
        start_time = datetime.now()

        try:
            await self._emit("info", f"{'='*50}")
            await self._emit("info", f"开始取证任务")
            await self._emit("info", f"  关键词: {self.keyword}")
            await self._emit("info", f"  最大视频: {self.max_videos}")
            await self._emit("info", f"  录屏方式: {self.capture_method}")
            await self._emit("info", f"{'='*50}")

            # 导入 weixin 核心模块（已迁移到 platform/backend/weixin/ 包内）
            import weixin.core.main as _weixin_main
            import weixin.core.media_capture as _weixin_media

            # 将 weixin 的文件输出路径重定向到 platform/evidence_data/
            _weixin_main.SCREENSHOT_DIR = str(SCREENSHOTS_DIR)
            _weixin_main.JSONS_DIR = str(JSONS_DIR)
            _weixin_media.MEDIA_DIR = RECORDINGS_DIR

            # 注入设备连接参数（来自平台配置或 API 传入）
            if self.device_ip:
                _weixin_main.PHONE_IP = self.device_ip
            _weixin_main.PHONE_PORT = self.device_port
            # 注入设备 serial，避免多设备时 ADB 报 "more than one device"
            if self.device_serial:
                _weixin_main._CURRENT_DEVICE_SERIAL = self.device_serial

            # 注册 emit 回调，让 weixin core 内部的 print 也推送到前端
            def _emit_cb(msg):
                try:
                    if self._sync_log_callback:
                        self._sync_log_callback("info", msg)
                    else:
                        asyncio.create_task(self._emit("info", msg))
                except Exception:
                    pass
            _weixin_main._emit_callback = _emit_cb

            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            sp = StdioServerParameters(
                command="python", args=["-m", "ascript_mcp.local"],
                env={**os.environ},
            )
            async with stdio_client(sp) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.success("MCP 会话已初始化")

                    if self._stopped:
                        await self._emit("warning", "任务已被用户停止")
                        return []

                    # 连接设备
                    from weixin.core.main import connect_device_auto_v2
                    if not await connect_device_auto_v2(session):
                        self.error("设备连接失败")
                        raise RuntimeError("设备连接失败")
                    self.success("设备已连接")

                    if self._stopped:
                        await self._emit("warning", "任务已被用户停止")
                        return []

                    # 执行阶段一：收集链接
                    await self._run_phase1(session, _emit_cb)
                    phase1_done = True
                    return []

        except Exception as e:
            if phase1_done:
                self.warning(f"MCP 会话清理异常（Phase 1 已正常完成，不影响结果）: {_unwrap_group(e)}")
                return []
            msg = _unwrap_group(e)
            self.error(f"取证任务异常: {msg}")
            raise
        finally:
            self._running = False


    # ── Phase 1: 收集链接 ──

    async def _run_phase1(self, session, _emit_cb) -> int:
        """
        阶段一：搜索关键词 → 点击首个视频 → 逐条复制分享链接 → 存入 video_links 表

        只做链接收集，不做录屏/截图/OCR/ASR 等重操作

        Returns: 收集到的链接数量
        """
        import weixin.core.collector as _collector
        _collector._emit_callback = _emit_cb

        # 搜索关键词
        if self.skip_search:
            await self._emit("warning", "已跳过搜索步骤，直接从当前视频开始")
        else:
            from weixin.core.main import search_keyword
            if not await search_keyword(session, self.keyword):
                self.error("Phase 1 搜索失败")
                return 0
            await self._emit("info", f"搜索完成: {self.keyword}")

            if self._stopped:
                return 0

            from weixin.core.main import click_first_video_result
            await click_first_video_result(session)
            self.success("已打开首个视频")


        from weixin.core.collector import _is_bottom_reached, capture_single_via_adb_execout
        from weixin.core.main import swipe_up
        from weixin.core.collector import (
            read_phone_clipboard,
            extract_link_from_clipboard_text,
            strip_phone_log_wrappers,
        )
        from weixin.core.main import run_on_phone, scale_point
        from weixin.core.collector import (
            SHARE_BUTTON_X, SHARE_BUTTON_Y,
            SHARE_TRAY_SWIPE_START_X, SHARE_TRAY_SWIPE_END_X, SHARE_TRAY_Y,
            COPY_LINK_X, COPY_LINK_Y,
        )

        def _parse_clipboard_from_log(log: str) -> str:
            start = log.find("CLIPBOARD_START")
            end = log.find("CLIPBOARD_END")
            if start < 0 or end <= start:
                return ""
            raw_text = log[start + len("CLIPBOARD_START"):end].strip()
            return strip_phone_log_wrappers(raw_text)

        # 快速复制链接：设哨兵+分享+复制+读剪贴板合并为一次 MCP，失败再补 1 次读剪贴板
        async def _fast_copy_link(session, tag: str) -> str:
            sentinel = f"__WEIXIN_COPY_PENDING_{tag}__"
            sentinel_esc = sentinel.replace("\\", "\\\\").replace("'", "\\'")

            share_x, share_y = scale_point(SHARE_BUTTON_X, SHARE_BUTTON_Y)
            tray_sx, tray_y = scale_point(SHARE_TRAY_SWIPE_START_X, SHARE_TRAY_Y)
            tray_ex, _ = scale_point(SHARE_TRAY_SWIPE_END_X, SHARE_TRAY_Y)
            copy_x, copy_y = scale_point(COPY_LINK_X, COPY_LINK_Y)

            code = f"""
import time
from ascript.android import action

# 哨兵：用于判断剪贴板是否已被「复制链接」刷新
try:
    from ascript.android.system import Clipboard
    Clipboard.set('{sentinel_esc}')
except Exception:
    try:
        from android.content import ClipData, Context
        from com.aojoy.airscript import Globals
        ctx = Globals.getContext()
        cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
        cm.setPrimaryClip(ClipData.newPlainText("weixin", "{sentinel_esc}"))
    except Exception:
        pass

action.click({share_x}, {share_y})
time.sleep(0.6)
action.swipe({tray_sx}, {tray_y}, {tray_ex}, {tray_y}, 350)
time.sleep(0.2)
action.swipe({tray_sx}, {tray_y}, {tray_ex}, {tray_y}, 350)
time.sleep(0.35)
action.click({copy_x}, {copy_y})
time.sleep(0.35)

clip_text = ""
try:
    from ascript.android.system import Clipboard
    clip_text = str(Clipboard.get() or "")
except Exception as e:
    print("[~] CLIPBOARD_GET_ASCRIPT_ERR:" + repr(e))

if not clip_text:
    try:
        from android.content import Context
        from com.aojoy.airscript import Globals
        ctx = Globals.getContext()
        cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
        clip = cm.getPrimaryClip()
        if clip and clip.getItemCount() > 0:
            clip_text = str(clip.getItemAt(0).coerceToText(ctx) or "")
    except Exception as e:
        print("[~] CLIPBOARD_GET_ANDROID_ERR:" + repr(e))

print("CLIPBOARD_START")
print(clip_text)
print("CLIPBOARD_END")
print("[OK] SHARE_COPY_DONE")
"""
            out = await run_on_phone(session, code, log_sec=3)
            raw = _parse_clipboard_from_log(out.get("log", "") or "")
            link = extract_link_from_clipboard_text(raw)
            if link and sentinel not in raw:
                return link

            # 偶发剪贴板未就绪：再补 1 次读剪贴板（不再轮询 5 次 MCP）
            await asyncio.sleep(0.35)
            raw2 = await read_phone_clipboard(session)
            link2 = extract_link_from_clipboard_text(raw2)
            if link2 and sentinel not in raw2:
                return link2
            return ""

        # 创建/复用链接批次（挂工单时写入 WO-{order_no}，供链接池取证）
        batch_id, batch_name = await self._resolve_phase1_batch()
        await self._emit("info", f"已就绪链接批次: {batch_name}")

        import itertools
        link_count = 0
        hit_bottom = False
        phase1_temp_paths: list[str] = []  # 临时截图路径，任务结束后统一清理
        for index in (range(1, self.max_videos + 1) if self.max_videos > 0 else itertools.count(1)):
            if self._stopped:
                break

            await self._emit("info", f"{'─'*40}")
            limit_label = f"/{self.max_videos}" if self.max_videos > 0 else ""
            await self._emit("info", f"Phase 1 [{index}{limit_label}]: 复制链接中...")

            # 全量采集时的滑到底检测（固定条数靠 index 终止，无需检测）
            if self.max_videos == 0:
                try:
                    phase1_bottom_path = os.path.join(str(TEMP_DIR), f"phase1_bottom_{self.task_id}_{index}.png")
                    if capture_single_via_adb_execout(phase1_bottom_path):
                        phase1_temp_paths.append(phase1_bottom_path)
                        if _is_bottom_reached(phase1_bottom_path):
                            await self._emit("warning", f"Phase 1 [{index}] 已滑到底部，停止收集链接")
                            hit_bottom = True
                            break
                except Exception as e:
                    self.warning(f"Phase 1 [{index}] 底部检测异常: {e}")

            try:
                link_url = await _fast_copy_link(session, f"p1_{index}")
            except Exception as e:
                self.warning(f"Phase 1 [{index}] 复制链接失败: {e}")
                link_url = ""

            if not link_url:
                self.warning(f"Phase 1 [{index}] 未获取到链接，跳过")
                if self.max_videos == 0 or index < self.max_videos:
                    try:
                        await swipe_up(session)
                        await asyncio.sleep(1.0)
                    except Exception:
                        pass
                continue

            if "weixin.qq.com" not in link_url:
                self.warning(f"Phase 1 [{index}] 非微信链接，跳过: {link_url[:80]}")
                if self.max_videos == 0 or index < self.max_videos:
                    try:
                        await swipe_up(session)
                        await asyncio.sleep(1.0)
                    except Exception:
                        pass
                continue

            # 存库放到后台执行，立即开始滑动，不等待 DB 写入
            link_count += 1
            asyncio.create_task(self._bg_save_link(
                link_url=link_url,
                keyword=self.keyword,
                sort_order=index,
                batch_id=batch_id,
                emit_index=index,
                emit_count=link_count,
            ))

            if self.max_videos == 0 or index < self.max_videos:
                try:
                    await swipe_up(session)
                    await self._emit("info", f"Phase 1 [{index}] 已滑动到下一个视频")
                    await asyncio.sleep(1.0)
                except Exception as e:
                    self.warning(f"Phase 1 滑动失败: {e}")
                    break

        # 全量采到底：连退 4 次，便于回到可再搜状态
        if hit_bottom:
            from weixin.core.main import go_back
            await self._emit("info", "Phase 1 已滑到底，ADB 返回 4 次")
            for _ in range(4):
                await go_back(session)

        # 清理临时截图
        for p in phase1_temp_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        if phase1_temp_paths:
            await self._emit("info", f"Phase 1 已清理 {len(phase1_temp_paths)} 张临时截图")

        await self._emit("info", f"{'='*50}")
        await self._emit("success", f"Phase 1 完成：收集到 {link_count} 条链接")
        return link_count

    # ── Phase 2: 逐链接完整取证 ──

    async def run_phase2(self) -> list[dict]:
        """
        阶段二（独立入口）：从 video_links 表读取待处理链接，
        通过 ADB intent 逐条打开 → 浏览器弹窗点击"前往微信" → 完整取证

        此方法独立创建 MCP session，可被 TaskScheduler 单独调用
        """
        self._running = True
        self._stopped = False
        self._collected_records = []
        self._db_record_ids = []

        try:
            await self._emit("info", f"{'='*50}")
            await self._emit("info", f"Phase 2: 开始逐条链接完整取证")
            await self._emit("info", f"  关键词: {self.keyword}")
            await self._emit("info", f"  录屏方式: {self.capture_method}")
            await self._emit("info", f"{'='*50}")

            import weixin.core.main as _weixin_main
            import weixin.core.media_capture as _weixin_media
            _weixin_main.SCREENSHOT_DIR = str(SCREENSHOTS_DIR)
            _weixin_main.JSONS_DIR = str(JSONS_DIR)
            _weixin_media.MEDIA_DIR = RECORDINGS_DIR

            if self.device_ip:
                _weixin_main.PHONE_IP = self.device_ip
            _weixin_main.PHONE_PORT = self.device_port
            if self.device_serial:
                _weixin_main._CURRENT_DEVICE_SERIAL = self.device_serial

            def _emit_cb(msg):
                try:
                    if self._sync_log_callback:
                        self._sync_log_callback("info", msg)
                    else:
                        asyncio.create_task(self._emit("info", msg))
                except Exception:
                    pass
            _weixin_main._emit_callback = _emit_cb

            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            sp = StdioServerParameters(
                command="python", args=["-m", "ascript_mcp.local"],
                env={**os.environ},
            )
            async with stdio_client(sp) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.success("Phase 2 MCP 会话已初始化")

                    if self._stopped:
                        await self._emit("warning", "任务已被用户停止")
                        return []

                    from weixin.core.main import connect_device_auto_v2
                    if not await connect_device_auto_v2(session):
                        self.error("Phase 2 设备连接失败")
                        raise RuntimeError("Phase 2 设备连接失败")
                    self.success("Phase 2 设备已连接")

                    if self._stopped:
                        await self._emit("warning", "任务已被用户停止")
                        return []

                    return await self._run_phase2(session, _emit_cb)

        except Exception as e:
            msg = _unwrap_group(e)
            self.error(f"Phase 2 异常: {msg}")
            raise
        finally:
            self._running = False

    async def _run_phase2(self, session, _emit_cb) -> list[dict]:
        """阶段二核心逻辑：读取链接 → 逐条 intent 打开 → 完整取证"""
        from config import INTENT_POPUP_WAIT_SECONDS, INTENT_WECHAT_OPEN_WAIT_SECONDS

        # 读取尚未采集的链接，并统计跳过已采数量
        total_links, links = await self._get_task_links_split()
        skipped = max(0, total_links - len(links))
        if not links:
            await self._emit("warning", "Phase 2: 没有待处理的链接")
            return []

        await self._emit(
            "info",
            f"Phase 2 断点续采：跳过已采 {skipped} 条，继续 {len(links)} 条"
            if skipped
            else f"Phase 2：跳过已采 0 条，共 {len(links)} 条",
        )

        import weixin.core.collector as _collector
        import weixin.core.navigator as _navigator
        _collector._emit_callback = _emit_cb
        _navigator._emit_callback = _emit_cb

        from weixin.core.main import (
            go_home, open_video_via_intent, click_goto_weixin_button,
            build_current_video_candidate, now_iso, attach_recording_media,
        )
        from weixin.core.collector import collect_current_video
        from weixin.core.media_capture import start_capture_session, stop_capture_session
        from weixin.core.store import save_record

        collected_count = 0

        def _discard_incomplete(slug: str = "", segment=None) -> None:
            from engine.orphan_media_cleanup import cleanup_slug_media
            from weixin.core.media_capture import stop_capture_session

            seg_path = ""
            if segment is not None:
                try:
                    stop_capture_session(segment)
                except Exception:
                    pass
                try:
                    seg_path = str(getattr(segment, "local_path", "") or "")
                except Exception:
                    seg_path = ""
            n = cleanup_slug_media(slug, seg_path or None)
            if n:
                print(f"[phase2] 已清除中断半截文件 {n} 个 slug={slug}")

        for idx, link in enumerate(links, 1):
            if self._stopped:
                await self._emit("warning", "Phase 2 已被用户停止")
                break

            await self._emit("info", f"{'─'*40}")
            await self._emit("info", f"Phase 2 [{idx}/{len(links)}]: {link.link_url[:60]}")

            link_url = link.link_url
            current_slug = ""
            segment = None
            marked = False

            # 检测是否微信链接
            if "weixin.qq.com" not in (link_url or ""):
                self.warning(f"Phase 2 [{idx}] 非微信链接，跳过")
                continue

            try:
                # 1. 回到桌面
                await go_home(session)

                # 2. Intent 打开链接
                ok = await open_video_via_intent(session, link_url)
                if not ok:
                    self.warning(f"Phase 2 [{idx}] intent 发送失败")
                    continue

                # 3. 等待浏览器弹窗渲染
                await self._emit("info", f"Phase 2 [{idx}] 等待弹窗渲染 ({INTENT_POPUP_WAIT_SECONDS}s)...")
                await asyncio.sleep(INTENT_POPUP_WAIT_SECONDS)
                if self._stopped:
                    break

                # 4. 截图 + 豆包识别 + 点击"前往微信"
                await click_goto_weixin_button(session, f"p2_{idx}")

                # 5. 等待微信打开视频
                await self._emit("info", f"Phase 2 [{idx}] 等待微信打开视频 ({INTENT_WECHAT_OPEN_WAIT_SECONDS}s)...")
                await asyncio.sleep(INTENT_WECHAT_OPEN_WAIT_SECONDS)
                if self._stopped:
                    break

                # 6. 构建候选（用链接自己的剧名，支持多剧合并）
                link_kw = link.keyword or self.keyword
                candidate = await build_current_video_candidate(session, link_kw, idx)
                import hashlib
                if not candidate.get("fingerprint"):
                    candidate["fingerprint"] = hashlib.md5(link_url.encode("utf-8")).hexdigest()
                fp = str(candidate.get("fingerprint") or "")
                current_slug = f"{fp[:10]}_{idx}"

                # 7. 开始录屏
                try:
                    segment = start_capture_session(
                        method=self.capture_method,
                        prefer_scrcpy=self.prefer_scrcpy,
                        device_serial=self.device_serial,
                    )
                    await self._emit("info", f"Phase 2 [{idx}] 录屏已开始: {segment.local_path}")
                except Exception as e:
                    self.error(f"Phase 2 [{idx}] 录屏启动失败: {e}")
                    _discard_incomplete(current_slug, None)
                    continue

                # 8. 完整证据采集（逐链接模式：不复制链接、不检测底部）
                try:
                    record = await collect_current_video(
                        session, link_kw, candidate, set(),
                        skip_copy_link=True, skip_bottom_check=True,
                    )
                    record.video_info["video_link"] = link_url
                    await self._emit("info", f"Phase 2 [{idx}] 证据采集完成: "
                        f"{record.video_info.get('blogger_name', '')[:20]}")
                except Exception as e:
                    self.error(f"Phase 2 [{idx}] 采集失败: {e}")
                    _discard_incomplete(current_slug, segment)
                    segment = None
                    continue

                if self._stopped:
                    _discard_incomplete(current_slug, segment)
                    segment = None
                    await self._emit("warning", "Phase 2 已被用户停止（当前条未入库，已清除半截文件）")
                    break

                # 9. 停留
                await self._emit("info", f"Phase 2 [{idx}] 停留 {self.hold_seconds}s ...")
                await self._sleep_interruptible(self.hold_seconds)

                if self._stopped:
                    _discard_incomplete(current_slug, segment)
                    segment = None
                    await self._emit("warning", "Phase 2 已被用户停止（当前条未入库，已清除半截文件）")
                    break

                # 10. 停止录屏
                seg_started = getattr(segment, "started_at", None)
                try:
                    ended_at = now_iso()
                    video_path = stop_capture_session(segment)
                    video_path = self._mute_traffic_audio_in_video(str(video_path), record, segment)
                    segment = None  # 已正常落盘，勿再当半截删
                    attach_recording_media(record, str(video_path), seg_started, ended_at)
                    self.success(f"Phase 2 [{idx}] 录屏保存: {video_path}")
                except Exception as e:
                    self.warning(f"Phase 2 [{idx}] 停止录屏异常: {e}")
                    _discard_incomplete(current_slug, segment)
                    segment = None
                    continue

                # 11. ASR
                if self.enable_asr:
                    await self._do_asr_for_record(record, _emit_cb)
                    await self._emit("info", f"Phase 2 [{idx}] ASR 完成")
                else:
                    await self._emit("info", "ASR 已禁用")

                if self._stopped:
                    _discard_incomplete(current_slug, None)
                    # 录屏已落盘但未入库：删 slug 截图 + 刚挂上的录屏路径
                    try:
                        vp = (record.media_info or {}).get("recording_video_path") or ""
                        if vp:
                            from engine.orphan_media_cleanup import cleanup_slug_media
                            cleanup_slug_media("", vp)
                    except Exception:
                        pass
                    await self._emit("warning", "Phase 2 已被用户停止（当前条未入库，已清除半截文件）")
                    break

                # 12. 保存证据
                try:
                    json_path = save_record(record)
                    self.success(f"Phase 2 [{idx}] 证据已保存: {Path(json_path).name}")
                except Exception as e:
                    self.warning(f"Phase 2 [{idx}] 保存证据异常: {e}")
                    json_path = ""

                self._collected_records.append(record)

                # 13. 写入平台数据库
                evidence_record_id = None
                if self.write_db:
                    try:
                        html_path = os.path.splitext(json_path)[0] + ".html" if json_path else ""
                        evidence_record_id = await self._save_to_platform_db(record, json_path, html_path)
                        if evidence_record_id:
                            self._db_record_ids.append(evidence_record_id)
                            await self._emit("info", f"Phase 2 [{idx}] 已写入数据库: row_id={evidence_record_id}")
                    except Exception as e:
                        self.warning(f"Phase 2 [{idx}] 写入数据库异常: {e}")

                # 14. 标记链接已采集（仅记录 evidence_record_id）
                if evidence_record_id:
                    await self._mark_link_collected(link.id, evidence_record_id)
                    marked = True
                    collected_count += 1
                    self.success(f"Phase 2 [{idx}] 完成 ({collected_count}/{len(links)})")
                else:
                    # 未入库视为中断半截，清掉本条文件以免孤儿
                    try:
                        vp = (record.media_info or {}).get("recording_video_path") or ""
                        _discard_incomplete(current_slug, None)
                        if vp:
                            from engine.orphan_media_cleanup import cleanup_slug_media
                            cleanup_slug_media("", vp)
                        if json_path:
                            jp = Path(json_path)
                            for victim in (jp, jp.with_suffix(".html")):
                                try:
                                    if victim.is_file():
                                        victim.unlink()
                                except OSError:
                                    pass
                    except Exception:
                        pass
                    self.warning(f"Phase 2 [{idx}] 未写入数据库，已清除本条半截文件")

                # 15. 回桌面准备下一条
                await go_home(session)
                await asyncio.sleep(5)

            except Exception as e:
                msg = _unwrap_group(e)
                self.error(f"Phase 2 [{idx}] 处理失败: {msg}")
                if not marked:
                    _discard_incomplete(current_slug, segment)
                    segment = None
                try:
                    await go_home(session)
                except Exception:
                    pass
                await asyncio.sleep(5)

        await self._emit("info", f"{'='*50}")
        await self._emit("success", f"Phase 2 完成：成功采集 {collected_count}/{len(links)} 条")
        if self._db_record_ids:
            await self._emit("info", f"  数据库记录: {len(self._db_record_ids)} 条")
        await self._emit("info", f"{'='*50}")

        return [r.to_dict() if hasattr(r, 'to_dict') else r for r in self._collected_records]

    # ── VideoLink 数据库操作 ──

    async def _resolve_phase1_batch(self) -> tuple[int, str]:
        """解析一阶段写入的链接批次。

        有 work_order_id 时复用/创建工单专属批次 WO-{order_no}（source=work_order），
        否则创建 collected 批次 {keyword}_{时间}。
        """
        from sqlalchemy import select
        from database import async_session
        from models import LinkBatch, WorkOrder

        if self.work_order_id:
            async with async_session() as db:
                wo = (
                    await db.execute(
                        select(WorkOrder).where(WorkOrder.id == self.work_order_id)
                    )
                ).scalar_one_or_none()
                if not wo:
                    raise RuntimeError(f"工单 #{self.work_order_id} 不存在，无法写入链接池")
                batch_name = f"WO-{wo.order_no}"
                batch = (
                    await db.execute(select(LinkBatch).where(LinkBatch.name == batch_name))
                ).scalar_one_or_none()
                if not batch:
                    batch = LinkBatch(name=batch_name, source="work_order", total_count=0)
                    db.add(batch)
                    await db.commit()
                    await db.refresh(batch)
                else:
                    if (batch.source or "") != "work_order":
                        batch.source = "work_order"
                        await db.commit()
                return batch.id, batch_name

        batch_name = f"{self.keyword}_{datetime.now().strftime('%Y-%m-%d_%H:%M')}"
        batch_id = await self._create_link_batch(batch_name, source="collected")
        return batch_id, batch_name

    async def _create_link_batch(self, name: str, source: str = "collected") -> int:
        """创建链接批次，返回 batch_id"""
        from database import async_session
        from models import LinkBatch

        async with async_session() as db:
            batch = LinkBatch(name=name, source=source, total_count=0)
            db.add(batch)
            await db.commit()
            await db.refresh(batch)
            return batch.id

    async def _bg_save_link(self, link_url: str, keyword: str = "", sort_order: int = 0, batch_id: int = None, emit_index: int = 0, emit_count: int = 0):
        """后台保存链接 + 发送日志，不阻塞主流程"""
        try:
            await self._save_video_link_to_db(link_url=link_url, keyword=keyword, sort_order=sort_order, batch_id=batch_id)
            self.success(f"Phase 1 [{emit_index}] 链接已保存: {link_url[:60]}...")
            await self._emit("info", f"已收集链接: {emit_count} 条")
        except Exception as e:
            self.warning(f"Phase 1 [{emit_index}] 存库失败: {e}")

    async def _save_video_link_to_db(self, link_url: str, keyword: str = "", sort_order: int = 0, batch_id: int = None) -> int:
        """保存单条视频链接到 video_links 表"""
        from sqlalchemy import select, update
        from database import async_session
        from models import VideoLink, LinkBatch

        async with async_session() as db:
            existing = (await db.execute(
                select(VideoLink).where(
                    VideoLink.link_url == link_url,
                    VideoLink.evidence_record_id.is_(None),
                )
            )).scalar_one_or_none()
            if existing:
                return existing.id

            link = VideoLink(
                task_id=self.task_id,
                batch_id=batch_id,
                keyword=keyword or self.keyword,
                link_url=link_url,
                sort_order=sort_order,
            )
            db.add(link)
            # 更新批次的 total_count
            if batch_id:
                await db.execute(
                    update(LinkBatch).where(LinkBatch.id == batch_id).values(
                        total_count=LinkBatch.total_count + 1
                    )
                )
            await db.commit()
            await db.refresh(link)
            return link.id

    async def _mark_link_collected(self, link_id: int, evidence_record_id: int):
        """标记链接已采集，记录关联的证据ID"""
        from datetime import datetime as dt
        from sqlalchemy import update
        from database import async_session
        from models import VideoLink

        async with async_session() as db:
            await db.execute(
                update(VideoLink).where(VideoLink.id == link_id).values(
                    evidence_record_id=evidence_record_id,
                    collected_at=dt.now(),
                )
            )
            await db.commit()

    async def _get_uncollected_links(self) -> list:
        """从数据库读取尚未采集的 VideoLink 列表（evidence_record_id 为空）"""
        _, links = await self._get_task_links_split()
        return links

    async def _get_task_links_split(self) -> tuple[int, list]:
        """返回 (任务链接总数, 未采集链接列表)。"""
        from sqlalchemy import select, func
        from database import async_session
        from models import VideoLink

        if self.task_id is None:
            raise RuntimeError("task_id 为空，无法查询待采集链接")
        async with async_session() as db:
            total = (await db.execute(
                select(func.count(VideoLink.id)).where(VideoLink.task_id == self.task_id)
            )).scalar() or 0
            result = await db.execute(
                select(VideoLink)
                .where(
                    VideoLink.task_id == self.task_id,
                    VideoLink.evidence_record_id.is_(None),
                )
                .order_by(VideoLink.sort_order)
            )
            return int(total), list(result.scalars().all())

    # ── 写入平台数据库 ──

    async def _save_to_platform_db(self, weixin_record, json_path: str = "", html_path: str = "") -> Optional[int]:
        """将 weixin 的 EvidenceRecord 保存到平台数据库
        
        自动将 weixin 输出的绝对路径转换为相对于 platform/evidence_data/ 的路径，
        以便前端通过 /files/{path} 访问。
        """
        from sqlalchemy import select
        from database import async_session
        from models import EvidenceRecord as PlatformRecord
        from config import EVIDENCE_DATA_DIR

        # 将 weixin record 的 dict 转换为平台模型字段
        d = weixin_record.to_dict() if hasattr(weixin_record, 'to_dict') else weixin_record

        def _rel_path(abs_path: str) -> str:
            """将绝对路径转为相对 EVIDENCE_DATA_DIR 的路径"""
            if not abs_path:
                return ""
            try:
                p = Path(abs_path)
                if p.is_absolute():
                    return str(p.relative_to(EVIDENCE_DATA_DIR))
                return abs_path
            except ValueError:
                return abs_path

        import json
        screenshots_raw = d.get("screenshots", []) or []
        screenshots_list = [_rel_path(s) if isinstance(s, str) else s for s in screenshots_raw]

        record = PlatformRecord(
            task_id=self.task_id or 0,
            search_keyword=d.get("search_keyword", self.keyword),
            video_identifier=d.get("candidate", {}).get("video_identifier", ""),
            fingerprint=d.get("candidate", {}).get("fingerprint", ""),
            capture_timestamp=d.get("capture_timestamp", ""),
            # 视频信息
            blogger_name=d.get("video_info", {}).get("blogger_name", ""),
            video_channel_id=d.get("video_info", {}).get("video_channel_id", ""),
            video_channel_id_raw=d.get("video_info", {}).get("video_channel_id_raw", ""),
            video_channel_id_needs_review=d.get("video_info", {}).get("video_channel_id_needs_review", False),
            title=d.get("video_info", {}).get("title", d.get("candidate", {}).get("title_text", "")),
            video_link=d.get("video_info", {}).get("video_link", ""),
            publish_time=d.get("video_info", {}).get("publish_time", d.get("candidate", {}).get("publish_time", "")),
            like_count=d.get("video_info", {}).get("like_count", ""),
            comment_count=d.get("video_info", {}).get("comment_count", ""),
            share_count=d.get("video_info", {}).get("share_count", ""),
            favorite_count=d.get("video_info", {}).get("favorite_count", ""),
            # 博主信息
            profile_name=d.get("profile_info", {}).get("name", ""),
            profile_account=d.get("profile_info", {}).get("account", ""),
            subject_type=d.get("profile_info", {}).get("subject_type", ""),
            company_full_name=d.get("profile_info", {}).get("company_full_name", ""),
            # 引流信息
            has_traffic_marker=d.get("traffic_info", {}).get("has_traffic_marker", False),
            traffic_marker_text=d.get("traffic_info", {}).get("marker_text", ""),
            traffic_video_name=d.get("traffic_info", {}).get("traffic_video_name", ""),
            target_blogger_name=d.get("traffic_info", {}).get("target_blogger_name", ""),
            target_video_channel_id=d.get("traffic_info", {}).get("target_video_channel_id", ""),
            target_video_channel_id_raw=d.get("traffic_info", {}).get("target_video_channel_id_raw", ""),
            target_company_name=d.get("traffic_info", {}).get("company_full_name", ""),
            target_company_verified_at=d.get("traffic_info", {}).get("company_verified_at", ""),
            # 媒体信息
            recording_video_path=_rel_path(d.get("media_info", {}).get("recording_video_path", "")),
            recording_audio_path=_rel_path(d.get("media_info", {}).get("recording_audio_path", "")),
            recording_duration_seconds=d.get("media_info", {}).get("recording_duration_seconds", 0),
            has_audio=d.get("media_info", {}).get("has_audio", False) or False,
            asr_text=d.get("media_info", {}).get("asr_text", ""),
            asr_model=d.get("media_info", {}).get("asr_model", ""),
            # 剧本比对
            script_match_status=d.get("media_info", {}).get("script_match", {}).get("status", "pending"),
            script_match_similarity=d.get("media_info", {}).get("script_match", {}).get("coverage",
                d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("similarity_score",
                d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("score", 0.0))),
            script_match_pinyin_score=d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("pinyin_score", 0.0),
            script_match_char_score=d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("char_score", 0.0),
            script_match_segments_matched=d.get("media_info", {}).get("script_match", {}).get("segments_matched", 0),
            script_match_segments_total=d.get("media_info", {}).get("script_match", {}).get("segments_total", 0),
            script_match_episode=d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("episode", ""),
            script_match_scene=d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("scene", ""),
            script_match_character=d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("character", ""),
            script_match_location=d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("location", ""),
            script_match_script_text=d.get("media_info", {}).get("script_match", {}).get("best_match", {}).get("script_text", d.get("media_info", {}).get("asr_text", "")[:200] or ""),
            script_match_segments_json=json.dumps(d.get("media_info", {}).get("script_match", {}).get("segments", []), ensure_ascii=False),
            # 证据文件 — 直接传入路径
            json_path=_rel_path(json_path) if json_path else "",
            html_path=_rel_path(html_path) if html_path else "",
            screenshots_json=json.dumps(screenshots_list, ensure_ascii=False),
        )

        # 计算侵权评分（与补比对共用公式）
        from engine.script_rematch import compute_infringement_from_script_match
        sm = d.get("media_info", {}).get("script_match", {}) or {}
        record.infringement_score, record.infringement_level = compute_infringement_from_script_match(sm)

        # 打印提取摘要，方便排查空字段问题
        title = d.get("video_info", {}).get("title", d.get("candidate", {}).get("title_text", ""))
        blogger = d.get("video_info", {}).get("blogger_name", "")
        ch_id = d.get("video_info", {}).get("video_channel_id", "")
        likes = d.get("video_info", {}).get("like_count", "")
        traffic = d.get("traffic_info", {}).get("has_traffic_marker", False)
        asr = d.get("media_info", {}).get("asr_text", "")
        print(f"[platform-db] 写入DB: "
              f"博主={blogger[:20] if blogger else '(空)'} "
              f"标题={title[:20] if title else '(空)'} "
              f"视频号ID={ch_id[:16] if ch_id else '(空)'} "
              f"喜欢={likes} "
              f"引流={traffic} "
              f"ASR={'有' if asr else '无'}")

        async with async_session() as session:
            # 检查侵权线索黑名单匹配
            # 匹配规则：引流博主名称匹配黑名单账号名称
            #       且 引流视频名称包含黑名单侵权作品名称（或反之）
            traffic_info = d.get("traffic_info", {}) or {}
            target_blogger = (traffic_info.get("target_blogger_name") or "").strip()
            traffic_video = (traffic_info.get("traffic_video_name") or "").strip()

            if target_blogger and traffic_video:
                from models import InfringementClue
                clues_result = await session.execute(select(InfringementClue))
                clues = clues_result.scalars().all()

                matched_clue = None
                for clue in clues:
                    # 博主名精确匹配（忽略大小写、去除空格）
                    clue_account = (clue.account_name or "").strip()
                    if clue_account.lower() != target_blogger.lower():
                        continue
                    # 视频名包含匹配（任一方包含另一方）
                    clue_work = (clue.work_name or "").strip()
                    if not clue_work:
                        continue
                    if clue_work in traffic_video or traffic_video in clue_work:
                        matched_clue = clue
                        break

                if matched_clue:
                    record.infringement_level = "高度疑似"
                    record.infringement_score = 1.0
                    reason = f"匹配到侵权线索（博主={matched_clue.account_name}"
                    if matched_clue.work_name:
                        reason += f"，作品={matched_clue.work_name}"
                    if matched_clue.our_work_name:
                        reason += f"，我方作品={matched_clue.our_work_name}"
                    reason += "）"
                    record.infringement_reason = reason
                    print(f"[platform-db] 匹配到侵权线索: {reason}")

            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id

    # ── 单条 ASR ──

    async def _do_asr_for_record(self, record, emit_cb=None):
        """录屏结束后立即对单条视频执行 ASR + 剧本比对（仅跑 pipeline，不写库）"""
        wav = record.media_info.get("recording_audio_path") if hasattr(record, 'media_info') else None
        if not wav:
            return

        vid = record.candidate.get("video_identifier", "") if record.candidate else ""
        try:
            _cb = emit_cb
            def _run():
                import weixin.asr.xunfei as _xf
                import weixin.asr.script_matcher as _sm
                from config import ASR_DIR
                if _cb:
                    _xf._emit_callback = _cb
                    _sm._emit_callback = _cb
                _xf.MEDIA_DIR = ASR_DIR
                from weixin.asr.pipeline import run_asr_pipeline
                run_asr_pipeline(record, str(wav), vid)

            await asyncio.to_thread(_run)
            await self._emit("info", f"ASR 完成: {vid[:16] if vid else '?'}")
        except Exception as e:
            await self._emit("warning", f"ASR 失败: {e}")

    # ── 录屏后处理 ──

    def _mute_traffic_audio_in_video(self, video_path: str, record, segment) -> str:
        """用 ffmpeg 对录屏视频中引流时间段的音频置零。

        scrcpy 的 AudioPlaybackCapture 在系统音量控制前捕获，
        系统静音无效，改为后处理音频置零。

        返回处理后的视频路径（如果处理了），否则返回原路径。
        """
        traffic_start = record.traffic_info.get("traffic_audio_mute_start")
        traffic_end = record.traffic_info.get("traffic_audio_mute_end")
        if not traffic_start or not traffic_end:
            return video_path  # 没有引流时间段，不需要处理

        try:
            recording_start_ts = datetime.fromisoformat(segment.started_at).timestamp()
        except Exception:
            return video_path  # 时间戳解析失败，跳过

        mute_start = max(0.0, traffic_start - recording_start_ts)
        mute_end = max(mute_start + 0.1, traffic_end - recording_start_ts)

        if mute_end - mute_start < 0.5:
            return video_path  # 引流时间太短，不需要处理

        import subprocess
        base, ext = os.path.splitext(str(video_path))
        output_path = f"{base}_muted{ext}"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-af", f"volume=0:enable='between(t,{mute_start:.2f},{mute_end:.2f})'",
            "-c:v", "copy",
            "-c:a", "aac",
            output_path,
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if proc.returncode == 0 and os.path.exists(output_path):
                self.info(f"引流时间段音频已置零: {mute_start:.1f}s - {mute_end:.1f}s")
                # 删除原始文件，用处理后的
                try:
                    os.remove(str(video_path))
                except OSError:
                    pass
                return output_path
            else:
                err = proc.stderr[-300:] if proc.stderr else "unknown"
                self.warning(f"ffmpeg 静音处理失败: {err}")
                return video_path
        except Exception as e:
            self.warning(f"ffmpeg 静音处理异常: {e}")
            return video_path

    # ── 任务控制 ──

    async def _sleep_interruptible(self, seconds: float, tick: float = 1.0):
        """可中断的 sleep，每 tick 秒检查一次 _stopped，收到停止信号后立即返回"""
        elapsed = 0.0
        while elapsed < seconds:
            if self._stopped:
                return
            await asyncio.sleep(min(tick, seconds - elapsed))
            elapsed += tick

    def stop(self):
        """停止采集"""
        self._stopped = True
        self._running = False
        print("[collector] 收到停止信号")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_records(self) -> list[dict]:
        return [r.to_dict() if hasattr(r, 'to_dict') else r for r in self._collected_records]

    def get_db_record_ids(self) -> list[int]:
        return self._db_record_ids
