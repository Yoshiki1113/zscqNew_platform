"""API 路由 — 复核管理"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, update
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
    """更新单条复核状态"""
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

    # 记录操作日志
    log = ReviewLog(
        evidence_id=evidence_id,
        previous_status=previous,
        new_status=body.review_status,
        reviewer=body.reviewer,
        notes=body.review_notes,
    )
    db.add(log)
    await db.commit()

    return {"status": "ok", "previous": previous, "new": body.review_status}


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
