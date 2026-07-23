# -*- coding: utf-8 -*-
"""工单台词库：按关键词目录存放；默认装全文，可选手动清洗（旁白+对白）。"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import PROJECT_ROOT, SCRIPTS_DIR

_SAFE_NAME_RE = re.compile(r'[\\/:*?"<>|]+')

SCRIPT_STATUS_NONE = "none"
SCRIPT_STATUS_PENDING = "pending"
SCRIPT_STATUS_CLEANING = "cleaning"
SCRIPT_STATUS_READY = "ready"
SCRIPT_STATUS_FAILED = "failed"

SCRIPT_STATUS_LABELS = {
    SCRIPT_STATUS_NONE: "缺台词",
    SCRIPT_STATUS_PENDING: "待装库",
    SCRIPT_STATUS_CLEANING: "清洗中",
    SCRIPT_STATUS_READY: "台词就绪",
    SCRIPT_STATUS_FAILED: "清洗失败",
}

LIBRARY_MODE_FULL = "full"
LIBRARY_MODE_NARRATION_DIALOG = "narration_dialog"

LIBRARY_MODE_LABELS = {
    LIBRARY_MODE_FULL: "原文",
    LIBRARY_MODE_NARRATION_DIALOG: "旁白+对白",
}


def safe_keyword(name: str) -> str:
    s = (name or "").strip()
    s = _SAFE_NAME_RE.sub("_", s)
    return s[:180]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def script_dir_for(drama_name: str) -> Path:
    kw = safe_keyword(drama_name)
    if not kw:
        raise ValueError("剧名为空")
    d = SCRIPTS_DIR / kw
    d.mkdir(parents=True, exist_ok=True)
    return d


def raw_script_path(drama_name: str) -> Path:
    """比对生效库（matcher 读取此文件）。"""
    return script_dir_for(drama_name) / "_script_raw.txt"


def full_script_path(drama_name: str) -> Path:
    """原文抽取（不经 LLM）。"""
    return script_dir_for(drama_name) / "_full.txt"


def meta_path(drama_name: str) -> Path:
    return script_dir_for(drama_name) / "_meta.json"


def read_meta(drama_name: str) -> dict:
    p = meta_path(drama_name)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_meta(drama_name: str, meta: dict) -> Path:
    p = meta_path(drama_name)
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def library_mode_of(drama_name: str) -> str:
    mode = (read_meta(drama_name).get("library_mode") or "").strip()
    if mode in LIBRARY_MODE_LABELS:
        return mode
    if raw_script_path(drama_name).is_file():
        return LIBRARY_MODE_FULL
    return ""


def library_mode_label(mode: str) -> str:
    return LIBRARY_MODE_LABELS.get(mode or "", mode or "")


def _write_text(path: Path, text: str) -> Path:
    body = (text or "").strip()
    path.write_text(body + ("\n" if body else ""), encoding="utf-8")
    return path


def install_cleaned_text(drama_name: str, text: str) -> Path:
    """覆盖比对库（清洗结果）。"""
    return _write_text(raw_script_path(drama_name), text)


def install_full_text(
    drama_name: str,
    text: str,
    *,
    source_hash: str = "",
    work_order_id: Optional[int] = None,
    keyword: str = "",
) -> Path:
    """写入 _full.txt + _script_raw.txt，library_mode=full。"""
    body = (text or "").strip()
    if not body:
        raise ValueError("台词全文为空")
    _write_text(full_script_path(drama_name), body)
    dest = _write_text(raw_script_path(drama_name), body)
    meta = {
        "keyword": keyword or safe_keyword(drama_name),
        "source_sha256": source_hash or "",
        "library_mode": LIBRARY_MODE_FULL,
        "cleaner": "none",
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "chars": len(body),
    }
    if work_order_id is not None:
        meta["work_order_id"] = work_order_id
    # 保留历史字段兼容
    meta["cleaned_at"] = meta["installed_at"]
    write_meta(drama_name, meta)
    return dest


def save_source_bytes(drama_name: str, data: bytes, ext: str) -> Path:
    d = script_dir_for(drama_name)
    ext = ext if ext.startswith(".") else f".{ext}"
    for old in d.glob("_source.*"):
        try:
            old.unlink()
        except OSError:
            pass
    dest = d / f"_source{ext}"
    dest.write_bytes(data)
    return dest


def library_ready_for_hash(drama_name: str, source_hash: str) -> bool:
    raw = raw_script_path(drama_name)
    if not raw.is_file() or raw.stat().st_size == 0:
        return False
    meta = read_meta(drama_name)
    if not meta:
        return True
    stored = (meta.get("source_sha256") or "").strip()
    if not stored:
        return True
    return stored == source_hash


def disk_library_ready(drama_name: str) -> bool:
    raw = raw_script_path(drama_name) if drama_name else None
    return bool(raw and raw.is_file() and raw.stat().st_size > 0)


def resolve_script_gate(
    drama_name: str,
    wo_script_status: str = "",
    script_error: str = "",
) -> tuple[bool, str]:
    """二阶段门禁：有比对库即可；不再因「未清洗」拦截。"""
    if disk_library_ready(drama_name):
        return True, ""
    status = (wo_script_status or "").strip()
    if status == SCRIPT_STATUS_READY:
        return False, f"剧名「{drama_name}」台词状态就绪但磁盘缺少 _script_raw.txt，请重新上传台词"
    if status == SCRIPT_STATUS_NONE:
        return False, f"剧名「{drama_name}」尚未上传台词，请先补传剧本后再开二阶段"
    if status == SCRIPT_STATUS_CLEANING:
        return False, f"剧名「{drama_name}」台词清洗中，请稍后再试"
    if status == SCRIPT_STATUS_PENDING:
        return False, f"剧名「{drama_name}」台词尚未装入比对库，请重新上传或等待装库完成"
    if status == SCRIPT_STATUS_FAILED:
        reason = (script_error or "").strip()
        if reason:
            return False, f"剧名「{drama_name}」台词处理失败：{reason}"
        return False, f"剧名「{drama_name}」台词处理失败，请重新上传剧本"
    return False, f"剧名「{drama_name}」缺少台词文件（_script_raw.txt），无法开二阶段"


def _load_full_text(drama_name: str) -> str:
    full = full_script_path(drama_name)
    if full.is_file() and full.stat().st_size > 0:
        return full.read_text(encoding="utf-8")
    d = script_dir_for(drama_name)
    for src in sorted(d.glob("_source.*")):
        if src.is_file():
            from weixin.asr.script_cleaner import extract_script_bytes

            return extract_script_bytes(src.read_bytes(), src.name)
    raw = raw_script_path(drama_name)
    if raw.is_file() and raw.stat().st_size > 0:
        return raw.read_text(encoding="utf-8")
    return ""


async def install_full_work_order_script(work_order_id: int) -> None:
    """兼容旧 pending：从附件抽取全文装库（不 LLM）。"""
    from sqlalchemy import select
    from database import async_session
    from models import WorkOrder, WorkOrderAttachment
    from weixin.asr.script_cleaner import extract_script_bytes

    async with async_session() as db:
        wo = (
            await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
        ).scalar_one_or_none()
        if not wo:
            return
        drama = wo.drama_name or ""
        if not drama:
            return
        source_hash = (getattr(wo, "script_source_hash", None) or "").strip()
        if library_ready_for_hash(drama, source_hash or ""):
            wo.script_status = SCRIPT_STATUS_READY
            wo.script_error = ""
            wo.updated_at = datetime.now()
            await db.commit()
            return

        att = (
            await db.execute(
                select(WorkOrderAttachment)
                .where(
                    WorkOrderAttachment.work_order_id == work_order_id,
                    WorkOrderAttachment.file_type == "script",
                )
                .order_by(WorkOrderAttachment.id.desc())
            )
        ).scalars().first()
        if not att or not att.file_path:
            wo.script_status = SCRIPT_STATUS_NONE
            wo.script_error = "无剧本附件"
            wo.updated_at = datetime.now()
            await db.commit()
            return

        src_path = PROJECT_ROOT / att.file_path
        if not src_path.is_file():
            wo.script_status = SCRIPT_STATUS_FAILED
            wo.script_error = f"附件不存在: {att.file_path}"
            wo.updated_at = datetime.now()
            await db.commit()
            return

        raw = src_path.read_bytes()
        source_hash = sha256_bytes(raw)
        ext = Path(att.file_name or src_path.name).suffix.lower() or ".docx"
        try:
            text = extract_script_bytes(raw, att.file_name or src_path.name)
            if not text.strip():
                raise RuntimeError("抽取台词为空")
            save_source_bytes(drama, raw, ext)
            install_full_text(
                drama,
                text,
                source_hash=source_hash,
                work_order_id=work_order_id,
                keyword=drama,
            )
            wo.script_status = SCRIPT_STATUS_READY
            wo.script_source_hash = source_hash
            wo.script_cleaned_at = datetime.now()
            wo.script_error = ""
            wo.updated_at = datetime.now()
            await db.commit()
            print(f"[script_install] 工单 #{work_order_id} 全文装库 chars={len(text)}")
        except Exception as e:
            print(f"[script_install] 工单 #{work_order_id} 失败: {e}")
            wo.script_status = SCRIPT_STATUS_FAILED
            wo.script_error = str(e)[:500]
            wo.updated_at = datetime.now()
            await db.commit()


async def clean_work_order_script(work_order_id: int) -> None:
    """后台任务：手动清洗为旁白+对白，覆盖比对库。"""
    from sqlalchemy import select
    from database import async_session
    from models import WorkOrder
    from weixin.asr.script_cleaner import clean_script_to_narration_and_dialogues

    async with async_session() as db:
        wo = (
            await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
        ).scalar_one_or_none()
        if not wo:
            print(f"[script_clean] 工单 #{work_order_id} 不存在")
            return

        drama = wo.drama_name or ""
        if not drama:
            wo.script_status = SCRIPT_STATUS_FAILED
            wo.script_error = "剧名为空"
            wo.updated_at = datetime.now()
            await db.commit()
            return

        if not disk_library_ready(drama) and not full_script_path(drama).is_file():
            # 尝试先装全文
            await install_full_work_order_script(work_order_id)
            wo = (
                await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
            ).scalar_one_or_none()
            if not wo or not disk_library_ready(drama):
                return

        wo.script_status = SCRIPT_STATUS_CLEANING
        wo.script_error = ""
        wo.updated_at = datetime.now()
        await db.commit()

        try:
            full_text = _load_full_text(drama)
            if not full_text.strip():
                raise RuntimeError("无原文可供清洗")
            cleaned, mode = clean_script_to_narration_and_dialogues(full_text)
            if not cleaned.strip():
                raise RuntimeError("清洗后旁白+对白为空")
            install_cleaned_text(drama, cleaned)
            source_hash = (getattr(wo, "script_source_hash", None) or "").strip()
            write_meta(drama, {
                "keyword": safe_keyword(drama),
                "source_sha256": source_hash,
                "library_mode": LIBRARY_MODE_NARRATION_DIALOG,
                "cleaner": mode,
                "cleaned_at": datetime.now().isoformat(timespec="seconds"),
                "chars": len(cleaned),
                "work_order_id": work_order_id,
            })
            wo = (
                await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
            ).scalar_one()
            wo.script_status = SCRIPT_STATUS_READY
            wo.script_cleaned_at = datetime.now()
            wo.script_error = ""
            wo.updated_at = datetime.now()
            await db.commit()
            print(
                f"[script_clean] 工单 #{work_order_id} 清洗完成 "
                f"mode={mode} chars={len(cleaned)}"
            )
        except Exception as e:
            print(f"[script_clean] 工单 #{work_order_id} 失败: {e}")
            wo = (
                await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
            ).scalar_one_or_none()
            if wo:
                # 清洗失败但原文库仍在 → 保持 ready，记录错误
                if disk_library_ready(drama):
                    wo.script_status = SCRIPT_STATUS_READY
                else:
                    wo.script_status = SCRIPT_STATUS_FAILED
                wo.script_error = str(e)[:500]
                wo.updated_at = datetime.now()
                await db.commit()


def schedule_clean_work_order(work_order_id: int) -> None:
    """Fire-and-forget 后台清洗（旁白+对白）。"""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(clean_work_order_script(work_order_id))


def schedule_install_full_work_order(work_order_id: int) -> None:
    """Fire-and-forget 全文装库（旧 pending 兼容）。"""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(install_full_work_order_script(work_order_id))
