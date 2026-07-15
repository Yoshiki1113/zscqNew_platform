"""启动时预热 — 提前下载/初始化第三方模型，避免任务运行时首次加载延迟"""
from __future__ import annotations

import asyncio
import os
import struct
import tempfile
import traceback
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _prewarm_paddleocr() -> dict:
    """初始化 PaddleOCR，触发模型下载（如有需要）到 .paddlex-cache/"""
    result = {"ok": False, "error": "", "cache_dir": ""}
    try:
        cache_dir = Path(__file__).resolve().parent / "weixin" / "core" / ".paddlex-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ.setdefault("FLAGS_enable_pir_api", "0")
        os.environ.setdefault("FLAGS_json_format_model", "0")
        os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MKLDNN_MODEL_BL", "True")
        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_use_onednn", "0")
        os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")
        result["cache_dir"] = str(cache_dir)

        from paddleocr import PaddleOCR
        print("  [prewarm] PaddleOCR 初始化中（首次可能下载模型）...")
        ocr = PaddleOCR(use_angle_cls=True, lang="ch")
        _ = ocr.ocr  # 确认模型已加载
        print(f"  [prewarm] PaddleOCR ✓  缓存: {cache_dir}")
        result["ok"] = True
    except Exception as e:
        result["error"] = str(e)
        print(f"  [prewarm] PaddleOCR ✗  失败: {e}")
        traceback.print_exc()
    return result


def _prewarm_ocr_worker() -> dict:
    """启动 OCR worker 子进程并发送预热图片，确保 worker 内 PaddleOCR 已就绪

    使用 collector 模块的 read_ocr_worker_line 安全读取响应，
    超时后自动重启 worker 避免 stdout 读取线程冲突。
    """
    result = {"ok": False, "error": "", "worker_pid": 0}
    tmp_path = ""
    try:
        from weixin.core.collector import (
            get_local_ocr_worker,
            stop_local_ocr_worker,
            read_ocr_worker_line,
        )

        # 创建 100x100 纯黑 PNG（足够大，避免检测模型 resize 后维度为 0）
        def _make_warmup_png() -> bytes:
            """生成 100x100 纯黑 PNG（IHDR + IDAT + IEND）"""
            def chunk(ctype: bytes, data: bytes) -> bytes:
                c = ctype + data
                return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

            width, height = 100, 100
            ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
            # 每行：1 字节 filter + width*3 字节 RGB
            raw_rows = b""
            for _ in range(height):
                raw_rows += b"\x00" + b"\x00\x00\x00" * width
            idat = zlib.compress(raw_rows)
            return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="prewarm_ocr_")
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(_make_warmup_png())

        print("  [prewarm] OCR worker 启动中（首次加载 PaddleOCR 模型约需 20-60s）...")
        proc = get_local_ocr_worker()
        result["worker_pid"] = proc.pid

        import json as _json
        payload = _json.dumps({"image_path": tmp_path}, ensure_ascii=False)
        proc.stdin.write(payload + "\n")
        proc.stdin.flush()

        # 使用 collector 的 read_ocr_worker_line（内部用 queue+thread，超时安全）
        from config import OCR_WORKER_TIMEOUT_SECONDS
        line = read_ocr_worker_line(proc, timeout_seconds=OCR_WORKER_TIMEOUT_SECONDS)
        if not line:
            stop_local_ocr_worker()
            raise RuntimeError("Worker 无响应（返回空行）")

        response = _json.loads(line)
        if not response.get("ok"):
            stop_local_ocr_worker()
            raise RuntimeError(response.get("error", "Worker 返回失败"))

        print(f"  [prewarm] OCR worker ✓  pid={proc.pid}  jobs={response.get('jobs')}")
        result["ok"] = True
    except Exception as e:
        result["error"] = str(e)
        print(f"  [prewarm] OCR worker ✗  失败: {e}")
        traceback.print_exc()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return result


def _check_xunfei() -> dict:
    """检查讯飞云 ASR 是否可用（环境变量或代码中的默认值）"""
    appid = os.environ.get("XUNFEI_APPID", "") or "6df50e17"
    apikey = os.environ.get("XUNFEI_APIKEY", "") or "21dd94aa98239d94138b9cefd38e151d"
    configured = bool(appid and apikey)
    return {"configured": configured, "appid": appid[:8] + "..." if configured else ""}


def _check_doubao_vision() -> dict:
    """检查豆包视觉 API 是否可用（启动时发一次 ping 请求验证密钥有效性）"""
    try:
        from weixin.core.doubao_vision import check_availability
        status = check_availability()
    except Exception as e:
        status = {
            "enabled": True,
            "configured": False,
            "model": "",
            "base_url": "",
            "ok": False,
            "error": f"模块加载失败: {e}",
        }
    if not status["enabled"]:
        print("  [prewarm] 豆包视觉 ⊘  已禁用（ARK_VISION_ENABLED=0）")
    elif status["ok"]:
        print(f"  [prewarm] 豆包视觉 ✓  模型={status['model']}  连通正常")
    else:
        print(f"  [prewarm] 豆包视觉 ✗  {status['error'][:120]}")
        print("  [prewarm]           字段提取将回退到 PaddleOCR")
    return status


def _check_script_data() -> dict:
    """检查剧本台词文件是否存在"""
    from config import SCRIPTS_DIR
    result = {"scripts_dir": str(SCRIPTS_DIR), "found": False, "keywords": []}
    if SCRIPTS_DIR.exists():
        result["found"] = True
        result["keywords"] = [
            d.name for d in SCRIPTS_DIR.iterdir()
            if d.is_dir() and (d / "_script_raw.txt").exists()
        ]
    return result


async def run_prewarm():
    """在后台线程池中执行预热任务（不阻塞 API 启动）"""
    loop = asyncio.get_running_loop()

    with ThreadPoolExecutor(max_workers=1) as pool:
        # PaddleOCR 主进程初始化（必须先完成，否则 worker 可能因缺少缓存而出错）
        paddle_future = loop.run_in_executor(pool, _prewarm_paddleocr)

        # 这些检查同步完成，不耗时
        xunfei_status = _check_xunfei()
        script_status = _check_script_data()
        doubao_status = _check_doubao_vision()

        paddle_status = await paddle_future

        # PaddleOCR 缓存就绪后再启动 worker（worker 依赖缓存中的模型文件）
        if paddle_status["ok"]:
            await loop.run_in_executor(pool, _prewarm_ocr_worker)
            worker_status = {"ok": True}
        else:
            print("  [prewarm] OCR worker ⊘  跳过（PaddleOCR 未就绪）")
            worker_status = {"ok": False, "error": "PaddleOCR 未就绪"}

    # ── 汇总 ──
    print(f"  [prewarm] 讯飞云ASR: {'✓ 已配置' if xunfei_status['configured'] else '✗ 未配置'}")
    print(f"  [prewarm] 剧本台词: {'✓' if script_status['found'] else '✗ 未找到'} "
          f"{script_status['scripts_dir']}")
    if script_status["keywords"]:
        print(f"  [prewarm]           已配置剧名: {', '.join(script_status['keywords'])}")

    return {
        "paddleocr": paddle_status,
        "ocr_worker": worker_status,
        "xunfei": xunfei_status,
        "scripts": script_status,
        "doubao_vision": doubao_status,
    }
