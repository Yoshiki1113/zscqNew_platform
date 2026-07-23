"""API 路由 — 任务管理"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import DEFAULT_MAX_VIDEOS, DEFAULT_HOLD_SECONDS, DEFAULT_CAPTURE_METHOD, DEFAULT_PHONE_PORT
from database import get_db
from models import Task, EvidenceRecord, ReviewLog, VideoLink, InfringementClue, WorkOrder
from engine import get_scheduler


async def _get_device_connection(device_id: str) -> tuple[str, int, str]:
    """获取设备连接参数：IP、端口、serial（仅支持真机直连，端口固定 9096）。"""
    from engine import get_device_manager
    mgr = get_device_manager()
    device_info = await mgr.get_device_info(device_id) if device_id else None
    device_ip = device_info.ip_address if device_info else ""
    device_serial = device_id or ""
    device_port = DEFAULT_PHONE_PORT

    return device_ip, device_port, device_serial


router = APIRouter(tags=["任务管理"])


# ── Pydantic Schemas ──
class TaskCreate(BaseModel):
    keyword: str = Field("", max_length=200)
    max_videos: int = Field(DEFAULT_MAX_VIDEOS, ge=0, le=100)
    hold_seconds: int = Field(DEFAULT_HOLD_SECONDS, ge=30, le=3600)
    capture_method: str = Field(DEFAULT_CAPTURE_METHOD, pattern="^(scrcpy)$")
    device_id: str = Field("", max_length=100)
    enable_asr: bool = Field(True)
    skip_search: bool = Field(False)
    work_order_id: Optional[int] = Field(None, ge=1)


class TaskResponse(BaseModel):
    id: int
    keyword: str
    status: str
    device_id: str
    max_videos: int
    hold_seconds: int
    capture_method: str
    enable_asr: bool = True
    skip_search: bool = False
    collect_mode: str = "link_first"
    phase: int = 1
    work_order_id: Optional[int] = None
    drama_name: str = ""
    order_no: str = ""
    evidence_count: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    error_message: str = ""
    orphans_deleted: int = 0

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    page: int
    page_size: int


def _task_to_response(
    task: Task,
    evidence_count: int = 0,
    orphans_deleted: int = 0,
    drama_name: str = "",
    order_no: str = "",
) -> TaskResponse:
    kw = task.keyword or ""
    drama = (drama_name or "").strip()
    ono = (order_no or "").strip()
    # keyword 若是 WO- 批次名且无剧名，仍展示原 keyword；有剧名则 drama_name 优先用于前端
    if not drama and kw and not kw.upper().startswith("WO-"):
        drama = kw
    return TaskResponse(
        id=task.id,
        keyword=kw,
        status=task.status,
        device_id=task.device_id or "",
        max_videos=task.max_videos,
        hold_seconds=task.hold_seconds,
        capture_method=task.capture_method,
        enable_asr=task.enable_asr if task.enable_asr is not None else True,
        skip_search=task.skip_search if task.skip_search is not None else False,
        collect_mode=task.collect_mode or "link_first",
        phase=task.phase if task.phase else 1,
        work_order_id=task.work_order_id,
        drama_name=drama,
        order_no=ono,
        evidence_count=evidence_count,
        started_at=task.started_at,
        finished_at=task.finished_at,
        created_at=task.created_at or datetime.now(),
        error_message=task.error_message or "",
        orphans_deleted=orphans_deleted,
    )


async def _wo_meta_map(db: AsyncSession, tasks: list[Task]) -> dict[int, tuple[str, str]]:
    """work_order_id -> (drama_name, order_no)；并尝试用 keyword=WO-{order_no} 反查。"""
    meta: dict[int, tuple[str, str]] = {}
    wo_ids = [t.work_order_id for t in tasks if t.work_order_id]
    if wo_ids:
        rows = (await db.execute(
            select(WorkOrder.id, WorkOrder.drama_name, WorkOrder.order_no).where(
                WorkOrder.id.in_(list(set(wo_ids)))
            )
        )).all()
        by_id = {wid: ((d or "").strip(), (o or "").strip()) for wid, d, o in rows}
        for t in tasks:
            if t.work_order_id and t.work_order_id in by_id:
                meta[t.id] = by_id[t.work_order_id]

    # keyword 形如 WO-{order_no} 时反查工单
    need = [t for t in tasks if t.id not in meta]
    order_nos = []
    task_to_ono: dict[int, str] = {}
    for t in need:
        name = (t.keyword or "").strip()
        if name.upper().startswith("WO-"):
            ono = name[3:].strip()
            if ono:
                order_nos.append(ono)
                task_to_ono[t.id] = ono
    if order_nos:
        rows = (await db.execute(
            select(WorkOrder.order_no, WorkOrder.drama_name).where(
                WorkOrder.order_no.in_(list(set(order_nos)))
            )
        )).all()
        by_ono = {(o or "").strip(): (d or "").strip() for o, d in rows}
        for tid, ono in task_to_ono.items():
            drama = by_ono.get(ono, "")
            if drama:
                meta[tid] = (drama, ono)
    return meta


async def _get_task_with_count(task_id: int, db: AsyncSession) -> tuple[Task, int]:
    row = (await db.execute(
        select(Task, func.count(EvidenceRecord.id).label("evidence_count"))
        .outerjoin(EvidenceRecord, EvidenceRecord.task_id == Task.id)
        .where(Task.id == task_id)
        .group_by(Task.id)
    )).first()
    if not row:
        raise HTTPException(404, "任务不存在")
    return row


# ── Routes ──

@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    status: str = Query("", max_length=20),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    phase: int = Query(0, ge=0, le=2),
    db: AsyncSession = Depends(get_db),
):
    """任务列表（分页 + 状态筛选 + 阶段筛选）
    phase=1: 只返回一阶段（链接采集）任务，含 link_count
    phase=2: 只返回二阶段（视频取证）任务（有证据记录的任务）
    phase=0: 返回所有任务
    """
    # 用相关子查询统计 evidence_count
    evidence_subq = (
        select(func.count(EvidenceRecord.id))
        .where(EvidenceRecord.task_id == Task.id)
        .correlate(Task)
        .scalar_subquery()
        .label("evidence_count")
    )
    base = select(Task, evidence_subq)

    count_q = select(func.count()).select_from(Task)

    if status:
        base = base.where(Task.status == status)
        count_q = count_q.where(Task.status == status)

    if phase:
        base = base.where(Task.phase == phase)
        count_q = count_q.where(Task.phase == phase)

    base = base.order_by(Task.created_at.desc())

    total = (await db.execute(count_q)).scalar() or 0

    rows = (await db.execute(base.offset((page - 1) * page_size).limit(page_size))).all()

    tasks = [t for t, _ec in rows]
    wo_meta = await _wo_meta_map(db, tasks)
    items = []
    for t, ec in rows:
        drama, ono = wo_meta.get(t.id, ("", ""))
        items.append(_task_to_response(t, ec or 0, drama_name=drama, order_no=ono))
    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    """创建新任务"""
    work_order_id = body.work_order_id
    if not work_order_id:
        from api.work_orders import resolve_work_order_id_from_keyword
        work_order_id = await resolve_work_order_id_from_keyword(db, body.keyword or "")

    task = Task(
        keyword=body.keyword,
        max_videos=body.max_videos,
        hold_seconds=body.hold_seconds,
        capture_method=body.capture_method,
        device_id=body.device_id,
        enable_asr=body.enable_asr,
        skip_search=body.skip_search,
        collect_mode="link_first",
        work_order_id=work_order_id,
        status="pending",
        created_at=datetime.now(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """任务详情"""
    task, evidence_count = await _get_task_with_count(task_id, db)
    wo_meta = await _wo_meta_map(db, [task])
    drama, ono = wo_meta.get(task.id, ("", ""))
    return _task_to_response(task, evidence_count or 0, drama_name=drama, order_no=ono)


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """删除任务及关联证据"""
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "任务不存在")
    sched = get_scheduler()
    if sched.is_running(task_id):
        raise HTTPException(400, "任务刚结束，监控日志保留5分钟，请稍后重试")
    # 清理复核记录（ReviewLog 无 FK cascade）
    from sqlalchemy import delete as sqla_delete
    evidence_ids = (await db.execute(
        select(EvidenceRecord.id).where(EvidenceRecord.task_id == task_id)
    )).scalars().all()
    if evidence_ids:
        await db.execute(sqla_delete(ReviewLog).where(ReviewLog.evidence_id.in_(evidence_ids)))
    # 清理关联的 video_links（无 FK cascade，需手动删除）
    await db.execute(sqla_delete(VideoLink).where(VideoLink.task_id == task_id))
    await db.delete(task)
    await db.commit()


# ── 任务控制 ──

@router.post("/tasks/{task_id}/start", response_model=TaskResponse)
async def start_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """启动任务（异步后台执行，支持长时间运行）"""
    task, evidence_count = await _get_task_with_count(task_id, db)

    if task.status == "running":
        raise HTTPException(400, "任务已在运行中")

    if task.status == "completed":
        raise HTTPException(400, "任务已完成，请使用重试或创建新任务")

    sched = get_scheduler()
    if sched.is_running(task_id):
        raise HTTPException(400, "任务调度中，请稍候")

    # 获取设备连接参数
    device_ip, device_port, device_serial = await _get_device_connection(task.device_id)

    # 标记为 pending（调度器会更新为 running）
    task.status = "pending"
    await db.commit()

    # 后台启动采集（不阻塞 API 响应，支持数小时的长任务）
    asyncio.create_task(sched.start_task(
        task_id=task_id,
        keyword=task.keyword,
        device_ip=device_ip,
        device_port=device_port,
        device_serial=device_serial,
        max_videos=task.max_videos,
        hold_seconds=task.hold_seconds,
        capture_method=task.capture_method,
        enable_asr=task.enable_asr,
        skip_search=task.skip_search,
        work_order_id=task.work_order_id,
    ))
    return _task_to_response(task, evidence_count or 0)


@router.post("/tasks/{task_id}/stop", response_model=TaskResponse)
async def stop_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """停止正在执行的任务"""
    task, evidence_count = await _get_task_with_count(task_id, db)

    if task.status != "running":
        raise HTTPException(400, f"任务状态为 {task.status}，无法停止")

    sched = get_scheduler()
    stopped = await sched.stop_task(task_id)
    if not stopped:
        raise HTTPException(404, "未找到运行中的任务实例")
    task.status = "stopped"
    task.error_message = "用户手动停止"
    await db.commit()

    return _task_to_response(task, evidence_count or 0)


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: int, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """重试失败/停止的任务（自动启动）"""
    task, evidence_count = await _get_task_with_count(task_id, db)

    if task.status == "running":
        raise HTTPException(400, "任务正在运行中，无需重试")

    if task.status not in ("failed", "stopped", "completed"):
        raise HTTPException(400, f"任务状态为 {task.status}，无需重试")

    # 重置状态
    task.status = "pending"
    task.started_at = None
    task.finished_at = None
    task.error_message = ""
    await db.commit()

    # 获取设备连接参数
    device_ip, device_port, device_serial = await _get_device_connection(task.device_id)

    sched = get_scheduler()
    asyncio.create_task(sched.start_task(
        task_id=task_id,
        keyword=task.keyword,
        device_ip=device_ip,
        device_port=device_port,
        device_serial=device_serial,
        max_videos=task.max_videos,
        hold_seconds=task.hold_seconds,
        capture_method=task.capture_method,
        enable_asr=task.enable_asr,
        skip_search=task.skip_search,
        work_order_id=task.work_order_id,
    ))

    return _task_to_response(task, evidence_count or 0)


# ── Phase 2 控制 ──

class StartPhase2Request(BaseModel):
    hold_seconds: int = DEFAULT_HOLD_SECONDS
    capture_method: str = DEFAULT_CAPTURE_METHOD
    enable_asr: bool = True
    resume: bool = False  # 前端断点续采传 true，仅日志区分


@router.post("/tasks/{task_id}/start-phase2", response_model=TaskResponse)
async def start_phase2(
    task_id: int,
    body: StartPhase2Request = StartPhase2Request(),
    db: AsyncSession = Depends(get_db),
):
    """手动触发阶段二：遍历已收集的链接进行完整取证

    支持前端直接传入取证参数（停留时长、ASR等），
    也可不传则使用默认值。
    前置条件：
      - links_collected（首次开二阶段）
      - stopped/failed 且 phase==2（断点续采）
    """
    task, evidence_count = await _get_task_with_count(task_id, db)

    if task.status == "running":
        raise HTTPException(400, "任务正在运行中")

    is_first = task.status == "links_collected"
    is_resume = task.status in ("stopped", "failed") and (task.phase or 1) == 2
    if not is_first and not is_resume:
        raise HTTPException(
            400,
            f"当前状态不可启动阶段二: status={task.status}, phase={task.phase}",
        )

    # 待采链接（续采与首次均校验）
    pending = (await db.execute(
        select(func.count(VideoLink.id)).where(
            VideoLink.task_id == task_id,
            VideoLink.evidence_record_id.is_(None),
        )
    )).scalar() or 0
    if pending == 0:
        raise HTTPException(400, "没有待续采链接" if is_resume or body.resume else "没有待处理的链接")

    sched = get_scheduler()
    if sched.is_running(task_id):
        raise HTTPException(400, "任务已在运行中")

    orphans_deleted = 0
    if is_resume or body.resume:
        from engine.orphan_media_cleanup import cleanup_task_orphan_media

        summary = await cleanup_task_orphan_media(task_id, since=task.started_at)
        orphans_deleted = int(summary.get("deleted") or 0)
        print(
            f"[start-phase2] 断点续采 task=#{task_id} pending={pending} "
            f"orphans_deleted={orphans_deleted}"
        )

    # 标记进入阶段二（status 由 scheduler 置 running）
    task.phase = 2
    task.error_message = ""
    await db.commit()

    # 获取设备连接参数
    device_ip, device_port, device_serial = await _get_device_connection(task.device_id)

    # 后台启动阶段二（使用请求参数，而非任务记录的旧值）
    asyncio.create_task(sched.start_phase2(
        task_id=task_id,
        keyword=task.keyword,
        device_ip=device_ip,
        device_port=device_port,
        device_serial=device_serial,
        max_videos=task.max_videos,
        hold_seconds=body.hold_seconds,
        capture_method=body.capture_method,
        enable_asr=body.enable_asr,
        work_order_id=task.work_order_id,
    ))

    return _task_to_response(task, evidence_count or 0, orphans_deleted=orphans_deleted)


@router.get("/tasks/{task_id}/video-links")
async def list_video_links(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    """查询阶段一收集的链接列表及采集状态"""
    rows = (await db.execute(
        select(VideoLink)
        .where(VideoLink.task_id == task_id)
        .order_by(VideoLink.sort_order)
    )).scalars().all()

    return [
        {
            "id": r.id,
            "link_url": r.link_url,
            "keyword": r.keyword,
            "collected": r.evidence_record_id is not None,
            "sort_order": r.sort_order,
            "evidence_record_id": r.evidence_record_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "collected_at": r.collected_at.isoformat() if r.collected_at else None,
        }
        for r in rows
    ]


# ── 从线索导入链接（跳过阶段一）──

class CreateFromCluesRequest(BaseModel):
    keyword: str = ""
    max_videos: int = Field(DEFAULT_MAX_VIDEOS, ge=0, le=200)
    hold_seconds: int = Field(DEFAULT_HOLD_SECONDS, ge=30, le=3600)
    capture_method: str = Field(DEFAULT_CAPTURE_METHOD, pattern="^(scrcpy)$")
    device_id: str = Field("", max_length=100)
    enable_asr: bool = Field(True)


@router.post("/tasks/create-from-clues", response_model=TaskResponse, status_code=201)
async def create_task_from_clues(
    body: CreateFromCluesRequest,
    db: AsyncSession = Depends(get_db),
):
    """从已导入的侵权线索中有视频链接的记录创建取证任务

    1. 创建 Task（collect_mode=link_first, status=links_collected，跳过阶段一）
    2. 将 InfringementClue 中有 video_link 的记录写入 video_links 表
    3. 返回任务信息（可直接调用 start-phase2 启动阶段二）
    """
    # 查询有链接的线索
    clues_result = await db.execute(
        select(InfringementClue).where(
            InfringementClue.video_link != "",
            InfringementClue.video_link.isnot(None),
        )
    )
    clues_with_links = clues_result.scalars().all()

    if not clues_with_links:
        raise HTTPException(400, "没有找到包含视频链接的侵权线索，请先导入线索 Excel")

    # 确定采集数量
    total_links = len(clues_with_links)
    actual_max = min(body.max_videos, total_links) if body.max_videos > 0 else total_links

    # 创建任务（跳过阶段一，直接设为 links_collected）
    task = Task(
        keyword=body.keyword or "(从线索导入)",
        max_videos=actual_max,
        hold_seconds=body.hold_seconds,
        capture_method=body.capture_method,
        device_id=body.device_id,
        enable_asr=body.enable_asr,
        skip_search=True,
        collect_mode="link_first",
        phase=2,
        status="links_collected",
        created_at=datetime.now(),
    )
    db.add(task)
    await db.flush()  # 获取 task.id

    # 将链接写入 video_links
    import_count = 0
    for idx, clue in enumerate(clues_with_links, 1):
        if body.max_videos > 0 and idx > body.max_videos:
            break
        link = VideoLink(
            task_id=task.id,
            keyword=clue.our_work_name or clue.work_name or "",
            link_url=clue.video_link,
            sort_order=idx,
        )
        db.add(link)
        import_count += 1

    await db.commit()
    await db.refresh(task)

    return _task_to_response(task, 0)
