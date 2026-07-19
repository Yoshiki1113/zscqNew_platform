# -*- coding: utf-8 -*-
"""工单台词异步清洗：剧名级缓存 + 源文件哈希复用。"""
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
    SCRIPT_STATUS_PENDING: "待清洗",
    SCRIPT_STATUS_CLEANING: "清洗中",
    SCRIPT_STATUS_READY: "台词就绪",
    SCRIPT_STATUS_FAILED: "清洗失败",
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
    return script_dir_for(drama_name) / "_script_raw.txt"


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


def install_cleaned_text(drama_name: str, text: str) -> Path:
    dest = raw_script_path(drama_name)
    body = (text or "").strip()
    dest.write_text(body + ("\n" if body else ""), encoding="utf-8")
    return dest


def save_source_bytes(drama_name: str, data: bytes, ext: str) -> Path:
    d = script_dir_for(drama_name)
    ext = ext if ext.startswith(".") else f".{ext}"
    # 清理旧源文件
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
        # 历史：已有清洗 txt、无 meta → 视为可复用，避免重洗
        return True
    stored = (meta.get("source_sha256") or "").strip()
    if not stored:
        return True
    return stored == source_hash


def resolve_script_gate(
    drama_name: str,
    wo_script_status: str = "",
    script_error: str = "",
) -> tuple[bool, str]:
    """二阶段门禁。返回 (ok, error_message)。"""
    status = (wo_script_status or "").strip()
    if status == SCRIPT_STATUS_READY:
        return True, ""
    if status == SCRIPT_STATUS_NONE:
        return False, f"剧名「{drama_name}」尚未上传台词，请先补传剧本后再开二阶段"
    if status in (SCRIPT_STATUS_PENDING, SCRIPT_STATUS_CLEANING):
        return False, f"剧名「{drama_name}」台词清洗尚未完成（{SCRIPT_STATUS_LABELS.get(status, status)}），请稍后再试"
    if status == SCRIPT_STATUS_FAILED:
        reason = (script_error or "").strip()
        if reason:
            return False, f"剧名「{drama_name}」台词清洗失败：{reason}"
        return False, f"剧名「{drama_name}」台词清洗失败，请重新上传剧本或联系运维"
    # 无工单状态：仅检查磁盘
    raw = raw_script_path(drama_name) if drama_name else None
    if raw and raw.is_file() and raw.stat().st_size > 0:
        return True, ""
    return False, f"剧名「{drama_name}」缺少清洗台词文件（_script_raw.txt），无法开二阶段"


async def clean_work_order_script(work_order_id: int) -> None:
    """后台任务：按工单附件清洗台词并写入剧名级台词库。"""
    from sqlalchemy import select
    from database import async_session
    from models import WorkOrder, WorkOrderAttachment
    from weixin.asr.script_cleaner import clean_script_to_dialogues, extract_script_bytes

    async with async_session() as db:
        wo = (
            await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
        ).scalar_one_or_none()
        if not wo:
            print(f"[script_clean] 工单 #{work_order_id} 不存在")
            return

        drama = wo.drama_name or ""
        status = getattr(wo, "script_status", None) or SCRIPT_STATUS_NONE
        if status == SCRIPT_STATUS_NONE:
            print(f"[script_clean] 工单 #{work_order_id} 无台词附件，跳过")
            return

        source_hash = (getattr(wo, "script_source_hash", None) or "").strip()
        if status == SCRIPT_STATUS_READY and source_hash and library_ready_for_hash(drama, source_hash):
            print(f"[script_clean] 工单 #{work_order_id} 已就绪，跳过")
            return

        # 历史 txt 无 meta：直接标 ready
        if library_ready_for_hash(drama, source_hash or ""):
            meta = read_meta(drama)
            if not meta and raw_script_path(drama).is_file():
                write_meta(drama, {
                    "source_sha256": source_hash,
                    "cleaner": "legacy",
                    "cleaned_at": datetime.now().isoformat(timespec="seconds"),
                    "chars": raw_script_path(drama).stat().st_size,
                })
            wo.script_status = SCRIPT_STATUS_READY
            wo.script_cleaned_at = datetime.now()
            wo.script_error = ""
            if source_hash:
                wo.script_source_hash = source_hash
            wo.updated_at = datetime.now()
            await db.commit()
            print(f"[script_clean] 工单 #{work_order_id} 复用已有 _script_raw.txt")
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
        wo.script_source_hash = source_hash

        if library_ready_for_hash(drama, source_hash):
            wo.script_status = SCRIPT_STATUS_READY
            wo.script_cleaned_at = datetime.now()
            wo.script_error = ""
            wo.updated_at = datetime.now()
            await db.commit()
            print(f"[script_clean] 工单 #{work_order_id} 哈希命中缓存，跳过 LLM")
            return

        wo.script_status = SCRIPT_STATUS_CLEANING
        wo.script_error = ""
        wo.updated_at = datetime.now()
        await db.commit()

        ext = Path(att.file_name or src_path.name).suffix.lower() or ".docx"
        try:
            extracted = extract_script_bytes(raw, att.file_name or src_path.name)
            cleaned, mode = clean_script_to_dialogues(extracted)
            if not cleaned.strip():
                raise RuntimeError("清洗后对白为空")
            save_source_bytes(drama, raw, ext)
            install_cleaned_text(drama, cleaned)
            write_meta(drama, {
                "source_sha256": source_hash,
                "cleaner": mode,
                "cleaned_at": datetime.now().isoformat(timespec="seconds"),
                "chars": len(cleaned),
                "work_order_id": work_order_id,
            })
            # 刷新对象
            wo = (
                await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
            ).scalar_one()
            wo.script_status = SCRIPT_STATUS_READY
            wo.script_source_hash = source_hash
            wo.script_cleaned_at = datetime.now()
            wo.script_error = ""
            wo.updated_at = datetime.now()
            await db.commit()
            print(f"[script_clean] 工单 #{work_order_id} 清洗完成 mode={mode} chars={len(cleaned)}")
        except Exception as e:
            print(f"[script_clean] 工单 #{work_order_id} 失败: {e}")
            wo = (
                await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
            ).scalar_one_or_none()
            if wo:
                wo.script_status = SCRIPT_STATUS_FAILED
                wo.script_error = str(e)[:500]
                wo.updated_at = datetime.now()
                await db.commit()


def schedule_clean_work_order(work_order_id: int) -> None:
    """Fire-and-forget 后台清洗。"""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(clean_work_order_script(work_order_id))
