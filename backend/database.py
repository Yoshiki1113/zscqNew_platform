"""数据库连接与 session 管理（SQLAlchemy 异步）"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# 旧版 / 共用库 tasks 表可能缺这些列（create_all 不会改已有表）
_TASK_COLUMN_MIGRATIONS = [
    ("device_id", "VARCHAR(100) DEFAULT ''"),
    ("max_videos", "INT DEFAULT 5"),
    ("hold_seconds", "INT DEFAULT 240"),
    ("capture_method", "VARCHAR(20) DEFAULT 'auto'"),
    ("enable_asr", "TINYINT(1) DEFAULT 1"),
    ("skip_search", "TINYINT(1) DEFAULT 0"),
    ("collect_mode", "VARCHAR(20) DEFAULT 'link_first'"),
    ("phase", "INT DEFAULT 1"),
    ("finished_at", "DATETIME NULL"),
    ("log_file_path", "VARCHAR(500) DEFAULT ''"),
    ("error_message", "TEXT"),
]

# 旧表遗留列若 NOT NULL 且无默认值，ORM 插入会 500
_TASK_LEGACY_NULLABLE = [
    ("log_json", "LONGTEXT NULL"),
    ("video_count", "INT NULL DEFAULT 0"),
    ("ended_at", "DATETIME NULL"),
    ("updated_at", "DATETIME NULL"),
    ("started_at", "DATETIME NULL"),
]


async def _ensure_task_columns(conn) -> None:
    """给已有 tasks 表补齐平台所需列，并放宽旧表遗留 NOT NULL 列（幂等）。"""
    result = await conn.execute(text("SHOW FULL COLUMNS FROM tasks"))
    rows = result.fetchall()
    existing = {row[0]: row for row in rows}

    for name, ddl in _TASK_COLUMN_MIGRATIONS:
        if name in existing:
            continue
        try:
            await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {ddl}"))
            print(f"  [migrate] tasks.{name} added")
        except Exception as e:
            print(f"  [migrate] tasks.{name} skip: {e}")

    # status 旧定义为 varchar(16)，平台状态 links_collected 刚好卡边，放宽到 32
    try:
        status_type = str(existing.get("status", [None, ""])[1]).lower()
        if "varchar" in status_type and "16" in status_type:
            await conn.execute(text("ALTER TABLE tasks MODIFY COLUMN status VARCHAR(32) NOT NULL"))
            print("  [migrate] tasks.status -> VARCHAR(32)")
    except Exception as e:
        print(f"  [migrate] tasks.status skip: {e}")

    for name, ddl in _TASK_LEGACY_NULLABLE:
        if name not in existing:
            continue
        null_flag = str(existing[name][3]).upper()
        if null_flag == "YES":
            continue
        try:
            await conn.execute(text(f"ALTER TABLE tasks MODIFY COLUMN {name} {ddl}"))
            print(f"  [migrate] tasks.{name} set nullable")
        except Exception as e:
            print(f"  [migrate] tasks.{name} nullable skip: {e}")

    if "work_order_id" not in existing:
        try:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN work_order_id INT NULL"))
            print("  [migrate] tasks.work_order_id added")
        except Exception as e:
            print(f"  [migrate] tasks.work_order_id skip: {e}")

    # evidence_records 推送公安字段
    try:
        er = await conn.execute(text("SHOW COLUMNS FROM evidence_records"))
        er_cols = {row[0] for row in er.fetchall()}
        for name, ddl in [
            ("pushed_to_police", "TINYINT(1) DEFAULT 0"),
            ("pushed_at", "DATETIME NULL"),
            ("pushed_by", "VARCHAR(100) DEFAULT ''"),
            ("pushed_to_company", "TINYINT(1) DEFAULT 0"),
            ("pushed_to_company_at", "DATETIME NULL"),
            ("pushed_to_company_by", "VARCHAR(100) DEFAULT ''"),
        ]:
            if name not in er_cols:
                await conn.execute(text(f"ALTER TABLE evidence_records ADD COLUMN {name} {ddl}"))
                print(f"  [migrate] evidence_records.{name} added")
    except Exception as e:
        print(f"  [migrate] evidence_records push columns: {e}")

    try:
        wo = await conn.execute(text("SHOW COLUMNS FROM work_orders"))
        wo_cols = {row[0] for row in wo.fetchall()}
        if "company_pushed_count" not in wo_cols:
            await conn.execute(text(
                "ALTER TABLE work_orders ADD COLUMN company_pushed_count INT DEFAULT 0"
            ))
            print("  [migrate] work_orders.company_pushed_count added")
        for name, ddl in [
            ("script_status", "VARCHAR(20) DEFAULT 'none'"),
            ("script_source_hash", "VARCHAR(64) DEFAULT ''"),
            ("script_cleaned_at", "DATETIME NULL"),
            ("script_error", "VARCHAR(500) DEFAULT ''"),
        ]:
            if name not in wo_cols:
                await conn.execute(text(f"ALTER TABLE work_orders ADD COLUMN {name} {ddl}"))
                print(f"  [migrate] work_orders.{name} added")
    except Exception as e:
        print(f"  [migrate] work_orders columns: {e}")


async def init_db():
    """创建所有表（首次运行）+ 增量迁移"""
    # 确保 models 已注册到 Base.metadata
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await _ensure_task_columns(conn)
        except Exception as e:
            print(f"  [migrate] tasks columns: {e}")


async def get_db() -> AsyncSession:
    """依赖注入用 — FastAPI Depends"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
