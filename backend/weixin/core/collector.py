"""Evidence collection from an opened Weixin video page."""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime

import cv2
import numpy as np

from weixin.core.main import SCREENSHOT_DIR, _adb_args, find_adb, run_on_phone, scale_point, scale_rect, scale_y
from weixin.core.media_capture import extract_audio, probe_audio
from weixin.db.models import EvidenceRecord
from weixin.utils.text_quality import analyze_video_channel_id

import builtins as _builtins

_emit_callback = None


def _log(*args, **kwargs):
    """同 print 并可选推送到平台前端。"""
    msg = " ".join(str(a) for a in args)
    _builtins.print(msg, **kwargs)
    if _emit_callback and msg:
        # 只转发日志类消息，过滤协议数据
        if msg.startswith(("[", "  [", "[OK]")) and not msg.startswith(
            ("OCR_START", "OCR_END", "CLIPBOARD_START", "CLIPBOARD_END")
        ):
            try:
                _emit_callback(msg)
            except Exception:
                pass


# 替换本模块内所有 print 调用为 _log
print = _log



DEFAULT_RECORD_SECONDS = int(os.environ.get("PLATFORM_RECORD_SECONDS", "90"))

SHARE_BUTTON_X = 746
SHARE_BUTTON_Y = 2153
SHARE_TRAY_SWIPE_START_X = 880
SHARE_TRAY_SWIPE_END_X = 140
SHARE_TRAY_Y = 1910
COPY_LINK_X = 950
COPY_LINK_Y = 1900
CLIPBOARD_POPUP_CLOSE_X = 281
CLIPBOARD_POPUP_CLOSE_Y = 2062

TRAFFIC_MARKER_X = 192
TRAFFIC_MARKER_Y = 1693
TRAFFIC_MARKER_LEFT = 40
TRAFFIC_MARKER_TOP = 1640
TRAFFIC_MARKER_RIGHT = 675
TRAFFIC_MARKER_BOTTOM = 1872
TRAFFIC_FIRST_EPISODE_X = 130
TRAFFIC_FIRST_EPISODE_Y = 1342
TRAFFIC_AVATAR_X = 140
TRAFFIC_AVATAR_Y = 2140
TRAFFIC_MORE_BUTTON_X = 975
TRAFFIC_MORE_BUTTON_Y = 834
TRAFFIC_MORE_INFO_X = 517
TRAFFIC_MORE_INFO_Y = 2063

AUTHOR_AVATAR_X = 140
AUTHOR_AVATAR_Y = 2140
AUTHOR_MORE_BUTTON_X = 970
AUTHOR_MORE_BUTTON_Y = 835
AUTHOR_MORE_INFO_X = 540
AUTHOR_MORE_INFO_Y = 2050
AUTHOR_CARD_NAME_LEFT = 310
AUTHOR_CARD_NAME_TOP = 735
AUTHOR_CARD_NAME_RIGHT = 790
AUTHOR_CARD_NAME_BOTTOM = 885
AUTHOR_NAME_COPY_POPUP_OFFSET_Y = 120
AUTHOR_NAME_LONG_PRESS_DURATION_MS = 700

_LOCAL_PADDLE_OCR = None
_LOCAL_OCR_WORKER = None

MIN_FULL_SCREENSHOT_BYTES = int(os.environ.get("PLATFORM_MIN_SCREENSHOT_BYTES", "4096"))
PADDLEX_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".paddlex-cache")
OCR_WORKER_PATH = os.path.join(os.path.dirname(__file__), "ocr_worker.py")
OCR_WORKER_TIMEOUT_SECONDS = float(os.environ.get("PLATFORM_OCR_WORKER_TIMEOUT_SECONDS", "120") or "120")


def configure_paddle_runtime_env() -> None:
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["PADDLE_PDX_CACHE_HOME"] = PADDLEX_CACHE_DIR
    os.environ["FLAGS_enable_pir_api"] = "0"
    os.environ["FLAGS_json_format_model"] = "0"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
    os.environ["PADDLE_PDX_DISABLE_MKLDNN_MODEL_BL"] = "True"
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["FLAGS_use_onednn"] = "0"
    os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")


configure_paddle_runtime_env()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def realtime_ocr_enabled() -> bool:
    return _env_bool("WEIXIN_REALTIME_OCR", False)


def realtime_traffic_ocr_enabled() -> bool:
    return _env_bool("WEIXIN_REALTIME_TRAFFIC_OCR", True)


def _is_bottom_reached(image_path: str) -> bool:
    """用 PaddleOCR 识别图片底部区域是否有文字，无文字则认为已滑到底。

    底部区域 (0,1940)-(1080,2400)（按 1080x2400 基准等比缩放）。
    正常视频播放页底部一定有博主名/标题/点赞数等 UI 文字；
    滑到底后无新视频加载，底部无文字。
    """
    img = cv2.imread(image_path)
    if img is None:
        return False
    h, w = img.shape[:2]
    top = int(1940 * h / 2400)
    bottom = int(2400 * h / 2400)
    crop = img[top:bottom, 0:w]
    crop_path = image_path.replace(".png", "_bottom.png")
    cv2.imwrite(crop_path, crop)
    del img
    items = local_ocr_image(crop_path)
    try:
        os.remove(crop_path)
    except OSError:
        pass
    reached = len(items) == 0
    if reached:
        print("[取证] 底部区域未识别到文字，判定已滑到底")
    else:
        texts = [it.get("text", "") for it in items if isinstance(it, dict)]
        print(f"[取证] 底部检测到文字，未到底: {texts}")
    return reached


async def collect_current_video(session, keyword, candidate_dict, seen, recording_video_path: str = "", skip_copy_link: bool = False, skip_bottom_check: bool = False):
    """Collect one complete evidence record from the current playback page."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    idx = candidate_dict.get("_index", 0)
    slug = f"{candidate_dict.get('fingerprint', ts)[:10]}_{idx}"
    capture_time = _now_iso()
    realtime_ocr = realtime_ocr_enabled()

    record = EvidenceRecord(
        search_keyword=keyword,
        capture_time=capture_time,
        capture_timestamp=capture_time,
        candidate=candidate_dict,
    )

    if recording_video_path:
        video_path = recording_video_path
        record.media_info["recording_video_path"] = str(video_path)
        has_audio = probe_audio(video_path)
        record.media_info["has_audio"] = has_audio
        if has_audio:
            wav_path = extract_audio(video_path)
            if wav_path:
                record.media_info["recording_audio_path"] = str(wav_path)
                # --- ASR 延后到全部采集结束后统一触发 ---
                from weixin.core.store import build_video_identifier
                vid = build_video_identifier(record.to_dict())
                record.candidate["video_identifier"] = vid
        print(f"[取证] 使用预录视频: {video_path} 有音频={has_audio}")

    print("[取证] 截取视频播放页...")
    play_path = os.path.join(SCREENSHOT_DIR, f"play_{slug}_0.png")
    play_ocr = []
    if await capture_single_with_adb_fallback(session, play_path, f"play_{slug}"):
        record.screenshots.append(play_path)
        # 检测是否已滑到底（仅搜索滑动模式需要，逐链接模式跳过）
        if not skip_bottom_check and _is_bottom_reached(play_path):
            record.video_info["bottom_reached"] = True
            print("[取证] 已滑到底部，跳过后续采集步骤")
            return record
        if realtime_ocr:
            # 先尝试豆包视觉模型提取结构化字段
            from weixin.core.doubao_vision import extract_video_fields_from_play
            doubao_fields = extract_video_fields_from_play(play_path)
            if doubao_fields:
                _apply_doubao_video_fields(record.video_info, doubao_fields)
                # 豆包成功时不做 PaddleOCR 字段提取，raw_ocr 留空
                print("[取证] 播放页字段已由豆包提取，跳过 PaddleOCR 字段解析")
            else:
                # 豆包失败 → 回退 PaddleOCR
                play_ocr = local_ocr_image(play_path)
                print(f"[OCR] 播放页识别到 {len(play_ocr)} 条文本（PaddleOCR 兜底）")
                record.video_info["raw_ocr"] = play_ocr
                fill_video_fields_from_ocr(record.video_info, play_ocr)
        else:
            print("[OCR] 播放页 OCR 延后到离线批量处理")

    print("[取证] 检查是否存在引流标记...")
    await collect_traffic_info(session, record, slug, play_ocr)

    print("[取证] 打开博主资料卡...")
    await open_author_profile_card(session)
    await capture_author_profile_card(session, record, slug, do_ocr=realtime_ocr)

    print("[取证] 打开博主更多信息页...")
    await open_author_more_info_from_card(session)
    await asyncio.sleep(1.5)

    profile_path = os.path.join(SCREENSHOT_DIR, f"profile_info_{slug}_0.png")
    if await capture_single_with_adb_fallback(session, profile_path, f"profile_info_{slug}"):
        record.screenshots.append(profile_path)
        if realtime_ocr:
            # 先尝试豆包视觉模型提取博主信息页字段
            from weixin.core.doubao_vision import extract_profile_info
            doubao_profile = extract_profile_info(profile_path)
            if doubao_profile:
                _apply_doubao_profile_fields(record.profile_info, record.video_info, doubao_profile)
                if not record.profile_info.get("name"):
                    record.profile_info["name"] = record.video_info.get("blogger_name", "")
                print("[取证] 博主信息页字段已由豆包提取，跳过 PaddleOCR 字段解析")
            else:
                # 豆包失败 → 回退 PaddleOCR
                profile_ocr = local_ocr_image(profile_path)
                print(f"[OCR] 博主信息页识别到 {len(profile_ocr)} 条文本（PaddleOCR 兜底）")
                record.profile_info["raw_ocr"] = profile_ocr
                fill_profile_fields_from_ocr(record.profile_info, profile_ocr)
                if not record.profile_info.get("name"):
                    record.profile_info["name"] = record.video_info.get("blogger_name", "")
                fill_video_channel_id_from_profile(record.video_info, record.profile_info)
        else:
            print("[OCR] 博主信息页 OCR 延后到离线批量处理")

    fp = candidate_dict.get("fingerprint", "")
    if fp:
        seen.add(fp)

    await back_from_profile(session)

    if skip_copy_link:
        print("[取证] 跳过复制视频链接（Phase 2 已有链接）")
    else:
        print("[取证] 从分享面板复制视频链接...")
        record.video_info["video_link"] = await copy_video_link(session, slug)
    return record


async def capture_single_with_adb_fallback(session, path: str, tag: str) -> bool:
    if capture_single_via_adb_execout(path):
        return True
    print(f"[截图] ADB 直接截图失败，尝试远程截图: {path}")
    if capture_single_via_adb(path, tag):
        return True
    return False


def write_and_validate_screenshot(path: str, data: bytes, source: str) -> bool:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    ok, reason = validate_screenshot_file(path)
    if not ok:
        print(f"[截图] {source} 生成的图片不可用: {reason}")


        try:
            os.remove(path)
        except OSError:
            pass
        return False
    print(f"  [截图] {path} ({len(data)} 字节)")
    return True


def validate_screenshot_file(path: str, min_size: int = MIN_FULL_SCREENSHOT_BYTES) -> tuple[bool, str]:
    if not os.path.exists(path):
        return False, "file missing"
    size = os.path.getsize(path)
    if size < min_size:
        return False, f"file too small ({size} bytes)"
    img = cv2.imread(path)
    if img is None or img.size == 0:
        return False, "cv2 cannot read image"
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    std = float(gray.std())
    del img, gray  # 释放 OpenCV 图像内存
    if mean < 3.0 and std < 2.0:
        return False, f"near-black image (mean={mean:.2f}, std={std:.2f})"
    if std < 0.5:
        return False, f"nearly flat image (mean={mean:.2f}, std={std:.2f})"
    return True, "ok"


def capture_single_via_adb_execout(path: str) -> bool:
    shot = subprocess.run(
        _adb_args() + ["exec-out", "screencap", "-p"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if shot.returncode != 0 or not shot.stdout:
        err = shot.stderr.decode("utf-8", "replace").strip()
        print(f"[截图] ADB 直接截图异常: {err}")
        return False
    return write_and_validate_screenshot(path, shot.stdout, "adb exec-out screencap")


def capture_single_via_adb(path: str, tag: str) -> bool:
    adb_prefix = _adb_args()
    remote_path = f"/sdcard/{tag}.png"
    os.makedirs(os.path.dirname(path), exist_ok=True)

    shot = subprocess.run(
        adb_prefix + ["shell", "screencap", "-p", remote_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if shot.returncode != 0:
        print(f"[截图] ADB screencap 失败: {shot.stderr.strip()}")
        return False

    pull = subprocess.run(
        adb_prefix + ["pull", remote_path, path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if pull.returncode != 0:
        print(f"[截图] ADB pull 失败: {pull.stderr.strip()}")
        return False
    ok, reason = validate_screenshot_file(path)
    if not ok:
        print(f"[截图] ADB 远程截图生成的图片不可用: {reason}")
        try:
            os.remove(path)
        except OSError:
            pass
        return False
    print(f"[截图] {path}")
    return True


async def back_from_profile(session):
    """Return from author info back to the playback page."""
    from weixin.core.navigator import back

    await back(session)
    await asyncio.sleep(1.6)
    await back(session)
    await asyncio.sleep(1.6)


async def copy_video_link(session, slug: str = "") -> str:
    """Copy the current video link via a debuggable share-sheet path."""
    tag = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    sentinel = f"__WEIXIN_COPY_PENDING_{tag}__"
    await set_phone_clipboard(session, sentinel)

    await open_share_sheet_to_copy_area(session)

    # 直接使用固定坐标（1080x2400 基准，tap_copy_link_button 内部 scale_point 缩放）
    await tap_copy_link_button(session, COPY_LINK_X, COPY_LINK_Y)

    for attempt in range(1, 6):
        await asyncio.sleep(0.6)
        raw_link = await read_phone_clipboard(session)
        link = extract_link_from_clipboard_text(raw_link)
        print(f"[取证] 读取剪贴板 {attempt}/5: {raw_link!r}")
        if link and sentinel not in raw_link:
            print(f"[取证] 已复制视频链接: {link}")
            return link

    print("[取证] 复制视频链接未获取到剪贴板文本")
    return ""


async def open_share_sheet_to_copy_area(session) -> None:
    share_x, share_y = scale_point(SHARE_BUTTON_X, SHARE_BUTTON_Y)
    tray_start_x, tray_y = scale_point(SHARE_TRAY_SWIPE_START_X, SHARE_TRAY_Y)
    tray_end_x, _ = scale_point(SHARE_TRAY_SWIPE_END_X, SHARE_TRAY_Y)
    code = f"""
import time
from ascript.android import action

action.click({share_x}, {share_y})
time.sleep(1.2)
action.swipe({tray_start_x}, {tray_y}, {tray_end_x}, {tray_y}, 350)
time.sleep(0.5)
action.swipe({tray_start_x}, {tray_y}, {tray_end_x}, {tray_y}, 350)
time.sleep(0.8)
print("[OK] SHARE_SHEET_READY")
"""
    await run_on_phone(session, code, log_sec=6)


async def tap_copy_link_button(session, x: int, y: int) -> None:
    tap_x, tap_y = scale_point(x, y)
    code = f"""
import time
from ascript.android import action

action.click({tap_x}, {tap_y})
time.sleep(1.0)
print("[OK] COPY_LINK_TAPPED")
"""
    await run_on_phone(session, code, log_sec=5)


async def set_phone_clipboard(session, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    code = f"""
try:
    from ascript.android.system import Clipboard
    Clipboard.set('{escaped}')
    print("[OK] CLIPBOARD_SET_ASCRIPT")
except Exception as e:
    print("[~] CLIPBOARD_SET_ASCRIPT_ERR:" + repr(e))
    try:
        from android.content import ClipData, Context
        from com.aojoy.airscript import Globals
        ctx = Globals.getContext()
        cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
        cm.setPrimaryClip(ClipData.newPlainText("weixin", "{escaped}"))
        print("[OK] CLIPBOARD_SET_ANDROID")
    except Exception as e2:
        print("[~] CLIPBOARD_SET_ANDROID_ERR:" + repr(e2))
"""
    await run_on_phone(session, code, log_sec=4)


async def read_phone_clipboard(session) -> str:
    code = """
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
"""
    out = await run_on_phone(session, code, log_sec=4)
    log = out.get("log", "")
    start = log.find("CLIPBOARD_START")
    end = log.find("CLIPBOARD_END")
    if start < 0 or end <= start:
        return ""
    raw_text = log[start + len("CLIPBOARD_START"):end].strip()
    return strip_phone_log_wrappers(raw_text)


def extract_link_from_clipboard_text(raw_text: str) -> str:
    match = re.search(r"https?://\S+", raw_text or "")
    return match.group(0).rstrip(")]}>,.;'\"") if match else ""


def strip_phone_log_wrappers(raw_text: str) -> str:
    if not raw_text:
        return ""
    cleaned = re.sub(
        r"\[INFO\]\s*\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2}:\d{3}",
        "",
        raw_text,
    )
    cleaned = cleaned.replace("[INFO]", "")
    cleaned = "".join(line.strip() for line in cleaned.splitlines() if line.strip())
    return cleaned or raw_text.strip()


def find_copy_link_button_from_image(image_path: str, tag: str) -> tuple[int, int] | None:
    region_path = os.path.join(SCREENSHOT_DIR, f"share_copy_region_{tag}.png")
    left, top, right, bottom = scale_rect(520, 1760, 1080, 2025)
    if not crop_image_region(image_path, region_path, left, top, right, bottom):
        return None

    items = local_ocr_image(region_path)
    candidates = []
    for item in items:
        text = (item.get("text", "") or "").strip()
        if not text:
            continue
        if "复制" not in text:
            continue
        if "链接" not in text and "口令" in text:
            continue
        x = item.get("x", 0) + left
        y = item.get("y", 0) + top
        candidates.append((abs(x - COPY_LINK_X) + abs(y - COPY_LINK_Y), x, y, text))

    if not candidates:
        return None
    _, x, y, text = sorted(candidates, key=lambda item: item[0])[0]
    print(f"[取证] 复制链接 OCR 识别文本: {text}")
    return int(x), int(y)


def mute_device_media_volume() -> int:
    """[已废弃] 系统音量静音对 scrcpy 录屏无效（AudioPlaybackCapture 在音量控制前捕获）。
    保留函数签名避免外部引用报错，实际不再使用。
    """
    return 0


def restore_device_media_volume(volume: int) -> None:
    """[已废弃] 同 mute_device_media_volume，保留签名避免引用报错。"""
    pass


async def collect_traffic_info(session, record: EvidenceRecord, slug: str, play_ocr=None) -> None:
    """Open the free-series traffic entry and collect target subject info."""
    if not realtime_traffic_ocr_enabled():
        print("[引流] 实时引流 OCR 已禁用，跳过引流检测")
        return

    marker_text, region_path, marker_point = await detect_traffic_marker(session, slug)
    if region_path:
        record.screenshots.append(region_path)
    if not marker_text:
        marker_text = find_traffic_marker_text_from_items(play_ocr or [])
        if marker_text:
            print(f"[引流] 播放页 OCR 兜底识别标记: {marker_text}")

    # 没有坐标且没有文字 → 真的没引流标记
    if not marker_point and not marker_text:
        print("[引流] 播放页未发现引流标记")
        return

    record.traffic_info["has_traffic_marker"] = True
    # 颜色识别成功但 OCR 无文字时，使用默认文本
    record.traffic_info["marker_text"] = marker_text or "免费剧集"
    if marker_point:
        record.traffic_info["marker_click_x"] = marker_point[0]
        record.traffic_info["marker_click_y"] = marker_point[1]
    print(f"[引流] 发现引流标记: {record.traffic_info['marker_text']}")

    if not marker_point:
        print("[引流] 未检测到标记坐标，跳过引流详情采集")
        return

    # === 引流操作：记录时间戳，用于录屏后用 ffmpeg 对引流时间段音频置零 ===
    # scrcpy 的 AudioPlaybackCapture 在系统音量控制前捕获，系统静音无效
    # 注意：引流弹窗只是选集窗口无音频，只有点击进入引流落地页后才有视频音频
    traffic_start_ts = None
    try:
        await open_traffic_subject(session, marker_point)
        traffic_popup_path = os.path.join(SCREENSHOT_DIR, f"traffic_popup_{slug}_0.png")
        if await capture_single_with_adb_fallback(session, traffic_popup_path, f"traffic_popup_{slug}"):
            record.screenshots.append(traffic_popup_path)
            # 使用豆包视觉模型从引流弹窗截图提取引流视频名称
            from weixin.core.doubao_vision import extract_traffic_video_name_from_popup
            traffic_video_name = extract_traffic_video_name_from_popup(traffic_popup_path)
            if traffic_video_name:
                record.traffic_info["traffic_video_name"] = traffic_video_name
                print(f"[引流] 引流视频名称（豆包）: {traffic_video_name}")

        # 点击进入引流落地页后才开始播放引流视频，此处开始需要静音
        traffic_start_ts = datetime.now().timestamp()
        await open_traffic_first_episode(session)
        traffic_landing_path = os.path.join(SCREENSHOT_DIR, f"traffic_landing_{slug}_0.png")
        if await capture_single_with_adb_fallback(session, traffic_landing_path, f"traffic_landing_{slug}"):
            record.screenshots.append(traffic_landing_path)

        await open_traffic_avatar_card(session)

        traffic_page_path = os.path.join(SCREENSHOT_DIR, f"traffic_page_{slug}_0.png")
        if await capture_single_with_adb_fallback(session, traffic_page_path, f"traffic_page_{slug}"):
            record.screenshots.append(traffic_page_path)
            traffic_name_region_path = os.path.join(SCREENSHOT_DIR, f"traffic_page_name_region_{slug}.png")
            left, top, right, bottom = scale_rect(
                AUTHOR_CARD_NAME_LEFT,
                AUTHOR_CARD_NAME_TOP,
                AUTHOR_CARD_NAME_RIGHT,
                AUTHOR_CARD_NAME_BOTTOM,
            )
            if crop_image_region(
                traffic_page_path,
                traffic_name_region_path,
                left,
                top,
                right,
                bottom,
            ):
                record.screenshots.append(traffic_name_region_path)
            # 先尝试豆包视觉模型提取引流博主名
            from weixin.core.doubao_vision import extract_blogger_name_from_card
            target_name = extract_blogger_name_from_card(traffic_page_path)
            if target_name:
                print(f"[引流] 目标账号资料卡名称（豆包）: {target_name}")
            else:
                # 豆包失败 → 回退 OCR + 长按剪贴板
                print("[豆包] 引流博主名提取失败，回退 OCR + 长按剪贴板")
                target_name = await extract_author_name_with_clipboard_fallback(
                    session,
                    traffic_page_path,
                    traffic_name_region_path,
                    left,
                    top,
                    f"traffic_{slug}",
                )
            record.traffic_info["target_blogger_name"] = target_name
            if target_name:
                print(f"[引流] 目标账号资料卡名称: {target_name}")

        await open_traffic_more_info_from_avatar_card(session)

        traffic_info_path = os.path.join(SCREENSHOT_DIR, f"traffic_info_{slug}_0.png")
        if await capture_single_with_adb_fallback(session, traffic_info_path, f"traffic_info_{slug}"):
            record.screenshots.append(traffic_info_path)
            # 先尝试豆包视觉模型提取引流信息页字段
            from weixin.core.doubao_vision import extract_traffic_info
            doubao_traffic = extract_traffic_info(traffic_info_path)
            if doubao_traffic:
                _apply_doubao_traffic_fields(record.traffic_info, doubao_traffic)
                print("[取证] 引流信息页字段已由豆包提取，跳过 PaddleOCR 字段解析")
            else:
                # 豆包失败 → 回退 PaddleOCR
                info_ocr = local_ocr_image(traffic_info_path)
                print(f"[OCR] 引流信息页识别到 {len(info_ocr)} 条文本（PaddleOCR 兜底）")
                record.traffic_info["raw_ocr"] = info_ocr
                fill_traffic_fields_from_ocr(record.traffic_info, info_ocr)

        await back_from_traffic_info(session)
    finally:
        if traffic_start_ts is not None:
            traffic_end_ts = datetime.now().timestamp()
            record.traffic_info["traffic_audio_mute_start"] = traffic_start_ts
            record.traffic_info["traffic_audio_mute_end"] = traffic_end_ts
            print(f"[引流] 引流音频静音区间: {traffic_start_ts:.1f} - {traffic_end_ts:.1f}（用于后处理静音）")


async def open_author_profile_card(session) -> None:
    avatar_x, avatar_y = scale_point(AUTHOR_AVATAR_X, AUTHOR_AVATAR_Y)
    code = f"""
import time
from ascript.android import action

action.click({avatar_x}, {avatar_y})
time.sleep(1.6)
print("[OK] AUTHOR_PROFILE_CARD_OPENED")
"""
    await run_on_phone(session, code, log_sec=5)
    await asyncio.sleep(0.6)


async def open_author_more_info_from_card(session) -> None:
    more_button_x, more_button_y = scale_point(AUTHOR_MORE_BUTTON_X, AUTHOR_MORE_BUTTON_Y)
    more_info_x, more_info_y = scale_point(AUTHOR_MORE_INFO_X, AUTHOR_MORE_INFO_Y)
    code = f"""
import time
from ascript.android import action

action.click({more_button_x}, {more_button_y})
time.sleep(1.2)
action.click({more_info_x}, {more_info_y})
time.sleep(2.0)
print("[OK] AUTHOR_MORE_INFO_OPENED")
"""
    await run_on_phone(session, code, log_sec=8)
    await asyncio.sleep(0.8)


async def capture_author_profile_card(session, record: EvidenceRecord, slug: str, do_ocr: bool = True) -> None:
    card_path = os.path.join(SCREENSHOT_DIR, f"profile_card_{slug}_0.png")
    if not await capture_single_with_adb_fallback(session, card_path, f"profile_card_{slug}"):
        return

    record.screenshots.append(card_path)
    region_path = os.path.join(SCREENSHOT_DIR, f"profile_card_name_region_{slug}.png")
    left, top, right, bottom = scale_rect(
        AUTHOR_CARD_NAME_LEFT,
        AUTHOR_CARD_NAME_TOP,
        AUTHOR_CARD_NAME_RIGHT,
        AUTHOR_CARD_NAME_BOTTOM,
    )
    if crop_image_region(
        card_path,
        region_path,
        left,
        top,
        right,
        bottom,
    ):
        record.screenshots.append(region_path)

    if not do_ocr:
        print("[OCR] 博主资料卡 OCR 延后到离线批量处理")
        return

    # 先尝试豆包视觉模型提取博主名（省去 OCR + 长按剪贴板流程）
    from weixin.core.doubao_vision import extract_blogger_name_from_card
    doubao_name = extract_blogger_name_from_card(card_path)
    if doubao_name:
        record.video_info["blogger_name"] = doubao_name
        record.profile_info["name"] = doubao_name
        print(f"[博主] 资料卡博主名称（豆包）: {doubao_name}")
        return

    # 豆包失败 → 回退 OCR + 长按剪贴板
    print("[豆包] 资料卡博主名提取失败，回退 OCR + 长按剪贴板")
    blogger_name = await extract_author_name_with_clipboard_fallback(
        session,
        card_path,
        region_path,
        left,
        top,
        slug,
    )
    if blogger_name:
        record.video_info["blogger_name"] = blogger_name
        record.profile_info["name"] = blogger_name
        print(f"[博主] 资料卡博主名称: {blogger_name}")
    else:
        print("[博主] 资料卡未找到博主名称")


async def extract_author_name_with_clipboard_fallback(
    session,
    card_path: str,
    region_path: str,
    region_left: int,
    region_top: int,
    tag: str = "",
) -> str:
    candidate = find_best_author_name_candidate_from_image(
        card_path,
        region_path,
        region_left,
        region_top,
    )
    if candidate and candidate.get("trusted"):
        return candidate["text"]

    if candidate and candidate.get("screen_x") is not None and candidate.get("screen_y") is not None:
        copied_name = await copy_author_name_via_long_press(
            session,
            int(candidate["screen_x"]),
            int(candidate["screen_y"]),
            tag=tag,
        )
        if copied_name:
            print(f"[博主] 长按复制博主名称: {copied_name}")
            return copied_name
        # 长按失败，回退使用 OCR 候选（但过滤链接）
        if candidate.get("text") and not is_likely_link(str(candidate.get("text", ""))):
            print(f"[博主] 长按失败，回退使用 OCR 候选: {candidate['text']}")
            return candidate["text"]

    return ""


def find_best_author_name_candidate_from_image(
    card_path: str,
    region_path: str = "",
    region_left: int = 0,
    region_top: int = 0,
) -> dict | None:
    # 只从专用裁剪区获取，不去整图回退（整图包含关注按钮、链接等干扰文本）
    if region_path and os.path.exists(region_path):
        region_items = local_ocr_image(region_path)
        print(f"[OCR] 博主名称裁剪区识别到 {len(region_items)} 条文本")
        candidate = extract_author_name_from_card_items(
            region_items,
            cropped=True,
            offset_x=region_left,
            offset_y=region_top,
        )
        if candidate:
            return candidate
        print("[博主] 裁剪区未识别到可信博主名称，放弃整图回退")
    return None


def extract_author_name_from_card_items(
    ocr_items,
    cropped: bool = False,
    offset_x: int = 0,
    offset_y: int = 0,
) -> dict | None:
    items = ocr_items if isinstance(ocr_items, list) else []
    visible_items = []
    for item in items:
        text = normalize_author_candidate_text(item.get("text", ""))
        if not text:
            continue
        x = int(item.get("x", 0))
        y = int(item.get("y", 0))
        if not cropped:
            if not (
                AUTHOR_CARD_NAME_LEFT <= x <= AUTHOR_CARD_NAME_RIGHT
                and AUTHOR_CARD_NAME_TOP <= y <= AUTHOR_CARD_NAME_BOTTOM
            ):
                continue
        visible_items.append(
            {
                "text": text,
                "x": x,
                "y": y,
                "w": int(item.get("w", 0) or 0),
                "h": int(item.get("h", 0) or 0),
            }
        )

    row_candidates = []
    for row in group_ocr_items_by_row(visible_items):
        merged_text = normalize_author_candidate_text("".join(item.get("text", "") for item in row))
        if not merged_text or is_author_ui_noise(merged_text):
            continue
        center_x = int(sum(item.get("x", 0) for item in row) / len(row))
        center_y = int(sum(item.get("y", 0) for item in row) / len(row))
        company_like = is_company_like_name(merged_text)
        trusted = is_probable_author_name(merged_text) and not company_like
        anchor_x = 240 if cropped else 550
        anchor_y = 70 if cropped else 808
        score = (
            (120 if trusted else 0)
            + (40 if not company_like else -20)
            - abs(center_y - anchor_y)
            - abs(center_x - anchor_x) / 12
            - max(0, len(merged_text) - 20) * 2
        )
        row_candidates.append(
            {
                "text": merged_text,
                "trusted": trusted,
                "company_like": company_like,
                "screen_x": center_x + offset_x,
                "screen_y": center_y + offset_y,
                "score": score,
            }
        )

    if not row_candidates:
        return None
    row_candidates.sort(key=lambda item: item["score"], reverse=True)
    return row_candidates[0]


def is_likely_link(text: str) -> bool:
    """判断文本是否像链接，避免 OCR 把链接当成博主名称。"""
    return bool(re.search(r"https?://|weixin\.qq\.com|chuangkit\.com", text))


def is_probable_author_name(text: str) -> bool:
    if not text or len(text) < 2 or len(text) > 32:
        return False
    ignored_tokens = (
        "关注",
        "私信",
        "视频号",
        "账号",
        "企业",
        "公司",
        "有限",
        "原创",
        "主页",
        "剧集",
        "作品",
        "粉丝",
        "获赞",
        "评论",
        "IP",
        "归属地",
        "资料",
        "搜索",
        "更多",
    )
    if any(token in text for token in ignored_tokens):
        return False
    return bool(re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", text))


def normalize_author_candidate_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text or "")
    compact = compact.strip("：:;；,，|/\\-_.。·•")
    compact = re.sub(r"^[品•·.。]+", "", compact)
    compact = re.sub(r"[•·.。]+$", "", compact)
    return compact


def is_author_ui_noise(text: str) -> bool:
    if not text:
        return True
    noise_tokens = (
        "关注",
        "私信",
        "视频号",
        "账号",
        "主页",
        "评论",
        "获赞",
        "资料",
        "更多",
        "搜索",
        "归属地",
    )
    return any(token in text for token in noise_tokens)


def is_company_like_name(text: str) -> bool:
    if not text:
        return False
    company_tokens = (
        "有限公司",
        "有限责任公司",
        "集团",
        "传媒",
        "科技",
        "文化",
        "商贸",
        "工作室",
        "企业",
        "所属",
    )
    return any(token in text for token in company_tokens)


def extract_author_name_from_clipboard_text(raw_text: str) -> str:
    text = normalize_author_candidate_text(strip_phone_log_wrappers(raw_text))
    if not text:
        return ""
    if is_likely_link(text):
        return ""
    if is_author_ui_noise(text):
        return ""
    if is_company_like_name(text):
        return ""
    if not re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", text):
        return ""
    return text


async def copy_author_name_via_long_press(session, press_x: int, press_y: int, tag: str = "") -> str:
    """通过 ascript 在手机上执行「长按 → 点复制 → 读剪贴板」获取博主名称。

    完全在手机端执行，不使用 adb input 命令（adb input swipe 在某些设备上不会触发长按菜单）。
    用 node.Selector 查找"复制"按钮，不依赖固定坐标偏移。
    """
    sentinel = f"__WEIXIN_AUTHOR_COPY_PENDING_{tag or datetime.now().strftime('%Y%m%d_%H%M%S')}__"
    escaped = sentinel.replace("\\", "\\\\").replace("'", "\\'")

    code = f"""
import time
from ascript.android import action, node
from ascript.android.system import Clipboard

# 1. 设哨兵值
Clipboard.set('{escaped}')
time.sleep(0.3)

# 2. 长按博主名称位置（duration 800ms 模拟长按）
action.swipe({press_x}, {press_y}, {press_x}, {press_y}, 800)
time.sleep(1.0)

# 3. 用 node.Selector 查找"复制"按钮（比固定坐标可靠得多）
copied = False
for btn_text in ["复制", "拷贝"]:
    btn = node.Selector().text(btn_text).find()
    if btn:
        btn.click()
        copied = True
        time.sleep(0.6)
        break

if not copied:
    # 兜底：在长按位置上方 120px 尝试点击（弹出菜单通常在手指上方）
    action.click({press_x}, max(1, {press_y} - 120))
    time.sleep(0.6)

# 4. 读剪贴板，过滤哨兵
result = ""
try:
    result = str(Clipboard.get() or "")
except:
    pass

if result and '{escaped}' not in result:
    print("COPY_OK:" + result)
else:
    print("COPY_FAIL:" + (result[:50] if result else "empty"))
"""
    out = await run_on_phone(session, code, log_sec=8)
    log = out.get("log", "")

    for line in log.splitlines():
        if line.startswith("COPY_OK:"):
            text = line[len("COPY_OK:"):].strip()
            filtered = extract_author_name_from_clipboard_text(text)
            if filtered:
                print(f"[博主] 长按复制博主名称: {filtered}")
                return filtered
            else:
                print(f"[博主] 长按复制内容被过滤: {text[:60]!r}")
        elif line.startswith("COPY_FAIL:"):
            print(f"[博主] 长按复制失败: {line[len('COPY_FAIL:'):]}")

    return ""


async def detect_traffic_marker(session, slug: str) -> tuple[str, str, tuple[int, int] | None]:
    """Detect the free-series marker and return click position."""
    screen_path = os.path.join(SCREENSHOT_DIR, f"traffic_marker_full_{slug}.png")
    if not await capture_single_with_adb_fallback(session, screen_path, f"traffic_marker_{slug}"):
        return "", "", None

    # ── 颜色过滤定位（颜色+尺寸双重过滤，精度足够，不再 OCR 验证）
    candidates = find_traffic_marker_candidates_by_color(screen_path)
    if candidates:
        best_point = candidates[0]
        print(f"[引流] 颜色识别定位标记: 点击位置={best_point}（共 {len(candidates)} 个候选）")
        return "", screen_path, best_point

    # ── 固定区域 OCR 兜底（颜色未找到时使用）
    region_path = os.path.join(SCREENSHOT_DIR, f"traffic_marker_region_{slug}.png")
    left, top, right, bottom = scale_rect(
        TRAFFIC_MARKER_LEFT,
        TRAFFIC_MARKER_TOP,
        TRAFFIC_MARKER_RIGHT,
        TRAFFIC_MARKER_BOTTOM,
    )
    if not crop_image_region(
        screen_path,
        region_path,
        left,
        top,
        right,
        bottom,
    ):
        return "", "", None

    marker_text, marker_point = find_traffic_marker_target_local(region_path, left, top)
    print(f"[OCR] 引流标记区域文本={marker_text!r}")
    if marker_text and marker_point:
        # X 用固定值更稳定，Y 用 OCR 检测值
        fixed_x, _ = scale_point(TRAFFIC_MARKER_X, TRAFFIC_MARKER_Y)
        marker_point = (fixed_x, marker_point[1])
        print(f"[引流] 区域 OCR 识别标记: {marker_text} 点击位置={marker_point}")
    return marker_text, region_path, marker_point


def find_traffic_marker_candidates_by_color(image_path: str) -> list[tuple[int, int]]:
    """通过 HSV 颜色过滤定位引流标记的橙色/黄色播放图标

    引流标记左侧有一个橙色/黄色播放图标（▶），大小固定（约屏幕宽度的 3%）。
    通过颜色 + 尺寸双重过滤精确定位，不受视频字幕干扰。

    Returns:
        按评分排序的候选坐标列表（最佳在前），空列表表示无候选
    """
    img = cv2.imread(image_path)
    if img is None:
        return []
    h, w = img.shape[:2]

    # 先裁剪扩大区域，再颜色过滤：减少视频区域黄色干扰，避免漏检
    # 原始引流标记裁剪图区域 (40,1640)-(675,1872) 太窄，Y 偏移会漏检
    # 扩大区域：X 0-65%宽，Y 62.5%-83.3%高，覆盖标记可能出现的范围
    crop_left = 0
    crop_top = int(h * 0.625)
    crop_right = min(w, int(w * 0.65))
    crop_bottom = int(h * 0.833)
    cropped = img[crop_top:crop_bottom, crop_left:crop_right]
    del img

    hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)
    del cropped

    # 橙色 + 黄色范围
    lower_orange = np.array([8, 80, 80])
    upper_orange = np.array([25, 255, 255])
    lower_yellow = np.array([25, 80, 80])
    upper_yellow = np.array([40, 255, 255])
    mask = cv2.bitwise_or(
        cv2.inRange(hsv, lower_orange, upper_orange),
        cv2.inRange(hsv, lower_yellow, upper_yellow),
    )
    del hsv

    # 形态学操作去噪
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 图标大小固定：基准 1080 宽度下约 32x40，按屏幕宽度等比缩放
    # 预期宽度 = w * 0.03，预期高度 = w * 0.037（图标略高）
    expected_size = w * 0.033  # 约 36px @ 1080
    expected_area = expected_size * expected_size  # 约 1296
    min_area = expected_area * 0.3   # 允许小到 30%（约 389）
    max_area = expected_area * 2.5   # 允许大到 250%（约 3240）
    min_dim = expected_size * 0.4    # 单边最小 40%
    max_dim = expected_size * 2.0    # 单边最大 200%

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        x, y, rw, rh = cv2.boundingRect(cnt)
        # 单边尺寸过滤（防止细长条误判）
        if rw < min_dim or rw > max_dim or rh < min_dim or rh > max_dim:
            continue
        # 裁剪区域内的坐标转换回全屏坐标
        full_x = x + crop_left
        full_y = y + crop_top
        cx = full_x + rw // 2
        cy = full_y + rh // 2
        ratio = rw / rh if rh > 0 else 0
        # 评分：宽高比接近 0.8（图标略高）+ 面积接近预期
        area_ratio = area / expected_area
        score = (
            abs(ratio - 0.8) * 3           # 宽高比越接近 0.8 越好
            + abs(area_ratio - 1.0) * 2    # 面积越接近预期越好
        )
        candidates.append({
            "cx": cx, "cy": cy,
            "area": area,
            "ratio": ratio,
            "score": score,
        })

    del mask, contours

    if not candidates:
        return []

    # 按评分升序（越小越好）
    candidates.sort(key=lambda c: c["score"])
    return [(c["cx"], c["cy"]) for c in candidates]


def read_traffic_marker_text_near(image_path: str, point: tuple[int, int]) -> str:
    """在指定位置附近做 OCR，读取引流标记文本

    从图标位置向右扩展裁剪区域，读取整条标记文字。
    用 is_traffic_marker_text 验证，确保是"免费剧集"类文字。
    """
    img = cv2.imread(image_path)
    if img is None:
        return ""
    h, w = img.shape[:2]
    px, py = point

    # 从图标位置向右扩展裁剪区域，读取整条标记文字
    left = max(0, px - 20)
    top = max(0, py - 60)
    right = min(w, px + 600)
    bottom = min(h, py + 60)

    region = img[top:bottom, left:right]
    del img
    if region.size == 0:
        return ""

    temp_path = image_path.replace(".png", "_color_region.png")
    cv2.imwrite(temp_path, region)
    del region

    items = local_ocr_image(temp_path)
    # 合并所有文本，用 is_traffic_marker_text 验证
    texts = [(item.get("text", "") or "").strip() for item in items or []]
    merged = "".join(texts)
    if is_traffic_marker_text(merged):
        return merged
    # 也检查单条
    for t in texts:
        if is_traffic_marker_text(t):
            return t
    return ""


def crop_image_region(src_path: str, dst_path: str, left: int, top: int, right: int, bottom: int) -> bool:
    img = cv2.imread(src_path)
    if img is None:
        return False
    height, width = img.shape[:2]
    left = max(0, min(left, width - 1))
    top = max(0, min(top, height - 1))
    right = max(left + 1, min(right, width))
    bottom = max(top + 1, min(bottom, height))
    region = img[top:bottom, left:right]
    del img  # 释放原图内存
    if region.size == 0:
        return False
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    ok = bool(cv2.imwrite(dst_path, region))
    del region  # 释放裁剪区域内存
    if ok:
        print(f"[截图] {dst_path}")
    return ok


def local_ocr_worker_enabled() -> bool:
    mode = os.environ.get("WEIXIN_OCR_MODE", "worker").strip().lower()
    return mode not in ("inprocess", "direct", "legacy", "off", "0", "false")


def stop_local_ocr_worker() -> None:
    global _LOCAL_OCR_WORKER
    proc = _LOCAL_OCR_WORKER
    _LOCAL_OCR_WORKER = None
    if proc is None:
        return
    try:
        if proc.stdin:
            proc.stdin.close()
    except Exception:
        pass
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


atexit.register(stop_local_ocr_worker)


def get_local_ocr_worker():
    global _LOCAL_OCR_WORKER
    if _LOCAL_OCR_WORKER is not None and _LOCAL_OCR_WORKER.poll() is None:
        return _LOCAL_OCR_WORKER
    if _LOCAL_OCR_WORKER is not None:
        stop_local_ocr_worker()

    _LOCAL_OCR_WORKER = subprocess.Popen(
        [sys.executable, OCR_WORKER_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    return _LOCAL_OCR_WORKER


def read_ocr_worker_line(proc, timeout_seconds: float) -> str:
    if proc.stdout is None:
        raise RuntimeError("OCR worker stdout is not available")
    result_queue: queue.Queue[str] = queue.Queue(maxsize=1)

    def _reader() -> None:
        try:
            result_queue.put(proc.stdout.readline())
        except Exception:
            result_queue.put("")

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    try:
        return result_queue.get(timeout=timeout_seconds)
    except queue.Empty as exc:
        raise TimeoutError(f"OCR worker timed out after {timeout_seconds:.1f}s") from exc


def local_ocr_image_via_worker(image_path: str) -> list[dict] | None:
    if not local_ocr_worker_enabled():
        return None

    payload = json.dumps({"image_path": image_path}, ensure_ascii=False)
    for attempt in range(2):
        try:
            proc = get_local_ocr_worker()
            if proc.stdin is None or proc.stdout is None:
                raise RuntimeError("OCR worker pipes are not available")
            proc.stdin.write(payload + "\n")
            proc.stdin.flush()
            line = read_ocr_worker_line(proc, OCR_WORKER_TIMEOUT_SECONDS)
            if not line:
                # 尝试读取 stderr 诊断启动失败原因
                stderr_info = ""
                if proc.stderr:
                    try:
                        import select as _select
                        while True:
                            ready, _, _ = _select.select([proc.stderr], [], [], 0.1)
                            if not ready:
                                break
                            chunk = proc.stderr.readline()
                            if chunk:
                                stderr_info += chunk
                            else:
                                break
                    except Exception:
                        pass
                detail = f"stderr: {stderr_info.strip()[:300]}" if stderr_info.strip() else "no stderr output"
                raise RuntimeError(f"OCR worker closed without response ({detail})")
            response = json.loads(line)
            if response.get("restart"):
                print(
                    "[ocr] worker restart requested "
                    f"jobs={response.get('jobs')} memory_mb={response.get('memory_mb')}"
                )
                stop_local_ocr_worker()
            if response.get("ok"):
                return response.get("items") or []
            raise RuntimeError(response.get("error", "unknown OCR worker error"))
        except Exception as exc:
            print(f"[OCR] worker 处理失败 {image_path} 第{attempt + 1}次: {exc}")
            stop_local_ocr_worker()
    return None


def get_local_paddle_ocr():
    global _LOCAL_PADDLE_OCR
    if _LOCAL_PADDLE_OCR is None:
        os.makedirs(PADDLEX_CACHE_DIR, exist_ok=True)
        from paddleocr import PaddleOCR

        _LOCAL_PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang="ch")
    return _LOCAL_PADDLE_OCR


def local_ocr_image(image_path: str) -> list[dict]:
    worker_items = local_ocr_image_via_worker(image_path)
    if worker_items is not None:
        return worker_items
    return local_ocr_image_inprocess(image_path)


def local_ocr_image_inprocess(image_path: str) -> list[dict]:
    import gc

    try:
        ocr = get_local_paddle_ocr()
        result = run_local_ocr(ocr, image_path)
    except Exception as exc:
        print(f"[OCR] 本地 OCR 失败 {image_path}: {exc}")
        return []

    lines = extract_ocr_lines(result)
    del result  # 释放 PaddleOCR 结果内存
    if not lines:
        return []

    items = []
    for line in lines:
        box, rec = normalize_ocr_line(line)
        if box is None or rec is None:
            continue
        text = str(rec[0]).strip() if isinstance(rec, (list, tuple)) else str(rec).strip()
        if not text:
            continue
        points = coerce_ocr_box_points(box)
        xs = [int(point[0]) for point in points]
        ys = [int(point[1]) for point in points]
        if not xs or not ys:
            continue
        items.append(
            {
                "text": text,
                "x": int(sum(xs) / len(xs)),
                "y": int(sum(ys) / len(ys)),
                "w": max(xs) - min(xs),
                "h": max(ys) - min(ys),
            }
        )
    gc.collect()  # 强制清理 PaddleOCR 产生的临时对象
    return items


def run_local_ocr(ocr, image_path: str):
    if hasattr(ocr, "ocr"):
        try:
            return ocr.ocr(image_path, cls=True)
        except TypeError as exc:
            if "unexpected keyword argument 'cls'" not in str(exc):
                raise
            return ocr.ocr(image_path)
    if hasattr(ocr, "predict"):
        return ocr.predict(image_path)
    raise RuntimeError("PaddleOCR object has neither ocr() nor predict()")


def extract_ocr_lines(result) -> list:
    if not result:
        return []
    if isinstance(result, dict):
        return extract_ocr_lines_from_dict(result)
    if isinstance(result, list):
        if result and isinstance(result[0], list):
            return result[0]
        if result and isinstance(result[0], dict):
            lines = []
            for page in result:
                lines.extend(extract_ocr_lines_from_dict(page))
            return lines
        return result
    return []


def extract_ocr_lines_from_dict(page: dict) -> list:
    texts = page.get("rec_texts") or page.get("texts") or page.get("text")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not texts:
        return []

    boxes = (
        page.get("rec_polys")
        or page.get("dt_polys")
        or page.get("boxes")
        or page.get("polys")
        or page.get("points")
    )
    if boxes is None:
        boxes = [None] * len(texts)

    scores = page.get("rec_scores") or page.get("scores") or [1.0] * len(texts)
    lines = []
    for index, text in enumerate(texts):
        box = boxes[index] if index < len(boxes) else None
        score = scores[index] if index < len(scores) else 1.0
        lines.append([box, (text, score)])
    return lines


def normalize_ocr_line(line):
    if isinstance(line, (list, tuple)) and len(line) >= 2:
        return line[0], line[1]
    if isinstance(line, dict):
        box = (
            line.get("box")
            or line.get("bbox")
            or line.get("points")
            or line.get("poly")
            or line.get("polygon")
        )
        rec = (
            line.get("rec")
            or line.get("text")
            or line.get("label")
            or line.get("transcription")
        )
        if isinstance(rec, str):
            rec = (rec, 1.0)
        return box, rec
    return None, None


def coerce_ocr_box_points(box) -> list:
    if box is None:
        return []
    if hasattr(box, "tolist"):
        box = box.tolist()
    if isinstance(box, tuple):
        box = list(box)
    if not isinstance(box, list):
        return []
    if len(box) == 4 and all(isinstance(value, (int, float)) for value in box):
        left, top, right, bottom = box
        return [[left, top], [right, top], [right, bottom], [left, bottom]]
    points = []
    for point in box:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if isinstance(point, tuple):
            point = list(point)
        if isinstance(point, list) and len(point) >= 2:
            points.append(point)
    return points


def _apply_doubao_video_fields(video_info: dict, fields: dict) -> None:
    """将豆包视觉模型提取的播放页字段写入 video_info"""
    if not fields:
        return
    if fields.get("blogger_name"):
        video_info["blogger_name"] = fields["blogger_name"]
    if fields.get("title"):
        # 保留完整标题（含 # 话题标签）— 取证需保持证据完整性
        video_info["title"] = fields["title"]
    if fields.get("publish_time"):
        video_info["publish_time"] = fields["publish_time"]
    if fields.get("like_count"):
        video_info["like_count"] = str(fields["like_count"])
    if fields.get("comment_count"):
        video_info["comment_count"] = str(fields["comment_count"])
    if fields.get("share_count"):
        video_info["share_count"] = str(fields["share_count"])


def fill_video_fields_from_ocr(video_info: dict, ocr_items) -> None:
    items = ocr_items if isinstance(ocr_items, list) else []

    blogger_name = ""
    title = ""
    publish_time = ""
    like_count = ""
    comment_count = ""
    share_count = ""

    # 用于标题提取：收集下半屏的候选文本
    title_candidates = []

    for item in items:
        text = (item.get("text", "") or "").strip()
        x = item.get("x", 0)
        y = item.get("y", 0)
        if not text:
            continue
        if not blogger_name and ("关注" in text or "+关注" in text):
            candidate = text.replace("+关注", "").replace("关注", "").strip()
            if candidate and not is_likely_link(candidate) and not is_company_like_name(candidate):
                blogger_name = candidate
            continue
        if not blogger_name and 2120 <= y <= 2265 and 80 <= x <= 460:
            if re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9_]{2,20}", text) and not is_company_like_name(text):
                blogger_name = text
        if "VideoMate" in text:
            continue
        if not publish_time and re.search(r"(\d+(秒|分钟|小时|天|周|月|年)前|\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2})", text):
            publish_time = text

        # 标题候选：下半屏 (y >= 1200)、有一定长度、非纯数字/符号
        if y >= 1200 and len(text) >= 4 and not re.fullmatch(r"[\d.,+\-*/×@#\s]+", text):
            if "关注" not in text and "VideoMate" not in text:
                title_candidates.append((len(text), text))

    # 取最长文本作为视频标题（视频页标题通常是最长的描述性文字）
    if title_candidates:
        title_candidates.sort(key=lambda t: -t[0])
        title = title_candidates[0][1]

    # 保留完整标题（含 # 话题标签）— 取证需保持证据完整性

    stats = []
    for item in items:
        text = (item.get("text", "") or "").strip()
        x = item.get("x", 0)
        y = item.get("y", 0)
        if 2140 <= y <= 2300 and x >= 540:
            match = re.fullmatch(r"[\d.]+[wW万]?", text)
            if match:
                stats.append((x, match.group(0)))
    stats.sort(key=lambda pair: pair[0])
    if len(stats) >= 1:
        like_count = stats[0][1]
    if len(stats) >= 2:
        comment_count = stats[1][1]
    if len(stats) >= 3:
        share_count = stats[2][1]

    if title:
        video_info["title"] = title
    video_info["blogger_name"] = blogger_name
    video_info["publish_time"] = publish_time
    video_info["like_count"] = like_count
    video_info["comment_count"] = comment_count
    video_info["share_count"] = share_count


def find_traffic_marker_text_local(image_path: str) -> str:
    marker_text, _ = find_traffic_marker_target_local(image_path)
    return marker_text


def find_traffic_marker_target_local(
    image_path: str,
    offset_x: int = 0,
    offset_y: int = 0,
) -> tuple[str, tuple[int, int] | None]:
    items = local_ocr_image(image_path)
    candidate = find_traffic_marker_candidate(items, offset_x=offset_x, offset_y=offset_y)
    if not candidate:
        return "", None
    return candidate["text"], (candidate["x"], candidate["y"])


def find_traffic_marker_candidate(
    ocr_items,
    offset_x: int = 0,
    offset_y: int = 0,
) -> dict | None:
    items = [item for item in (ocr_items or []) if (item.get("text", "") or "").strip()]
    candidates = []

    for item in items:
        text = (item.get("text", "") or "").strip()
        if is_traffic_marker_text(text):
            x = int(item.get("x", 0)) + offset_x
            y = int(item.get("y", 0)) + offset_y
            width = int(item.get("w", 0) or 0)
            height = int(item.get("h", 0) or 0)
            candidates.append(
                {
                    "text": text,
                    "x": x,
                    "y": y,
                    "left": x - width // 2,
                    "right": x + width // 2,
                    "top": y - height // 2,
                    "bottom": y + height // 2,
                    "score": marker_candidate_score(text, width, height),
                }
            )

    for row in group_ocr_items_by_row(items):
        merged = "".join((item.get("text", "") or "").strip() for item in row)
        if not is_traffic_marker_text(merged):
            continue
        # 只用命中 is_traffic_marker_text 的 item 算坐标，排除同行的无关文字干扰
        matched_items = [item for item in row if is_traffic_marker_text((item.get("text", "") or "").strip())]
        if not matched_items:
            matched_items = row  # 兜底：合并文字命中但单条都没命中时用整行
        left = min(int(item.get("x", 0) - (item.get("w", 0) or 0) / 2) for item in matched_items) + offset_x
        right = max(int(item.get("x", 0) + (item.get("w", 0) or 0) / 2) for item in matched_items) + offset_x
        top = min(int(item.get("y", 0) - (item.get("h", 0) or 0) / 2) for item in matched_items) + offset_y
        bottom = max(int(item.get("y", 0) + (item.get("h", 0) or 0) / 2) for item in matched_items) + offset_y
        candidates.append(
            {
                "text": merged,
                "x": int((left + right) / 2),
                "y": int((top + bottom) / 2),
                "left": left,
                "right": right,
                "top": top,
                "bottom": bottom,
                "score": marker_candidate_score(merged, right - left, bottom - top) + 2,
            }
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item["score"], item["y"], item["x"]))
    return candidates[0]


def group_ocr_items_by_row(items: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for item in sorted(items, key=lambda value: (value.get("y", 0), value.get("x", 0))):
        y = int(item.get("y", 0))
        height = int(item.get("h", 0) or 0)
        threshold = max(24, height * 2)
        matched = None
        for row in rows:
            row_y = sum(int(entry.get("y", 0)) for entry in row) / len(row)
            if abs(y - row_y) <= threshold:
                matched = row
                break
        if matched is None:
            rows.append([item])
        else:
            matched.append(item)
    for row in rows:
        row.sort(key=lambda value: value.get("x", 0))
    return rows


def find_traffic_marker_text_from_items(ocr_items) -> str:
    texts = [(item.get("text", "") or "").strip() for item in ocr_items or []]
    return find_traffic_marker_text_from_texts(texts)


def find_traffic_marker_text_from_texts(texts: list[str]) -> str:
    for text in texts:
        if not text:
            continue
        if is_traffic_marker_text(text):
            return text
    merged = "".join(text for text in texts if text)
    if is_traffic_marker_text(merged):
        return merged
    return ""


def is_traffic_marker_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    return "免费剧集" in compact or bool(re.search(r"全\d{1,4}集", compact))


def marker_candidate_score(text: str, width: int, height: int) -> int:
    compact = re.sub(r"\s+", "", text or "")
    score = 0
    if "免费剧集" in compact:
        score += 5
    if re.search(r"全\d{1,4}集", compact):
        score += 4
    if width >= 80:
        score += 1
    if height >= 16:
        score += 1
    return score


async def open_traffic_subject(session, marker_point: tuple[int, int] | None = None) -> None:
    if not marker_point:
        print("[引流] 无有效点击坐标，跳过")
        return
    marker_x, marker_y = int(marker_point[0]), int(marker_point[1])
    code = f"""
import time
from ascript.android import action

action.click({marker_x}, {marker_y})
time.sleep(1.5)
print("[OK] TRAFFIC_POPUP_OPENED")
"""
    await run_on_phone(session, code, log_sec=5)
    await asyncio.sleep(0.8)


async def open_traffic_first_episode(session) -> None:
    episode_x, episode_y = scale_point(TRAFFIC_FIRST_EPISODE_X, TRAFFIC_FIRST_EPISODE_Y)
    code = f"""
import time
from ascript.android import action

action.click({episode_x}, {episode_y})
time.sleep(2.8)
print("[OK] TRAFFIC_SUBJECT_OPENED")
"""
    await run_on_phone(session, code, log_sec=6)
    await asyncio.sleep(1.0)


async def open_traffic_avatar_card(session) -> None:
    avatar_x, avatar_y = scale_point(TRAFFIC_AVATAR_X, TRAFFIC_AVATAR_Y)
    code = f"""
import time
from ascript.android import action

action.click({avatar_x}, {avatar_y})
time.sleep(1.8)
print("[OK] TRAFFIC_AVATAR_CARD_OPENED")
"""
    await run_on_phone(session, code, log_sec=5)
    await asyncio.sleep(0.8)


def extract_theater_account_name_from_image(image_path: str) -> str:
    candidate = find_best_author_name_candidate_from_image(image_path)
    if candidate:
        return candidate["text"]
    return ""


def _apply_doubao_profile_fields(profile_info: dict, video_info: dict, fields: dict) -> None:
    """将豆包视觉模型提取的博主信息页字段写入 profile_info / video_info

    复用 analyze_video_channel_id 校验视频号ID质量，与 PaddleOCR 路径保持一致。
    """
    if not fields:
        return
    account = (fields.get("video_channel_id") or "").strip()
    if account:
        id_quality = analyze_video_channel_id(account)
        profile_info["account"] = id_quality["normalized"]
        video_info["video_channel_id_raw"] = id_quality["raw"]
        video_info["video_channel_id"] = id_quality["normalized"]
        video_info["video_channel_id_needs_review"] = id_quality["needs_review"]
        video_info["video_channel_id_ambiguous_positions"] = id_quality["ambiguous_positions"]
    company = (fields.get("company_full_name") or "").strip()
    if company:
        profile_info["company_full_name"] = company
    subject = (fields.get("subject_type") or "").strip()
    if subject:
        profile_info["subject_type"] = subject
    elif company:
        profile_info["subject_type"] = "企业"


def fill_profile_fields_from_ocr(profile_info: dict, ocr_items) -> None:
    items = ocr_items if isinstance(ocr_items, list) else []
    texts = [(item.get("text", "") or "").strip() for item in items]

    account = ""
    company_name = ""
    has_company_label = False
    for index, text in enumerate(texts):
        if not text:
            continue
        if "视频号ID" in text or "视频号" in text or "账号" in text:
            account = pick_neighbor_value(texts, index)
            break

    if not account:
        for text in texts:
            compact = re.sub(r"\s+", "", text)
            if re.fullmatch(r"sph[A-Za-z0-9_-]{6,64}", compact):
                account = compact
                break

    for index, text in enumerate(texts):
        if not text:
            continue
        if "企业全称" not in text:
            continue
        has_company_label = True
        company_name = pick_company_name_from_profile_items(items, index, texts)
        if company_name:
            break

    if not company_name:
        for item in items:
            text = (item.get("text", "") or "").strip()
            if "有限公司" in text or "有限责任公司" in text:
                company_name = text
                has_company_label = True
                break

    profile_info["account"] = account
    profile_info["company_full_name"] = company_name
    profile_info["subject_type"] = "企业" if has_company_label or company_name else "个人"


def pick_company_name_from_profile_items(items: list[dict], label_index: int, texts: list[str]) -> str:
    label_item = items[label_index] if label_index < len(items) else {}
    label_text = texts[label_index] if label_index < len(texts) else ""
    inline = pick_inline_value(label_text)
    if inline:
        return inline

    value = pick_multiline_value_after_label(items, label_item, "企业全称")
    if value:
        return value

    return pick_neighbor_value(texts, label_index)


def pick_multiline_value_after_label(items: list[dict], label_item: dict, label_text: str) -> str:
    label_x = label_item.get("x", 0)
    label_y = label_item.get("y", 0)
    if not label_y:
        return ""

    next_label_y = find_next_left_label_y(items, label_x, label_y)
    bottom_y = (next_label_y - 30) if next_label_y else (label_y + 220)
    candidates = []
    for item in items:
        text = (item.get("text", "") or "").strip()
        if not text or label_text in text or is_profile_field_label(text):
            continue
        x = item.get("x", 0)
        y = item.get("y", 0)
        if x <= label_x + 120:
            continue
        if label_y - 45 <= y < bottom_y:
            candidates.append((y, x, text))
    if not candidates:
        return ""

    parts = [text for _, _, text in sorted(candidates, key=lambda row: (row[0], row[1]))]
    return clean_joined_company_name("".join(parts))


def find_next_left_label_y(items: list[dict], label_x: int, label_y: int) -> int:
    candidates = []
    for item in items:
        text = (item.get("text", "") or "").strip()
        y = item.get("y", 0)
        x = item.get("x", 0)
        if y <= label_y + 30:
            continue
        if is_profile_field_label(text) or x <= label_x + 80:
            candidates.append(y)
    return min(candidates) if candidates else 0


def is_profile_field_label(text: str) -> bool:
    return text in (
        "IP归属地",
        "资料所在地",
        "视频号ID",
        "认证信息",
        "企业全称",
        "主体类型",
        "认证时间",
        "一般经营范围",
    )


def clean_joined_company_name(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    text = re.sub(r"(蓝V|认证|✓|✔|✅)$", "", text)
    return text.strip()


def pick_inline_value(text: str) -> str:
    for sep in ("：", ":", " "):
        if sep in text:
            value = text.split(sep, 1)[1].strip()
            if value and "企业全称" not in value:
                return value
    return ""


def fill_video_channel_id_from_profile(video_info: dict, profile_info: dict) -> None:
    account = profile_info.get("account", "") or ""
    if not account:
        return
    id_quality = analyze_video_channel_id(account)
    video_info["video_channel_id_raw"] = id_quality["raw"]
    video_info["video_channel_id"] = id_quality["normalized"]
    video_info["video_channel_id_needs_review"] = id_quality["needs_review"]
    video_info["video_channel_id_ambiguous_positions"] = id_quality["ambiguous_positions"]


async def open_traffic_more_info_from_avatar_card(session) -> None:
    more_button_x, more_button_y = scale_point(TRAFFIC_MORE_BUTTON_X, TRAFFIC_MORE_BUTTON_Y)
    more_info_x, more_info_y = scale_point(TRAFFIC_MORE_INFO_X, TRAFFIC_MORE_INFO_Y)
    code = f"""
import time
from ascript.android import action

action.click({more_button_x}, {more_button_y})
time.sleep(1.6)
action.click({more_info_x}, {more_info_y})
time.sleep(2.0)
print("[OK] TRAFFIC_MORE_INFO_OPENED")
"""
    await run_on_phone(session, code, log_sec=8)
    await asyncio.sleep(1.0)


def _apply_doubao_traffic_fields(traffic_info: dict, fields: dict) -> None:
    """将豆包视觉模型提取的引流信息页字段写入 traffic_info

    复用 analyze_video_channel_id 校验目标视频号ID质量，与 PaddleOCR 路径保持一致。
    """
    if not fields:
        return
    target_id = (fields.get("target_video_channel_id") or "").strip()
    if target_id:
        id_quality = analyze_video_channel_id(target_id)
        traffic_info["target_video_channel_id_raw"] = id_quality["raw"]
        traffic_info["target_video_channel_id"] = id_quality["normalized"]
        traffic_info["target_video_channel_id_needs_review"] = id_quality["needs_review"]
        traffic_info["target_video_channel_id_ambiguous_positions"] = id_quality["ambiguous_positions"]
    company = (fields.get("company_full_name") or "").strip()
    if company:
        traffic_info["company_full_name"] = company
    verified_at = (fields.get("company_verified_at") or "").strip()
    if verified_at:
        traffic_info["company_verified_at"] = verified_at


def fill_traffic_fields_from_ocr(traffic_info: dict, ocr_items) -> None:
    items = ocr_items if isinstance(ocr_items, list) else []
    texts = [(item.get("text", "") or "").strip() for item in items]

    raw_id = ""
    company_name = ""
    verified_at = ""

    for index, text in enumerate(texts):
        if not text:
            continue
        if not raw_id and ("视频号ID" in text or "视频号" in text or "账号" in text):
            raw_id = pick_neighbor_value(texts, index)
        if not company_name and "企业全称" in text:
            company_name = pick_company_name_from_profile_items(items, index, texts)
        if not verified_at and ("认证时间" in text or "完成微信认证" in text):
            verified_at = pick_neighbor_value(texts, index) if "认证时间" in text else text

    if not raw_id:
        for text in texts:
            compact = re.sub(r"\s+", "", text)
            if re.fullmatch(r"[A-Za-z0-9_-]{6,64}", compact) and not compact.isdigit():
                raw_id = compact
                break

    if not company_name:
        for text in texts:
            if any(token in text for token in ("有限公司", "有限责任公司", "公司")):
                company_name = clean_joined_company_name(text)
                break

    if not verified_at:
        for text in texts:
            if re.search(r"\d{4}年\d{1,2}月\d{1,2}日", text):
                verified_at = text
                break

    id_quality = analyze_video_channel_id(raw_id)
    traffic_info["target_video_channel_id_raw"] = id_quality["raw"]
    traffic_info["target_video_channel_id"] = id_quality["normalized"]
    traffic_info["target_video_channel_id_needs_review"] = id_quality["needs_review"]
    traffic_info["target_video_channel_id_ambiguous_positions"] = id_quality["ambiguous_positions"]
    traffic_info["company_full_name"] = company_name
    traffic_info["company_verified_at"] = verified_at


def pick_neighbor_value(texts: list[str], index: int) -> str:
    for candidate_index in (index, index + 1, index - 1):
        if candidate_index < 0 or candidate_index >= len(texts):
            continue
        value = texts[candidate_index]
        if "：" in value:
            return value.split("：", 1)[1].strip()
        if ":" in value:
            return value.split(":", 1)[1].strip()
        if candidate_index != index and value:
            return value.strip()
    return ""


async def back_from_traffic_info(session) -> None:
    adb_prefix = _adb_args()
    for index in range(4):
        subprocess.run(
            adb_prefix + ["shell", "input", "keyevent", "4"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        print(f"[引流] ADB 返回 {index + 1}/4")
        # 加长间隔，确保页面刷新完成再触发下一次回退，避免在过渡态触发导致跳层
        await asyncio.sleep(2.0 if index < 3 else 2.4)
