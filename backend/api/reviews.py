"""API 路由 — 复核管理"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import EvidenceRecord, ReviewLog

router = APIRouter(tags=["复核管理"])


class ReviewUpdate(BaseModel):
    review_status: str = Field(..., pattern="^(侵权|未侵权|)$")
    reviewer: str = Field("", max_length=100)
    review_notes: str = Field("", max_length=2000)


class BatchReviewUpdate(BaseModel):
    evidence_ids: list[int] = Field(..., min_length=1)
    review_status: str = Field(..., pattern="^(侵权|未侵权|)$")
    reviewer: str = Field("", max_length=100)
    review_notes: str = Field("", max_length=2000)


@router.get("/reviews/pool")
async def review_pool(
    keyword: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
):
    """待复核池列表"""
    base = select(EvidenceRecord).where(EvidenceRecord.review_status == "")
    count_base = select(func.count(EvidenceRecord.id)).where(
        EvidenceRecord.review_status == ""
    )

    if keyword:
        base = base.where(EvidenceRecord.search_keyword.like(f"%{keyword}%"))
        count_base = count_base.where(EvidenceRecord.search_keyword.like(f"%{keyword}%"))

    base = base.order_by(EvidenceRecord.created_at.desc())

    total = (await db.execute(count_base)).scalar() or 0
    rows = (await db.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars().all()

    from api.evidence import _record_to_dict
    return {
        "items": [_record_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("/reviews/{evidence_id}")
async def update_review(evidence_id: int, body: ReviewUpdate, db: AsyncSession = Depends(get_db)):
    """更新单条复核状态；响应附带同剧同博主可同步条目。"""
    row = (await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id == evidence_id)
    )).scalar_one_or_none()

    if not row:
        raise HTTPException(404, "证据不存在")

    previous = row.review_status
    row.review_status = body.review_status
    row.reviewer = body.reviewer
    row.review_notes = body.review_notes
    row.reviewed_at = datetime.now()

    log = ReviewLog(
        evidence_id=evidence_id,
        previous_status=previous,
        new_status=body.review_status,
        reviewer=body.reviewer,
        notes=body.review_notes,
    )
    db.add(log)
    await db.commit()

    peers = await _find_review_peers(db, row, body.review_status)
    return {
        "status": "ok",
        "previous": previous,
        "new": body.review_status,
        "peer_count": len(peers),
        "peer_ids": peers,
    }


async def _find_review_peers(
    db: AsyncSession,
    row: EvidenceRecord,
    target_status: str,
) -> list[int]:
    """同剧(search_keyword) + 同博主(channel_id 优先，否则 blogger_name)，且尚未为目标状态的其它证据。"""
    keyword = (row.search_keyword or "").strip()
    if not keyword or not target_status:
        return []

    channel = (row.video_channel_id or "").strip()
    blogger = (row.blogger_name or "").strip()

    q = select(EvidenceRecord.id).where(
        EvidenceRecord.id != row.id,
        EvidenceRecord.search_keyword == keyword,
        or_(
            EvidenceRecord.review_status.is_(None),
            EvidenceRecord.review_status != target_status,
        ),
    )
    if channel:
        q = q.where(EvidenceRecord.video_channel_id == channel)
    elif blogger:
        q = q.where(EvidenceRecord.blogger_name == blogger)
    else:
        return []

    ids = list((await db.execute(q.order_by(EvidenceRecord.id.asc()))).scalars().all())
    return [int(i) for i in ids]


@router.get("/reviews/peers")
async def list_review_peers(
    evidence_id: int = Query(..., ge=1),
    status: str = Query(..., pattern="^(侵权|未侵权)$"),
    db: AsyncSession = Depends(get_db),
):
    """查询同剧同博主、尚未标记为目标状态的其它证据 id。"""
    row = (await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id == evidence_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "证据不存在")
    peers = await _find_review_peers(db, row, status)
    return {"peer_count": len(peers), "peer_ids": peers}


@router.post("/reviews/batch")
async def batch_update_review(body: BatchReviewUpdate, db: AsyncSession = Depends(get_db)):
    """批量更新复核状态"""
    rows = (await db.execute(
        select(EvidenceRecord).where(EvidenceRecord.id.in_(body.evidence_ids))
    )).scalars().all()

    updated = 0
    for row in rows:
        previous = row.review_status
        row.review_status = body.review_status
        row.reviewer = body.reviewer
        row.review_notes = body.review_notes
        row.reviewed_at = datetime.now()

        db.add(ReviewLog(
            evidence_id=row.id,
            previous_status=previous,
            new_status=body.review_status,
            reviewer=body.reviewer,
            notes=body.review_notes,
        ))
        updated += 1

    await db.commit()
    return {"status": "ok", "updated_count": updated}
