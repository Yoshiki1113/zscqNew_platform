# -*- coding: utf-8 -*-
"""断点续采：清除本任务未入库的半截截图/录屏/json 等孤儿文件。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from config import (
    ASR_DIR,
    EVIDENCE_DATA_DIR,
    JSONS_DIR,
    RECORDINGS_DIR,
    SCREENSHOTS_DIR,
)


def _norm_path(p: str | Path) -> Optional[Path]:
    if not p:
        return None
    try:
        path = Path(str(p).replace("\\", "/"))
        if not path.is_absolute():
            path = EVIDENCE_DATA_DIR / path
        return path.resolve()
    except Exception:
        return None


def _add_path(refs: set[Path], raw: str | Path | None) -> None:
    n = _norm_path(raw) if raw is not None else None
    if n is not None:
        refs.add(n)


def referenced_paths_for_records(rows: Iterable) -> set[Path]:
    """从 EvidenceRecord 列表汇总已引用文件路径（绝对 resolve）。"""
    refs: set[Path] = set()
    for r in rows:
        shots = []
        try:
            shots = list(getattr(r, "screenshots", None) or [])
        except Exception:
            shots = []
        if not shots:
            raw = getattr(r, "screenshots_json", None) or "[]"
            try:
                shots = json.loads(raw) if isinstance(raw, str) else (raw or [])
            except (json.JSONDecodeError, TypeError):
                shots = []
        for s in shots:
            if isinstance(s, dict):
                _add_path(refs, s.get("path") or s.get("file") or "")
            else:
                _add_path(refs, s)
        _add_path(refs, getattr(r, "recording_video_path", None) or "")
        _add_path(refs, getattr(r, "recording_audio_path", None) or "")
        _add_path(refs, getattr(r, "json_path", None) or "")
        _add_path(refs, getattr(r, "html_path", None) or "")
        # json 同名 html
        jp = _norm_path(getattr(r, "json_path", None) or "")
        if jp is not None:
            _add_path(refs, jp.with_suffix(".html"))
    return refs


async def referenced_paths_for_task(task_id: int) -> set[Path]:
    from sqlalchemy import select
    from database import async_session
    from models import EvidenceRecord

    async with async_session() as db:
        rows = (
            await db.execute(
                select(EvidenceRecord).where(EvidenceRecord.task_id == task_id)
            )
        ).scalars().all()
        return referenced_paths_for_records(rows)


def _iter_media_files() -> list[Path]:
    dirs = [SCREENSHOTS_DIR, RECORDINGS_DIR, JSONS_DIR, ASR_DIR]
    out: list[Path] = []
    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file():
                out.append(p)
    return out


def cleanup_task_orphan_media_sync(
    referenced: set[Path],
    since: Optional[datetime],
) -> dict:
    """删除未引用且 mtime >= since 的媒体文件。"""
    if since is None:
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    since_ts = since.timestamp()

    deleted = 0
    skipped_referenced = 0
    skipped_old = 0
    errors = 0

    for p in _iter_media_files():
        try:
            resolved = p.resolve()
        except OSError:
            errors += 1
            continue
        if resolved in referenced:
            skipped_referenced += 1
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            errors += 1
            continue
        if mtime < since_ts:
            skipped_old += 1
            continue
        try:
            p.unlink()
            deleted += 1
            print(f"[orphan_cleanup] 删除 {p}")
        except OSError as e:
            errors += 1
            print(f"[orphan_cleanup] 删除失败 {p}: {e}")

    return {
        "deleted": deleted,
        "skipped_referenced": skipped_referenced,
        "skipped_old": skipped_old,
        "errors": errors,
    }


async def cleanup_task_orphan_media(
    task_id: int,
    since: Optional[datetime] = None,
) -> dict:
    refs = await referenced_paths_for_task(task_id)
    summary = cleanup_task_orphan_media_sync(refs, since)
    print(
        f"[orphan_cleanup] task=#{task_id} deleted={summary['deleted']} "
        f"kept_ref={summary['skipped_referenced']} old={summary['skipped_old']} "
        f"errors={summary['errors']}"
    )
    return summary


def cleanup_slug_media(slug: str, segment_path: str | Path | None = None) -> int:
    """删除某次采集 slug 相关截图，以及可选的录屏/音频文件。"""
    if not slug:
        return 0
    deleted = 0
    shot_dir = Path(SCREENSHOTS_DIR)
    if shot_dir.is_dir():
        for p in shot_dir.glob(f"*{slug}*"):
            if not p.is_file():
                continue
            try:
                p.unlink()
                deleted += 1
                print(f"[orphan_cleanup] slug删截图 {p.name}")
            except OSError as e:
                print(f"[orphan_cleanup] slug删失败 {p}: {e}")

    paths: list[Path] = []
    if segment_path:
        vp = Path(segment_path)
        paths.append(vp)
        # 常见衍生 wav
        paths.append(vp.with_suffix(".wav"))
        paths.append(Path(str(vp) + ".wav"))
    for p in paths:
        try:
            if p.is_file():
                p.unlink()
                deleted += 1
                print(f"[orphan_cleanup] slug删录屏 {p}")
        except OSError as e:
            print(f"[orphan_cleanup] slug删录屏失败 {p}: {e}")
    return deleted
