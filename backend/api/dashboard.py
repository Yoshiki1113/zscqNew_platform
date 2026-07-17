"""API 路由 — 公安驾驶舱统计"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import EvidenceRecord, Task, VideoLink, WorkOrder

router = APIRouter(tags=["驾驶舱"])


def _period_start(period: str) -> datetime | None:
    now = datetime.now()
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return None


@router.get("/dashboard/police")
async def police_dashboard(
    period: str = Query("all", pattern="^(all|today|7d|30d)$"),
    db: AsyncSession = Depends(get_db),
):
    since = _period_start(period)

    def _task_filter(q):
        if since:
            return q.where(Task.created_at >= since)
        return q

    def _ev_filter(q):
        if since:
            return q.where(EvidenceRecord.created_at >= since)
        return q

    task_total = (await db.execute(_task_filter(select(func.count(Task.id))))).scalar() or 0
    task_running = (
        await db.execute(
            _task_filter(select(func.count(Task.id)).where(Task.status == "running"))
        )
    ).scalar() or 0
    task_completed = (
        await db.execute(
            _task_filter(select(func.count(Task.id)).where(Task.status == "completed"))
        )
    ).scalar() or 0

    link_q = select(func.count(VideoLink.id))
    if since:
        link_q = link_q.where(VideoLink.created_at >= since)
    link_total = (await db.execute(link_q)).scalar() or 0

    ev_base = select(
        func.count(EvidenceRecord.id),
        func.sum(case((EvidenceRecord.pushed_to_police == True, 1), else_=0)),
        func.sum(case((EvidenceRecord.infringement_level.in_(["高度疑似", "侵权"]), 1), else_=0)),
        func.sum(case((EvidenceRecord.infringement_level == "疑似", 1), else_=0)),
        func.sum(case((EvidenceRecord.review_status == "侵权", 1), else_=0)),
    )
    ev_row = (await db.execute(_ev_filter(ev_base))).first()
    evidence_total = int(ev_row[0] or 0) if ev_row else 0
    pushed_total = int(ev_row[1] or 0) if ev_row else 0
    high_count = int(ev_row[2] or 0) if ev_row else 0
    mid_count = int(ev_row[3] or 0) if ev_row else 0
    infringement_reviewed = int(ev_row[4] or 0) if ev_row else 0

    # 运行时长：已完成/已停止任务累计执行秒数
    rt_rows = (
        await db.execute(
            _task_filter(
                select(Task.started_at, Task.finished_at).where(Task.started_at.isnot(None))
            )
        )
    ).all()
    runtime_seconds = 0
    for started, finished in rt_rows:
        if started:
            end = finished or datetime.now()
            runtime_seconds += max(0, int((end - started).total_seconds()))

    wo_q = select(func.count(WorkOrder.id))
    if since:
        wo_q = wo_q.where(WorkOrder.created_at >= since)
    work_order_total = (await db.execute(wo_q)).scalar() or 0

    drama_q = select(func.count(func.distinct(WorkOrder.drama_name)))
    if since:
        drama_q = drama_q.where(WorkOrder.created_at >= since)
    drama_count = (await db.execute(drama_q)).scalar() or 0

    # 近 14 日趋势
    trend = []
    for i in range(13, -1, -1):
        day = (datetime.now() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = day + timedelta(days=1)
        ev_day = (
            await db.execute(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.created_at >= day,
                    EvidenceRecord.created_at < next_day,
                )
            )
        ).scalar() or 0
        push_day = (
            await db.execute(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.pushed_to_police == True,
                    EvidenceRecord.pushed_at >= day,
                    EvidenceRecord.pushed_at < next_day,
                )
            )
        ).scalar() or 0
        company_day = (
            await db.execute(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.pushed_to_company == True,
                    EvidenceRecord.pushed_to_company_at >= day,
                    EvidenceRecord.pushed_to_company_at < next_day,
                )
            )
        ).scalar() or 0
        review_day = (
            await db.execute(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.reviewed_at >= day,
                    EvidenceRecord.reviewed_at < next_day,
                    EvidenceRecord.review_status.in_(["侵权", "未侵权"]),
                )
            )
        ).scalar() or 0
        trend.append({
            "date": day.strftime("%m-%d"),
            "evidence": ev_day,
            "pushed": push_day,
            "company_pushed": company_day,
            "company_reviewed": review_day,
        })

    # 工单状态分布
    wo_status = {"draft": 0, "submitted": 0, "collecting": 0, "partial": 0, "completed": 0, "closed": 0}
    wo_status_q = select(WorkOrder.status, func.count(WorkOrder.id)).group_by(WorkOrder.status)
    if since:
        wo_status_q = wo_status_q.where(WorkOrder.created_at >= since)
    for st, cnt in (await db.execute(wo_status_q)).all():
        if st in wo_status:
            wo_status[st] = int(cnt or 0)

    # 低等级观察
    low_count = (
        await db.execute(
            _ev_filter(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.infringement_level == "待观察"
                )
            )
        )
    ).scalar() or 0

    # 公司核查池待复核（已推公司、未标结论）
    company_pending = (
        await db.execute(
            select(func.count(EvidenceRecord.id)).where(
                EvidenceRecord.pushed_to_company == True,
                EvidenceRecord.review_status == "",
            )
        )
    ).scalar() or 0

    # 取证→公司→公安 链路统计
    company_pushed_total = (
        await db.execute(
            _ev_filter(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.pushed_to_company == True
                )
            )
        )
    ).scalar() or 0
    company_reviewed_ok = (
        await db.execute(
            _ev_filter(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.pushed_to_company == True,
                    EvidenceRecord.review_status == "侵权",
                )
            )
        )
    ).scalar() or 0
    company_reviewed_no = (
        await db.execute(
            _ev_filter(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.pushed_to_company == True,
                    EvidenceRecord.review_status == "未侵权",
                )
            )
        )
    ).scalar() or 0

    # 最近操作动态（取证推公司 / 公司复核 / 推公安）
    recent_activity = []
    # 推送公司
    for r in (
        await db.execute(
            select(EvidenceRecord)
            .where(EvidenceRecord.pushed_to_company == True)
            .order_by(EvidenceRecord.pushed_to_company_at.desc())
            .limit(8)
        )
    ).scalars().all():
        recent_activity.append({
            "type": "push_company",
            "label": "取证推送公司核查",
            "evidence_id": r.id,
            "title": r.title or "无标题",
            "actor": r.pushed_to_company_by or "取证员",
            "time": str(r.pushed_to_company_at) if r.pushed_to_company_at else "",
        })
    # 公司复核
    for r in (
        await db.execute(
            select(EvidenceRecord)
            .where(EvidenceRecord.reviewed_at.isnot(None), EvidenceRecord.review_status != "")
            .order_by(EvidenceRecord.reviewed_at.desc())
            .limit(8)
        )
    ).scalars().all():
        recent_activity.append({
            "type": "company_review",
            "label": f"公司复核：{r.review_status}",
            "evidence_id": r.id,
            "title": r.title or "无标题",
            "actor": r.reviewer or "公司用户",
            "time": str(r.reviewed_at) if r.reviewed_at else "",
            "status": r.review_status,
        })
    # 推送公安
    for r in (
        await db.execute(
            select(EvidenceRecord)
            .where(EvidenceRecord.pushed_to_police == True)
            .order_by(EvidenceRecord.pushed_at.desc())
            .limit(8)
        )
    ).scalars().all():
        recent_activity.append({
            "type": "push_police",
            "label": "推送公安线索",
            "evidence_id": r.id,
            "title": r.title or "无标题",
            "actor": r.pushed_by or "取证员",
            "time": str(r.pushed_at) if r.pushed_at else "",
        })
    recent_activity.sort(key=lambda x: x.get("time") or "", reverse=True)
    recent_activity = recent_activity[:12]

    # 最近推送公安的证据（缩略图墙）
    recent_pushed = []
    rp_rows = (
        await db.execute(
            select(EvidenceRecord)
            .where(EvidenceRecord.pushed_to_police == True)
            .order_by(EvidenceRecord.pushed_at.desc(), EvidenceRecord.id.desc())
            .limit(4)
        )
    ).scalars().all()
    for r in rp_rows:
        shots = r.screenshots or []
        thumb = ""
        if shots:
            s0 = shots[0]
            thumb = s0 if isinstance(s0, str) else (s0.get("path") if isinstance(s0, dict) else "")
        recent_pushed.append({
            "id": r.id,
            "title": r.title or "无标题",
            "blogger_name": r.blogger_name or "",
            "thumb": thumb,
            "pushed_at": str(r.pushed_at) if r.pushed_at else "",
            "infringement_level": r.infringement_level or "",
            "review_status": r.review_status or "",
        })

    # 热点剧名 TOP5 + 指标表
    td_q = (
        select(WorkOrder.drama_name, func.count(EvidenceRecord.id).label("cnt"))
        .join(Task, Task.work_order_id == WorkOrder.id, isouter=True)
        .join(EvidenceRecord, EvidenceRecord.task_id == Task.id, isouter=True)
        .group_by(WorkOrder.drama_name)
        .order_by(func.count(EvidenceRecord.id).desc())
        .limit(5)
    )
    td_rows = (await db.execute(td_q)).all()
    top_dramas = [{"name": row[0], "count": int(row[1] or 0)} for row in td_rows if row[0]]

    indicators = []
    for row in td_rows:
        if not row[0]:
            continue
        name = row[0]
        cnt = int(row[1] or 0)
        pushed_n = (
            await db.execute(
                select(func.count(EvidenceRecord.id))
                .join(Task, EvidenceRecord.task_id == Task.id)
                .join(WorkOrder, Task.work_order_id == WorkOrder.id)
                .where(
                    WorkOrder.drama_name == name,
                    EvidenceRecord.pushed_to_police == True,
                )
            )
        ).scalar() or 0
        indicators.append({
            "name": name,
            "total": cnt,
            "pushed": int(pushed_n),
            "rate": round(pushed_n / cnt * 100, 1) if cnt else 0,
        })

    return {
        "period": period,
        "runtime_seconds": int(runtime_seconds or 0),
        "runtime_hours": round((runtime_seconds or 0) / 3600, 1),
        "tasks": {
            "total": task_total,
            "running": task_running,
            "completed": task_completed,
            "pending": max(0, task_total - task_running - task_completed),
        },
        "links_collected": link_total,
        "evidence_total": evidence_total,
        "pushed_total": pushed_total,
        "infringement": {
            "high": high_count,
            "mid": mid_count,
            "low": low_count,
            "reviewed_infringement": infringement_reviewed,
        },
        "work_orders": work_order_total,
        "work_order_status": wo_status,
        "company_pending": company_pending,
        "pipeline": {
            "company_pushed": company_pushed_total,
            "company_pending": company_pending,
            "company_infringement": company_reviewed_ok,
            "company_not_infringement": company_reviewed_no,
            "police_pushed": pushed_total,
        },
        "drama_count": drama_count,
        "trend_14d": trend,
        "top_dramas": top_dramas,
        "recent_pushed": recent_pushed,
        "recent_activity": recent_activity,
        "indicators": indicators,
    }
