"""迁移脚本：新增字段和表"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from database import engine, Base


async def migrate():
    async with engine.begin() as conn:
        # 1. tasks.collect_mode
        try:
            await conn.execute(text(
                "ALTER TABLE tasks ADD COLUMN collect_mode TEXT DEFAULT 'standard'"
            ))
            print("[迁移] tasks.collect_mode 列已添加")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("[迁移] tasks.collect_mode 列已存在，跳过")
            else:
                print(f"[迁移] tasks.collect_mode: {e}")

        # 2. video_links.batch_id
        try:
            await conn.execute(text(
                "ALTER TABLE video_links ADD COLUMN batch_id INTEGER"
            ))
            print("[迁移] video_links.batch_id 列已添加")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("[迁移] video_links.batch_id 列已存在，跳过")
            else:
                print(f"[迁移] video_links.batch_id: {e}")

        # 3. infringement_clues.traffic_description
        try:
            await conn.execute(text(
                "ALTER TABLE infringement_clues ADD COLUMN traffic_description TEXT DEFAULT ''"
            ))
            print("[迁移] infringement_clues.traffic_description 列已添加")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("[迁移] infringement_clues.traffic_description 列已存在，跳过")
            else:
                print(f"[迁移] infringement_clues.traffic_description: {e}")

        # 4. 新建 link_batches 表
        await conn.run_sync(Base.metadata.create_all)
        print("[迁移] link_batches 表已创建（如未存在）")

    print("[迁移] 完成！")


if __name__ == "__main__":
    asyncio.run(migrate())
