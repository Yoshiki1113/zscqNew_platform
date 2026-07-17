"""API 路由 — 链接池（批次管理）"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import DEFAULT_HOLD_SECONDS, DEFAULT_CAPTURE_METHOD
from database import get_db
from models import Task, VideoLink, InfringementClue, LinkBatch

router = APIRouter(tags=["链接池"])


class CreateFromPoolRequest(BaseModel):
    batch_ids: list[int] = Field(..., min_length=1, max_length=50)
    keyword: str = ""
    device_id: str = Field("", max_length=100)
    hold_seconds: int = Field(DEFAULT_HOLD_SECONDS, ge=30, le=3600)
    capture_method: str = Field(DEFAULT_CAPTURE_METHOD, pattern="^(scrcpy)$")
    enable_asr: bool = Field(True)
    work_order_id: Optional[int] = Field(None, ge=1)


# ── 批次列表 ──

@router.get("/link-pool/batches")
async def list_batches(db: AsyncSession = Depends(get_db)):
    """列出所有链接批次"""
    result = await db.execute(
        select(LinkBatch).order_by(LinkBatch.created_at.desc())
    )
    batches = result.scalars().all()

    # 统计每个批次未采集的链接数（一次 GROUP BY 查询）
    pending_counts = {}
    if batches:
        batch_ids = [b.id for b in batches]
        count_rows = (await db.execute(
            select(VideoLink.batch_id, func.count(VideoLink.id)).where(
                VideoLink.batch_id.in_(batch_ids),
                VideoLink.evidence_record_id.is_(None),
            ).group_by(VideoLink.batch_id)
        )).all()
        pending_counts = {row[0]: row[1] for row in count_rows}

    items = []
    for b in batches:
        items.append({
            "id": b.id,
            "name": b.name,
            "source": b.source,
            "task_id": b.task_id,
            "total_count": b.total_count,
            "pending_count": pending_counts.get(b.id, 0),
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })

    # 统计线索中可导入的微信链接数
    clue_result = await db.execute(
        select(func.count(InfringementClue.id)).where(
            InfringementClue.video_link != "",
            InfringementClue.video_link.isnot(None),
            InfringementClue.video_link.contains("weixin.qq.com"),
        )
    )
    clue_count = clue_result.scalar() or 0

    return {
        "batches": items,
        "unimported_clue_count": clue_count,
    }


# ── 批次内链接 ──

@router.get("/link-pool/batches/{batch_id}/links")
async def list_batch_links(batch_id: int, db: AsyncSession = Depends(get_db)):
    """查看某个批次内的链接列表"""
    batch = await db.get(LinkBatch, batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")

    result = await db.execute(
        select(VideoLink).where(
            VideoLink.batch_id == batch_id,
        ).order_by(VideoLink.sort_order)
    )
    links = result.scalars().all()

    return {
        "batch": {
            "id": batch.id,
            "name": batch.name,
            "source": batch.source,
            "task_id": batch.task_id,
            "total_count": batch.total_count,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
        },
        "links": [
            {
                "id": l.id,
                "link_url": l.link_url,
                "keyword": l.keyword,
                "collected": l.evidence_record_id is not None,
                "sort_order": l.sort_order,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "collected_at": l.collected_at.isoformat() if l.collected_at else None,
            }
            for l in links
        ],
    }


# ── 手动创建批次 ──

@router.post("/link-pool/batches")
async def create_manual_batch(
    name: str = "",
    db: AsyncSession = Depends(get_db),
):
    """创建手动批次"""
    if not name.strip():
        name = f"手动添加_{datetime.now().strftime('%Y-%m-%d_%H:%M')}"
    batch = LinkBatch(name=name.strip(), source="manual")
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return {"id": batch.id, "name": batch.name, "message": "批次已创建"}


# ── 删除批次 ──

@router.delete("/link-pool/batches/{batch_id}")
async def delete_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    """删除批次及其中未采集的链接（已采集的链接保留）"""
    batch = await db.get(LinkBatch, batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")

    # 删除该批次下所有未采集的链接
    from sqlalchemy import delete as sqla_delete
    result = await db.execute(
        sqla_delete(VideoLink).where(
            VideoLink.batch_id == batch_id,
            VideoLink.evidence_record_id.is_(None),
        )
    )
    deleted_links = result.rowcount or 0

    await db.delete(batch)
    await db.commit()
    return {"message": f"已删除批次「{batch.name}」及 {deleted_links} 条未采集链接"}


# ── 手动添加链接到批次 ──

@router.post("/link-pool/batches/{batch_id}/add-link")
async def add_link_to_batch(
    batch_id: int,
    link_url: str = "",
    keyword: str = "",
    db: AsyncSession = Depends(get_db),
):
    """手动添加链接到指定批次"""
    batch = await db.get(LinkBatch, batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")
    if not link_url or "weixin.qq.com" not in link_url:
        raise HTTPException(400, "请输入有效的微信视频号链接")

    link = VideoLink(
        batch_id=batch_id,
        keyword=keyword or "手动添加",
        link_url=link_url.strip(),
        sort_order=batch.total_count + 1,
    )
    db.add(link)
    batch.total_count += 1
    await db.commit()
    return {"id": link.id, "message": "已添加"}


# ── 从线索导入到批次 ──

@router.post("/link-pool/import-from-clues")
async def import_from_clues(
    batch_name: str = "",
    db: AsyncSession = Depends(get_db),
):
    """从侵权线索导入链接到新批次"""
    if not batch_name.strip():
        raise HTTPException(400, "请为导入批次命名（如：侵权线索_2026年7月）")

    clues_result = await db.execute(
        select(InfringementClue).where(
            InfringementClue.video_link != "",
            InfringementClue.video_link.isnot(None),
        ).order_by(InfringementClue.id)
    )
    clues = clues_result.scalars().all()
    if not clues:
        raise HTTPException(400, "没有找到包含视频链接的侵权线索")

    batch = LinkBatch(name=batch_name.strip(), source="imported")
    db.add(batch)
    await db.flush()

    skipped_non_weixin = 0
    for idx, clue in enumerate(clues, 1):
        if "weixin.qq.com" not in (clue.video_link or ""):
            skipped_non_weixin += 1
            continue
        link = VideoLink(
            batch_id=batch.id,
            keyword=clue.our_work_name or clue.work_name or "",
            link_url=clue.video_link,
            sort_order=idx,
        )
        db.add(link)

    batch.total_count = len(clues) - skipped_non_weixin
    await db.commit()
    await db.refresh(batch)
    return {
        "id": batch.id,
        "name": batch.name,
        "imported_count": batch.total_count,
        "skipped_non_weixin": skipped_non_weixin,
        "message": f"已导入 {batch.total_count} 条链接到批次「{batch.name}」" +
                   (f"，跳过 {skipped_non_weixin} 条非微信链接" if skipped_non_weixin else ""),
    }


# ── 从批次创建 Phase 2 任务 ──

@router.post("/link-pool/create-task")
async def create_task_from_pool(
    body: CreateFromPoolRequest,
    db: AsyncSession = Depends(get_db),
):
    """从选中的批次创建 Phase 2 任务"""
    # 验证所有批次存在
    total_links = 0
    for bid in body.batch_ids:
        batch = await db.get(LinkBatch, bid)
        if not batch:
            raise HTTPException(404, f"批次 #{bid} 不存在")
        count = (await db.execute(
            select(func.count(VideoLink.id)).where(
                VideoLink.batch_id == bid,
                VideoLink.evidence_record_id.is_(None),
            )
        )).scalar() or 0
        total_links += count

    if total_links == 0:
        raise HTTPException(400, "所选批次中没有待处理的链接")

    # 创建任务：优先使用用户填写的名称，未填则用第一个批次名兜底
    first_batch = await db.get(LinkBatch, body.batch_ids[0])
    batch_name = first_batch.name if first_batch else "(批次导入)"
    keyword = body.keyword or batch_name

    task = Task(
        keyword=keyword,
        max_videos=total_links,
        hold_seconds=body.hold_seconds,
        capture_method=body.capture_method,
        device_id=body.device_id,
        enable_asr=body.enable_asr,
        skip_search=True,
        collect_mode="link_first",
        phase=2,
        status="links_collected",
        work_order_id=body.work_order_id,
        created_at=datetime.now(),
    )
    db.add(task)
    await db.flush()

    # 将批次中所有未采集的链接关联到任务
    import_count = 0
    for bid in body.batch_ids:
        links_result = await db.execute(
            select(VideoLink).where(
                VideoLink.batch_id == bid,
                VideoLink.evidence_record_id.is_(None),
            ).order_by(VideoLink.sort_order)
        )
        for link in links_result.scalars():
            link.task_id = task.id
            import_count += 1

    task.max_videos = import_count
    await db.commit()
    await db.refresh(task)

    return {
        "id": task.id,
        "keyword": task.keyword,
        "status": task.status,
        "max_videos": task.max_videos,
        "imported_links": import_count,
        "batch_count": len(body.batch_ids),
        "message": f"已创建任务 #{task.id}，从 {len(body.batch_ids)} 个批次导入了 {import_count} 条链接",
    }
