"""数据库连接与 session 管理（SQLAlchemy 异步）"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """创建所有表（首次运行）+ 增量迁移"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 增量：为已有 tasks 表添加 phase 列（如果不存在）
        try:
            await conn.run_sync(
                lambda c: c.exec_driver_sql("ALTER TABLE tasks ADD COLUMN phase INTEGER DEFAULT 1")
            )
        except Exception:
            pass  # 列已存在


async def get_db() -> AsyncSession:
    """依赖注入用 — FastAPI Depends"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
