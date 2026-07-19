# -*- coding: utf-8 -*-
"""单步冒烟：连设备 → 搜索 → 点「视频」→ 点「最新」，然后停下（不点第一个视频）。

用法（conda env zscq）:
  python scripts/test_search_to_latest.py
  python scripts/test_search_to_latest.py --keyword 弃子归来震万城

手机请先停留在微信视频号可搜索的入口页（与正式一阶段一致）。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


async def main(keyword: str) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from weixin.core.main import connect_device_auto_v2, search_keyword

    print("=" * 60)
    print("冒烟：搜索 → 视频 → 最新（不点首个视频）")
    print(f"关键词: {keyword}")
    print("=" * 60)

    sp = StdioServerParameters(
        command="python",
        args=["-m", "ascript_mcp.local"],
        env={**os.environ},
    )
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[1/3] MCP 已初始化")

            if not await connect_device_auto_v2(session):
                print("[✗] 设备未连接")
                return 1
            print("[2/3] 设备已连接")

            print("[3/3] 执行 search_keyword（含点「视频」→「最新」）...")
            ok = await search_keyword(session, keyword)
            if not ok:
                print("[✗] 搜索失败")
                return 2

            print("-" * 60)
            print("[✓] 冒烟结束：已点「视频」与「最新」，未点第一个视频")
            print("请人工确认手机界面是否为「视频 / 最新」结果列表")
            print("-" * 60)
            return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="搜索到「最新」Tab 单步冒烟")
    parser.add_argument(
        "--keyword",
        default="弃子归来震万城",
        help="搜索剧名（默认：弃子归来震万城）",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.keyword.strip() or "弃子归来震万城")))
