"""一键清除所有任务运行痕迹（数据库 + 文件产物）"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

# 确保可以导入 config
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DATABASE_URL, EVIDENCE_DATA_DIR,
    SCREENSHOTS_DIR, RECORDINGS_DIR, JSONS_DIR, TEMP_DIR, EVIDENCE_DIR,
    ASR_DIR,
)


def confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in ("y", "yes")


async def clear_table(table_name: str) -> int:
    """清空指定表，返回删除行数"""
    from sqlalchemy import text
    from database import async_session

    try:
        async with async_session() as conn:
            # 检查表是否存在
            result = await conn.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :name"),
                {"name": table_name},
            )
            exists = result.scalar()
            if not exists:
                print(f"  ⏭ {table_name}: 表不存在，跳过")
                return 0
            result = await conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
            count = result.scalar()
            if count:
                await conn.execute(text(f"DELETE FROM `{table_name}`"))
                await conn.commit()
    except Exception as e:
        print(f"  ⚠ {table_name}: {e}")
        return 0
    return count


def clear_dir(dir_path: Path) -> int:
    """清空目录中的所有文件和子目录，返回删除的项数"""
    if not dir_path.exists():
        return 0
    count = 0
    for item in dir_path.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            count += 1
        except Exception as e:
            print(f"  ⚠ 删除失败: {item} — {e}")
    return count


async def main():
    print("=" * 60)
    print("  嘉剧荟 — 短剧侵权识别平台 — 一键清理脚本")
    print("=" * 60)
    print(f"  证据目录: {EVIDENCE_DATA_DIR}")
    print(f"  数据库:   {DATABASE_URL}")
    print()

    print("将清除以下内容：")
    print("  📁 截图文件")
    print("  📁 录屏 / 音频文件")
    print("  📁 JSON / HTML 证据包")
    print("  📁 任务组织目录")
    print("  📁 临时文件")
    print("  📁 ASR 转写输出")
    print("  🗄️  数据库所有表数据（保留侵权线索黑名单）")
    print()

    if not confirm("确定要清除所有任务运行痕迹？"):
        print("已取消。")
        return

    print()
    print("正在清理...")

    # ── 清理数据库 ──
    print("\n[数据库]")
    tables = ["review_logs", "evidence_records", "video_links",
              "link_batches", "tasks", "author_clusters", "devices"]
    # 注意: infringement_clues（侵权线索黑名单）不在清理范围内
    total_db = 0
    for table in tables:
        count = await clear_table(table)
        if count:
            print(f"  ✅ {table}: 删除 {count} 行")
            total_db += count
        else:
            print(f"  ⏭ {table}: 无数据")
    if total_db == 0:
        print("  ℹ️  数据库无数据，无需清理")

    # ── 清理文件 ──
    print("\n[文件产物]")
    dirs = {
        "截图": SCREENSHOTS_DIR,
        "录屏/音频": RECORDINGS_DIR,
        "JSON/HTML": JSONS_DIR,
        "任务证据": EVIDENCE_DIR,
        "临时文件": TEMP_DIR,
        "ASR转写": ASR_DIR,
    }
    total_files = 0
    for label, path in dirs.items():
        count = clear_dir(path)
        status = "✅" if count else "⏭"
        print(f"  {status} {label}: 清理 {count} 项")
        total_files += count

    if total_files == 0:
        print("  ℹ️  无文件产物")

    # 重新创建目录
    for d in [SCREENSHOTS_DIR, RECORDINGS_DIR, JSONS_DIR, EVIDENCE_DIR, TEMP_DIR, ASR_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 60)
    print("  清理完成！")
    print(f"  数据库: {total_db} 行")
    print(f"  文件:   {total_files} 项")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
    input("\n按回车键退出...")
