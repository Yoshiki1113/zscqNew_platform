"""API 路由 — 博主聚合"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import EvidenceRecord

router = APIRouter(tags=["博主聚合"])


@router.get("/authors")
async def list_authors(
    keyword: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """博主聚合列表（按 video_channel_id 实时聚合）"""
    infringe = case((EvidenceRecord.review_status == "侵权", 1), else_=0)
    whitelist = case((EvidenceRecord.review_status == "未侵权", 1), else_=0)
    uncertain = case((EvidenceRecord.review_status == "", 1), else_=0)

    filters = [EvidenceRecord.video_channel_id != ""]
    if keyword:
        filters.append(EvidenceRecord.blogger_name.like(f"%{keyword}%"))

    base = select(
        EvidenceRecord.video_channel_id,
        func.max(EvidenceRecord.blogger_name).label("blogger_name"),
        func.max(EvidenceRecord.subject_type).label("subject_type"),
        func.max(EvidenceRecord.company_full_name).label("company_full_name"),
        func.count(EvidenceRecord.id).label("total_videos"),
        func.sum(infringe).label("infringement_count"),
        func.sum(whitelist).label("whitelist_count"),
        func.sum(uncertain).label("uncertain_count"),
        func.max(EvidenceRecord.created_at).label("last_capture_time"),
    ).where(*filters).group_by(EvidenceRecord.video_channel_id).order_by(
        func.sum(infringe).desc()
    )

    # 总数（与列表相同过滤）
    count_q = select(func.count()).select_from(
        select(EvidenceRecord.video_channel_id)
        .where(*filters)
        .group_by(EvidenceRecord.video_channel_id)
        .subquery()
    )
    total = (await db.execute(count_q)).scalar() or 0

    rows = (await db.execute(base.offset((page - 1) * page_size).limit(page_size))).all()

    items = []
    for row in rows:
        items.append({
            "video_channel_id": row.video_channel_id,
            "blogger_name": row.blogger_name or "",
            "subject_type": row.subject_type or "",
            "company_full_name": row.company_full_name or "",
            "total_videos": row.total_videos or 0,
            "infringement_count": int(row.infringement_count or 0),
            "whitelist_count": int(row.whitelist_count or 0),
            "uncertain_count": int(row.uncertain_count or 0),
            "last_capture_time": str(row.last_capture_time) if row.last_capture_time else "",
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/authors/{channel_id}")
async def get_author_detail(channel_id: str, db: AsyncSession = Depends(get_db)):
    """博主详情 + 所有证据"""
    rows = (await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.video_channel_id == channel_id)
        .order_by(EvidenceRecord.created_at.desc())
    )).scalars().all()

    if not rows:
        raise HTTPException(404, "博主不存在")

    from api.evidence import _record_to_dict

    infringement = sum(1 for r in rows if r.review_status == "侵权")
    whitelist = sum(1 for r in rows if r.review_status == "未侵权")
    uncertain = sum(1 for r in rows if r.review_status == "")

    return {
        "blogger_name": rows[0].blogger_name,
        "video_channel_id": channel_id,
        "subject_type": rows[0].subject_type or "",
        "company_full_name": rows[0].company_full_name or "",
        "total_videos": len(rows),
        "infringement_count": infringement,
        "whitelist_count": whitelist,
        "uncertain_count": uncertain,
        "evidence_records": [_record_to_dict(r) for r in rows],
    }
