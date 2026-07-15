"""数据库迁移：给 tasks 表加 skip_search 字段"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "evidence_data" / "db" / "platform.db"

def main():
    if not DB_PATH.exists():
        print(f"[错误] 数据库文件不存在: {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN skip_search BOOLEAN DEFAULT 0")
        conn.commit()
        print("skip_search 列添加成功")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e):
            print("skip_search 列已存在，跳过")
        else:
            raise
    conn.close()

if __name__ == "__main__":
    main()
