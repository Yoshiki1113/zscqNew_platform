"""API 路由 — 证据查询"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import EvidenceRecord

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
        "capture_timestamp": r.capture_timestamp or "",
        "created_at": str(r.created_at) if r.created_at else "",
    }


@router.get("/evidence", response_model=EvidenceListResponse)
async def list_evidence(
    review_status: str = Query("", max_length=20),
    keyword: str = Query("", max_length=200),
    blogger: str = Query("", max_length=200),
    task_id: int = Query(0, ge=0),
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


@router.get("/evidence/{evidence_id}")
async def get_evidence(evidence_id: int, db: AsyncSession = Depends(get_db)):
    """证据详情"""
    row = (await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id == evidence_id)
    )).scalar_one_or_none()

    if not row:
        raise HTTPException(404, "证据不存在")

    return _record_to_dict(row)
