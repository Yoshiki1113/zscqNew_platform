"""FastAPI 应用入口"""
from __future__ import annotations

import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import init_db
from config import (
    EVIDENCE_DATA_DIR, SCREENSHOTS_DIR, RECORDINGS_DIR,
    JSONS_DIR, EVIDENCE_DIR, CORS_ORIGINS, BASE_DIR, PROJECT_ROOT,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：建表 → 恢复僵尸任务 → 初始化引擎 → 预热模型"""
    print("─" * 48)
    print("  [init] 初始化数据库...")
    await init_db()

    # 恢复僵尸任务：后端重启后，scheduler 的 _runners 已清空，
    # DB 中残留的 "running" 状态任务实际上是已死的，需要纠正
    from database import async_session
    from sqlalchemy import select, update
    async with async_session() as db:
        from models import Task
        result = await db.execute(
            select(Task).where(Task.status == "running")
        )
        zombie_tasks = result.scalars().all()
        if zombie_tasks:
            ids = [t.id for t in zombie_tasks]
            print(f"  [init] 发现 {len(ids)} 个僵尸任务（#{min(ids)} ~ #{max(ids)}），重置为 stopped")
            from sqlalchemy import update as sqla_update
            await db.execute(
                sqla_update(Task).where(Task.id.in_(ids)).values(
                    status="stopped",
                    error_message="后端服务重启，任务中断",
                    finished_at=datetime.now(),
                )
            )
            await db.commit()
        else:
            print("  [init] 没有残留的运行中任务")

    print("  [init] 初始化调度器 & 设备管理器...")
    from engine import get_scheduler, get_device_manager
    get_scheduler()
    get_device_manager()

    # 模型预热放到后台，避免 OCR worker 超时拖住 API（创建任务等接口可先用）
    print("  [init] 后台预热第三方模型（不阻塞 API）...")
    from prewarm import run_prewarm

    async def _prewarm_bg():
        try:
            await run_prewarm()
            print("  [init] 模型预热完成")
        except Exception as e:
            print(f"  [init] 预热失败（服务仍可用）: {e}")

    prewarm_task = asyncio.create_task(_prewarm_bg())

    print("─" * 48)
    print("  [init] OK 全部就绪，服务启动中...")
    yield
    prewarm_task.cancel()
    try:
        await prewarm_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="嘉剧荟 - 短剧侵权识别平台",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — 允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务 — 直接访问证据文件（截图/录屏/HTML）
FILE_SEARCH_DIRS = [
    EVIDENCE_DATA_DIR,    # platform/evidence_data/（根，支持子路径）
    SCREENSHOTS_DIR,       # platform/evidence_data/screenshots/
    RECORDINGS_DIR,        # platform/evidence_data/recordings/
    JSONS_DIR,             # platform/evidence_data/jsons/
    EVIDENCE_DIR,          # platform/evidence_data/tasks/
]


@app.get("/files/{file_path:path}")
async def serve_file(file_path: str):
    """文件服务 — 按优先级在 platform 和 weixin 目录中查找
    
    证据数据统一存储在 platform/evidence_data/ 下：
      screenshots/  截图
      recordings/   录屏和音频
      jsons/        JSON + HTML 证据包
      tasks/        按任务组织的证据
    
    兼容 weixin/core/ 旧数据。
    """
    safe_path = file_path.lstrip("/").lstrip("\\")
    for base_dir in FILE_SEARCH_DIRS:
        candidate = base_dir / safe_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
    raise HTTPException(404, f"文件不存在: {safe_path}")


# ── 注册 API 路由 ──
from api.tasks import router as tasks_router
from api.evidence import router as evidence_router
from api.reviews import router as reviews_router
from api.authors import router as authors_router
from api.devices import router as devices_router
from api.clues import router as clues_router
from api.link_pool import router as link_pool_router
from api.websocket import router as ws_router
from api.work_orders import router as work_orders_router
from api.dashboard import router as dashboard_router

app.include_router(tasks_router, prefix="/api")
app.include_router(evidence_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
app.include_router(authors_router, prefix="/api")
app.include_router(devices_router, prefix="/api")
app.include_router(clues_router, prefix="/api")
app.include_router(link_pool_router, prefix="/api")
app.include_router(work_orders_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")


# ── 前端静态文件托管 ──
# 生产环境（dist 存在时）：FastAPI 直接托管前端，一个端口搞定
# 开发环境（dist 不存在时）：Vite 开发服务器独立运行，走 CORS 代理
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    # 静态资源（/assets/*）
    if (FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")

    # favicon 等根目录文件
    for _name in ("favicon.ico", "favicon.svg"):
        _fp = FRONTEND_DIST / _name
        if _fp.exists():
            @app.get(f"/{_name}", include_in_schema=False)
            async def _serve_root_file(file_path: str = str(_fp)):
                return FileResponse(file_path)
            break

    # SPA fallback — 所有非 /api、非 /ws、非 /files 的 GET 请求返回 index.html
    # 注意：这个路由必须定义在 API 路由之后，FastAPI 按注册顺序匹配
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """SPA fallback"""
        # 排除 API/WS/文件路径
        if full_path.startswith(("api/", "ws/", "files/")):
            raise HTTPException(404, f"Not found: {full_path}")
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(404, "前端文件不存在，请先执行 npm run build")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
