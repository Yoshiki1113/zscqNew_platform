#!/usr/bin/env python3
"""插入演示用工单与侵权链接（可选运行）

用法（zscq 环境）:
  python scripts/seed_demo_work_order.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from database import async_session, init_db  # noqa: E402
from models import WorkOrder  # noqa: E402
from api.work_orders import _gen_order_no, _import_links_to_batch  # noqa: E402


DEMO_LINKS = [
    "https://channels.weixin.qq.com/platform/post/example-link-1",
    "https://channels.weixin.qq.com/platform/post/example-link-2",
]


async def main() -> None:
    await init_db()
    async with async_session() as db:
        wo = WorkOrder(
            order_no=_gen_order_no(),
            drama_name="演示剧名-弃子归来",
            description="演示工单：公司直接提交侵权链接，取证员在链接池创建二阶段任务。",
            priority=5,
            status="submitted",
            submitter="演示公司",
            submitted_at=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(wo)
        await db.flush()
        summary = await _import_links_to_batch(db, wo, DEMO_LINKS)
        await db.commit()
        print(f"演示工单已创建: id={wo.id} order_no={wo.order_no}")
        print(f"链接池批次: {summary.get('batch_name')} 导入 {summary.get('imported')} 条")


if __name__ == "__main__":
    asyncio.run(main())
