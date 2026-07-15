"""对已有证据记录重新执行黑名单匹配（补匹配）"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import select
from database import async_session, engine
from models import Base, EvidenceRecord, InfringementClue


async def rematch_all():
    async with async_session() as session:
        # 加载黑名单
        clues = (await session.execute(select(InfringementClue))).scalars().all()
        print(f'黑名单: {len(clues)} 条')

        # 查所有有引流数据的记录
        records = (await session.execute(
            select(EvidenceRecord).where(
                (EvidenceRecord.target_blogger_name != '') &
                (EvidenceRecord.traffic_video_name != '')
            )
        )).scalars().all()
        print(f'有引流数据的证据: {len(records)} 条')

        updated = 0
        for r in records:
            target_blogger = (r.target_blogger_name or '').strip()
            traffic_video = (r.traffic_video_name or '').strip()
            if not target_blogger or not traffic_video:
                continue

            matched_clue = None
            for clue in clues:
                clue_account = (clue.account_name or '').strip()
                if clue_account.lower() != target_blogger.lower():
                    continue
                clue_work = (clue.work_name or '').strip()
                if not clue_work:
                    continue
                if clue_work in traffic_video or traffic_video in clue_work:
                    matched_clue = clue
                    break

            if matched_clue:
                r.infringement_level = '高度疑似'
                r.infringement_score = 1.0
                reason = f'匹配到侵权线索（博主={matched_clue.account_name}'
                if matched_clue.work_name:
                    reason += f'，作品={matched_clue.work_name}'
                if matched_clue.our_work_name:
                    reason += f'，我方作品={matched_clue.our_work_name}'
                reason += '）'
                r.infringement_reason = reason
                updated += 1
                print(f'  id={r.id} [MATCH] {target_blogger} / {traffic_video}')
            else:
                print(f'  id={r.id} [NO MATCH] {target_blogger} / {traffic_video}')

        await session.commit()
        print(f'\n补匹配完成: 更新 {updated} 条记录')


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await rematch_all()


if __name__ == '__main__':
    asyncio.run(main())
