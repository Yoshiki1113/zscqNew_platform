"""API 路由 — 证据查询"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import EvidenceRecord, Task

router = APIRouter(tags=["证据查询"])


def _parse_json_safe(raw: str) -> list:
    try:
        return json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []


class EvidenceListResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    stats: dict = {}

    model_config = {"from_attributes": True}


def _record_to_list_item(r: EvidenceRecord) -> dict:
    """轻量版：仅返回列表卡片需要的字段，跳过 asr_text、script_match_segments 等重数据"""
    return {
        "id": r.id,
        "task_id": r.task_id,
        "search_keyword": r.search_keyword or "",
        "blogger_name": r.blogger_name or "",
        "video_channel_id": r.video_channel_id or "",
        "title": r.title or "",
        "video_link": r.video_link or "",
        "like_count": r.like_count or "",
        "comment_count": r.comment_count or "",
        "share_count": r.share_count or "",
        "company_full_name": r.company_full_name or "",
        # 引流信息
        "has_traffic_marker": r.has_traffic_marker or False,
        "traffic_marker_text": r.traffic_marker_text or "",
        "traffic_video_name": r.traffic_video_name or "",
        "target_blogger_name": r.target_blogger_name or "",
        # 侵权评分
        "infringement_score": r.infringement_score or 0.0,
        "infringement_level": r.infringement_level or "",
        "infringement_reason": r.infringement_reason or "",
        # 证据文件（screenshots 需要用于缩略图，但不做 JSON 解析）
        "screenshots": r.screenshots,
        # 复核
        "review_status": r.review_status or "",
        "pushed_to_police": bool(getattr(r, "pushed_to_police", False)),
        "pushed_at": str(r.pushed_at) if getattr(r, "pushed_at", None) else "",
        "pushed_to_company": bool(getattr(r, "pushed_to_company", False)),
        "pushed_to_company_at": str(r.pushed_to_company_at) if getattr(r, "pushed_to_company_at", None) else "",
        # 时间
        "capture_timestamp": r.capture_timestamp or "",
        "created_at": str(r.created_at) if r.created_at else "",
    }


def _record_to_dict(r: EvidenceRecord) -> dict:
    """完整版：详情页使用"""
    return {
        "id": r.id,
        "task_id": r.task_id,
        "search_keyword": r.search_keyword or "",
        "video_identifier": r.video_identifier or "",
        "fingerprint": r.fingerprint or "",
        "blogger_name": r.blogger_name or "",
        "video_channel_id": r.video_channel_id or "",
        "video_channel_id_raw": r.video_channel_id_raw or "",
        "video_channel_id_needs_review": r.video_channel_id_needs_review or False,
        "title": r.title or "",
        "video_link": r.video_link or "",
        "publish_time": r.publish_time or "",
        "like_count": r.like_count or "",
        "comment_count": r.comment_count or "",
        "share_count": r.share_count or "",
        "favorite_count": r.favorite_count or "",
        "profile_name": r.profile_name or "",
        "profile_account": r.profile_account or "",
        "subject_type": r.subject_type or "",
        "company_full_name": r.company_full_name or "",
        "has_traffic_marker": r.has_traffic_marker or False,
        "traffic_marker_text": r.traffic_marker_text or "",
        "traffic_video_name": r.traffic_video_name or "",
        "target_blogger_name": r.target_blogger_name or "",
        "target_video_channel_id": r.target_video_channel_id or "",
        "target_video_channel_id_raw": r.target_video_channel_id_raw or "",
        "target_company_name": r.target_company_name or "",
        "target_company_verified_at": r.target_company_verified_at or "",
        "asr_text": r.asr_text or "",
        "asr_model": r.asr_model or "",
        "script_match_status": r.script_match_status or "",
        "script_match_similarity": r.script_match_similarity or 0.0,
        "script_match_pinyin_score": r.script_match_pinyin_score or 0.0,
        "script_match_char_score": r.script_match_char_score or 0.0,
        "script_match_segments_matched": r.script_match_segments_matched or 0,
        "script_match_segments_total": r.script_match_segments_total or 0,
        "script_match_episode": r.script_match_episode or "",
        "script_match_scene": r.script_match_scene or "",
        "script_match_character": r.script_match_character or "",
        "script_match_location": r.script_match_location or "",
        "script_match_script_text": r.script_match_script_text or "",
        "script_match_segments": _parse_json_safe(r.script_match_segments_json),
        "infringement_score": r.infringement_score or 0.0,
        "infringement_level": r.infringement_level or "",
        "infringement_reason": r.infringement_reason or "",
        "recording_video_path": r.recording_video_path or "",
        "recording_audio_path": r.recording_audio_path or "",
        "recording_duration_seconds": r.recording_duration_seconds or 0,
        "has_audio": r.has_audio or False,
        "screenshots": r.screenshots,
        "json_path": r.json_path or "",
        "html_path": r.html_path or "",
        "review_status": r.review_status or "",
        "reviewer": r.reviewer or "",
        "review_notes": r.review_notes or "",
        "reviewed_at": str(r.reviewed_at) if r.reviewed_at else "",
        "pushed_to_police": bool(getattr(r, "pushed_to_police", False)),
        "pushed_at": str(r.pushed_at) if getattr(r, "pushed_at", None) else "",
        "pushed_to_company": bool(getattr(r, "pushed_to_company", False)),
        "pushed_to_company_at": str(r.pushed_to_company_at) if getattr(r, "pushed_to_company_at", None) else "",
        "pushed_by": getattr(r, "pushed_by", "") or "",
        "pushed_to_company_by": getattr(r, "pushed_to_company_by", "") or "",
        "capture_timestamp": r.capture_timestamp or "",
        "created_at": str(r.created_at) if r.created_at else "",
    }


@router.get("/evidence", response_model=EvidenceListResponse)
async def list_evidence(
    review_status: str = Query("", max_length=20),
    keyword: str = Query("", max_length=200),
    blogger: str = Query("", max_length=200),
    task_id: int = Query(0, ge=0),
    work_order_id: int = Query(0, ge=0),
    pushed_only: bool = Query(False),
    company_pool_only: bool = Query(False),
    review_pending: bool = Query(False),
    phase: int = Query(0, ge=0, le=2),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """证据列表（分页 + 多条件筛选，支持按 task_id 筛选）"""
    base = select(EvidenceRecord)
    count_base = select(func.count(EvidenceRecord.id))

    # 列表筛选条件（审核状态、关键词、博主、任务）
    filters = []
    if review_status:
        filters.append(EvidenceRecord.review_status == review_status)
    if keyword:
        filters.append(EvidenceRecord.search_keyword.like(f"%{keyword}%"))
    if blogger:
        filters.append(EvidenceRecord.blogger_name.like(f"%{blogger}%"))
    if task_id:
        filters.append(EvidenceRecord.task_id == task_id)
    if work_order_id:
        task_ids_subq = select(Task.id).where(Task.work_order_id == work_order_id)
        filters.append(EvidenceRecord.task_id.in_(task_ids_subq))
    if pushed_only:
        filters.append(EvidenceRecord.pushed_to_police == True)
    if company_pool_only:
        filters.append(EvidenceRecord.pushed_to_company == True)
    if review_pending:
        filters.append(EvidenceRecord.review_status == "")
    if phase:
        task_ids_phase = select(Task.id).where(Task.phase == phase)
        filters.append(EvidenceRecord.task_id.in_(task_ids_phase))

    for f in filters:
        base = base.where(f)
        count_base = count_base.where(f)

    base = base.order_by(EvidenceRecord.created_at.desc(), EvidenceRecord.id.desc())

    # 统计查询：和列表用同一套筛选，动态反映当前筛选结果
    from sqlalchemy import case
    combined_q = select(
        func.count(EvidenceRecord.id).label("total"),
        func.sum(case((EvidenceRecord.review_status == "侵权", 1), else_=0)).label("infringement"),
        func.sum(case((EvidenceRecord.infringement_level.in_(["高度疑似", "侵权"]), 1), else_=0)).label("high"),
        func.sum(case((EvidenceRecord.infringement_level == "疑似", 1), else_=0)).label("mid"),
        func.sum(case((EvidenceRecord.infringement_level == "待观察", 1), else_=0)).label("low"),
    )
    for f in filters:
        combined_q = combined_q.where(f)

    # 同一个 AsyncSession 不支持并发查询，改为顺序执行
    rows_result = await db.execute(base.offset((page - 1) * page_size).limit(page_size))
    stats_result = await db.execute(combined_q)
    rows = rows_result.scalars().all()
    stats_row = stats_result.first()

    total = stats_row.total if stats_row else 0

    return EvidenceListResponse(
        items=[_record_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        stats={
            "total": stats_row.total if stats_row else 0,
            "infringement": stats_row.infringement or 0,
            "high": stats_row.high or 0,
            "mid": stats_row.mid or 0,
            "low": stats_row.low or 0,
        } if stats_row else {},
    )


class RematchScriptsRequest(BaseModel):
    work_order_id: Optional[int] = Field(None, ge=1)
    task_id: Optional[int] = Field(None, ge=1)
    keyword: str = Field("", max_length=200)


def _apply_evidence_scope_filters(q, body: RematchScriptsRequest):
    if body.task_id:
        q = q.where(EvidenceRecord.task_id == body.task_id)
    if body.work_order_id:
        task_ids_subq = select(Task.id).where(Task.work_order_id == body.work_order_id)
        q = q.where(EvidenceRecord.task_id.in_(task_ids_subq))
    if body.keyword and body.keyword.strip():
        q = q.where(EvidenceRecord.search_keyword.like(f"%{body.keyword.strip()}%"))
    return q


def _has_media_or_asr_clause():
    """已有 ASR，或有录屏/音频路径可转写。"""
    return or_(
        and_(EvidenceRecord.asr_text.is_not(None), EvidenceRecord.asr_text != ""),
        and_(
            EvidenceRecord.recording_audio_path.is_not(None),
            EvidenceRecord.recording_audio_path != "",
        ),
        and_(
            EvidenceRecord.recording_video_path.is_not(None),
            EvidenceRecord.recording_video_path != "",
        ),
    )


@router.post("/evidence/rematch-scripts")
async def rematch_scripts(
    body: RematchScriptsRequest = RematchScriptsRequest(),
    db: AsyncSession = Depends(get_db),
):
    """一键补台词比对：无 ASR 先转写再比对；有 ASR 则直接按剧名比对。"""
    from engine.script_rematch import rematch_evidence_rows

    q = _pending_rematch_query(body)
    rows = list((await db.execute(q.order_by(EvidenceRecord.id.asc()))).scalars().all())
    if not rows:
        return {
            "total_candidates": 0,
            "matched": 0,
            "not_found": 0,
            "still_unavailable": 0,
            "skipped_no_asr": 0,
            "skipped_no_keyword": 0,
            "transcribed": 0,
            "error": 0,
            "message": "没有需要补比对的证据",
        }

    summary = await asyncio.to_thread(rematch_evidence_rows, rows)
    await db.commit()

    parts = [
        f"候选 {summary['total_candidates']} 条",
        f"匹配 {summary['matched']}",
        f"未命中 {summary['not_found']}",
        f"仍缺台词 {summary['still_unavailable']}",
    ]
    if summary.get("transcribed"):
        parts.append(f"补转写 {summary['transcribed']}")
    if summary.get("skipped_no_asr"):
        parts.append(f"转写失败 {summary['skipped_no_asr']}")
    if summary.get("skipped_no_keyword"):
        parts.append(f"缺关键词 {summary['skipped_no_keyword']}")
    if summary.get("error"):
        parts.append(f"异常 {summary['error']}")
    summary["message"] = "补比对完成：" + "，".join(parts)
    return summary


def _pending_rematch_query(body: RematchScriptsRequest):
    from engine.script_rematch import REMATCH_STATUSES

    q = select(EvidenceRecord).where(
        or_(
            EvidenceRecord.script_match_status.in_(list(REMATCH_STATUSES)),
            EvidenceRecord.script_match_status.is_(None),
        ),
        _has_media_or_asr_clause(),
    )
    return _apply_evidence_scope_filters(q, body)


@router.post("/evidence/rematch-scripts/candidates")
async def rematch_scripts_candidates(
    body: RematchScriptsRequest = RematchScriptsRequest(),
    db: AsyncSession = Depends(get_db),
):
    """返回待台词比对的证据 id 列表（不跑比对），供前端逐条进度调用。"""
    q = _pending_rematch_query(body)
    rows = list((await db.execute(q.order_by(EvidenceRecord.id.asc()))).scalars().all())
    ids = [r.id for r in rows]
    return {
        "total": len(ids),
        "ids": ids,
        "message": f"待比对 {len(ids)} 条" if ids else "没有需要补比对的证据",
    }


@router.post("/evidence/batch-asr")
async def batch_asr(
    body: RematchScriptsRequest = RematchScriptsRequest(),
    db: AsyncSession = Depends(get_db),
):
    """一键 ASR 转写：对无转写文本且有媒体的证据只跑讯飞转写，不做台词比对。"""
    from engine.script_rematch import batch_asr_evidence_rows

    q = select(EvidenceRecord).where(
        or_(EvidenceRecord.asr_text.is_(None), EvidenceRecord.asr_text == ""),
        or_(
            and_(
                EvidenceRecord.recording_audio_path.is_not(None),
                EvidenceRecord.recording_audio_path != "",
            ),
            and_(
                EvidenceRecord.recording_video_path.is_not(None),
                EvidenceRecord.recording_video_path != "",
            ),
        ),
    )
    q = _apply_evidence_scope_filters(q, body)

    rows = list((await db.execute(q.order_by(EvidenceRecord.id.asc()))).scalars().all())
    if not rows:
        return {
            "total": 0,
            "transcribed": 0,
            "skipped_no_media": 0,
            "skipped_has_asr": 0,
            "error": 0,
            "message": "没有需要转写的证据",
        }

    summary = await asyncio.to_thread(batch_asr_evidence_rows, rows)
    await db.commit()

    parts = [
        f"候选 {summary['total']} 条",
        f"成功 {summary['transcribed']}",
    ]
    if summary.get("skipped_no_media"):
        parts.append(f"无可用媒体 {summary['skipped_no_media']}")
    if summary.get("error"):
        parts.append(f"异常 {summary['error']}")
    summary["message"] = "ASR 转写完成：" + "，".join(parts)
    return summary


def _pending_asr_query(body: RematchScriptsRequest):
    q = select(EvidenceRecord).where(
        or_(EvidenceRecord.asr_text.is_(None), EvidenceRecord.asr_text == ""),
        or_(
            and_(
                EvidenceRecord.recording_audio_path.is_not(None),
                EvidenceRecord.recording_audio_path != "",
            ),
            and_(
                EvidenceRecord.recording_video_path.is_not(None),
                EvidenceRecord.recording_video_path != "",
            ),
        ),
    )
    return _apply_evidence_scope_filters(q, body)


@router.post("/evidence/batch-asr/candidates")
async def batch_asr_candidates(
    body: RematchScriptsRequest = RematchScriptsRequest(),
    db: AsyncSession = Depends(get_db),
):
    """返回待 ASR 的证据 id 列表（不跑转写），供前端逐条进度调用。"""
    q = _pending_asr_query(body)
    rows = list((await db.execute(q.order_by(EvidenceRecord.id.asc()))).scalars().all())
    ids = [r.id for r in rows]
    return {
        "total": len(ids),
        "ids": ids,
        "message": f"待转写 {len(ids)} 条" if ids else "没有需要转写的证据",
    }


@router.post("/evidence/{evidence_id}/asr")
async def asr_one_evidence(evidence_id: int, db: AsyncSession = Depends(get_db)):
    """单条证据 ASR 转写（无比对）。"""
    from engine.script_rematch import transcribe_evidence_row

    row = (await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id == evidence_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "证据不存在")

    if (row.asr_text or "").strip():
        return {
            "ok": True,
            "skipped": True,
            "evidence_id": evidence_id,
            "message": "已有 ASR，跳过",
        }

    text = await asyncio.to_thread(transcribe_evidence_row, row)
    if not text:
        await db.commit()  # 可能写了 recording_audio_path
        return {
            "ok": False,
            "skipped": False,
            "evidence_id": evidence_id,
            "message": "转写失败或无可用媒体",
        }
    await db.commit()
    return {
        "ok": True,
        "skipped": False,
        "evidence_id": evidence_id,
        "asr_len": len(text),
        "message": "转写成功",
    }


@router.post("/evidence/{evidence_id}/rematch-script")
async def rematch_one_evidence(evidence_id: int, db: AsyncSession = Depends(get_db)):
    """单条证据台词比对（无 ASR 时会先补转写）。"""
    from engine.script_rematch import rematch_evidence_rows

    row = (await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id == evidence_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "证据不存在")

    summary = await asyncio.to_thread(rematch_evidence_rows, [row])
    await db.commit()
    await db.refresh(row)

    st = (row.script_match_status or "").strip()
    failed = bool(
        summary.get("skipped_no_asr")
        or summary.get("skipped_no_keyword")
        or summary.get("error")
    )
    return {
        "ok": not failed,
        "evidence_id": evidence_id,
        "script_match_status": st,
        "script_match_similarity": float(row.script_match_similarity or 0),
        "summary": summary,
        "message": f"比对完成: {st or 'unknown'}",
    }


@router.get("/evidence/{evidence_id}")
async def get_evidence(evidence_id: int, db: AsyncSession = Depends(get_db)):
    """证据详情"""
    row = (await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id == evidence_id)
    )).scalar_one_or_none()

    if not row:
        raise HTTPException(404, "证据不存在")

    return _record_to_dict(row)


class PushEvidenceRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1)
    pushed_by: str = Field("取证员", max_length=100)


class PushCompanyAllRequest(BaseModel):
    pushed_by: str = Field("取证员", max_length=100)
    task_id: Optional[int] = Field(None, ge=1)
    work_order_id: Optional[int] = Field(None, ge=1)


@router.post("/evidence/push-company-all")
async def push_all_evidence_to_company(
    body: PushCompanyAllRequest,
    db: AsyncSession = Depends(get_db),
):
    """取证端：一键推送全部未推送的二阶段证据至公司核查池"""
    phase2_ids = select(Task.id).where(Task.phase == 2)
    if body.task_id:
        phase2_ids = select(Task.id).where(Task.id == body.task_id, Task.phase == 2)
    elif body.work_order_id:
        phase2_ids = select(Task.id).where(
            Task.work_order_id == body.work_order_id,
            Task.phase == 2,
        )

    q = select(EvidenceRecord).where(
        EvidenceRecord.task_id.in_(phase2_ids),
        EvidenceRecord.pushed_to_company == False,
    )
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return {"updated": 0, "skipped": 0, "total": 0, "message": "没有待推送的二阶段证据"}

    now = datetime.now()
    updated = 0
    work_order_ids: set[int] = set()
    for r in rows:
        r.pushed_to_company = True
        r.pushed_to_company_at = now
        r.pushed_to_company_by = body.pushed_by
        updated += 1
        task = (await db.execute(select(Task).where(Task.id == r.task_id))).scalar_one_or_none()
        if task:
            from api.work_orders import ensure_task_work_order_id
            woid = await ensure_task_work_order_id(db, task)
            if woid:
                work_order_ids.add(woid)

    await db.commit()
    from api.work_orders import _refresh_work_order_stats
    for woid in work_order_ids:
        await _refresh_work_order_stats(db, woid)
    await db.commit()

    return {
        "updated": updated,
        "skipped": 0,
        "total": updated,
        "message": f"已一键推送 {updated} 条至公司核查池",
    }


@router.post("/evidence/push-company")
async def push_evidence_to_company(body: PushEvidenceRequest, db: AsyncSession = Depends(get_db)):
    """取证端：推送二阶段证据至公司核查池"""
    now = datetime.now()
    result = await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id.in_(body.ids))
    )
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(404, "未找到证据记录")

    updated = 0
    skipped = 0
    work_order_ids: set[int] = set()
    for r in rows:
        if r.pushed_to_company:
            continue
        task = (await db.execute(select(Task).where(Task.id == r.task_id))).scalar_one_or_none()
        if not task or (task.phase or 1) != 2:
            skipped += 1
            continue
        r.pushed_to_company = True
        r.pushed_to_company_at = now
        r.pushed_to_company_by = body.pushed_by
        updated += 1
        from api.work_orders import ensure_task_work_order_id
        woid = await ensure_task_work_order_id(db, task)
        if woid:
            work_order_ids.add(woid)

    if updated == 0 and skipped > 0:
        raise HTTPException(400, "仅二阶段任务产出的证据可推送公司核查池")

    await db.commit()

    from api.work_orders import _refresh_work_order_stats
    for woid in work_order_ids:
        await _refresh_work_order_stats(db, woid)
    await db.commit()

    return {"updated": updated, "skipped": skipped, "total": len(body.ids)}


@router.post("/evidence/push")
async def push_evidence_to_police(body: PushEvidenceRequest, db: AsyncSession = Depends(get_db)):
    """取证端：推送证据至公安线索池（平台内可见）"""
    now = datetime.now()
    result = await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id.in_(body.ids))
    )
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(404, "未找到证据记录")

    updated = 0
    work_order_ids: set[int] = set()
    for r in rows:
        if r.pushed_to_police:
            continue
        if not r.pushed_to_company or r.review_status != "侵权":
            continue
        r.pushed_to_police = True
        r.pushed_at = now
        r.pushed_by = body.pushed_by
        updated += 1
        task = (await db.execute(select(Task).where(Task.id == r.task_id))).scalar_one_or_none()
        if task and task.work_order_id:
            work_order_ids.add(task.work_order_id)

    if updated == 0:
        raise HTTPException(400, "仅「已送核查池且公司标侵权」的证据可推送公安")

    await db.commit()

    from api.work_orders import _refresh_work_order_stats
    for woid in work_order_ids:
        await _refresh_work_order_stats(db, woid)
    await db.commit()

    return {"updated": updated, "total": len(body.ids)}
