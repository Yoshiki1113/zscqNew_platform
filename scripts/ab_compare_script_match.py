# -*- coding: utf-8 -*-
"""《时光不渡傅先生》未清洗 vs 清洗后 台词比对离线实验。

不写回 DB、不改 evidence_data/scripts 正式库。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

KEYWORD = "时光不渡傅先生"
OUT_DIR = ROOT / "docs" / "samples" / "_ab_compare" / KEYWORD
SRC_SCRIPT = ROOT / "evidence_data" / "scripts" / f"{KEYWORD}.txt"
MAX_ROWS = 20


def _summary(sm: dict) -> dict:
    best = sm.get("best_match") or {}
    return {
        "status": sm.get("status") or "",
        "coverage": float(sm.get("coverage") or 0),
        "segments_matched": int(sm.get("segments_matched") or 0),
        "segments_total": int(sm.get("segments_total") or 0),
        "avg_similarity": float(sm.get("avg_similarity") or 0),
        "pinyin_score": float(best.get("pinyin_score") or 0),
        "char_score": float(best.get("char_score") or 0),
        "script_preview": (best.get("script_text") or "")[:60],
        "episode": best.get("episode") or "",
    }


def ensure_raw() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = OUT_DIR / "raw.txt"
    if not SRC_SCRIPT.is_file():
        raise FileNotFoundError(f"找不到台词: {SRC_SCRIPT}")
    text = SRC_SCRIPT.read_text(encoding="utf-8")
    raw.write_text(text, encoding="utf-8")
    return raw


def clean_raw(raw_path: Path) -> tuple[Path, str, dict]:
    from weixin.asr.script_cleaner import clean_script_to_dialogues

    raw = raw_path.read_text(encoding="utf-8")
    cleaned, mode = clean_script_to_dialogues(raw)
    cleaned_path = OUT_DIR / "cleaned.txt"
    cleaned_path.write_text(cleaned or "", encoding="utf-8")
    meta = {
        "mode": mode,
        "raw_chars": len(raw),
        "raw_lines": len([ln for ln in raw.splitlines() if ln.strip()]),
        "cleaned_chars": len(cleaned or ""),
        "cleaned_lines": len([ln for ln in (cleaned or "").splitlines() if ln.strip()]),
    }
    (OUT_DIR / "clean_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cleaned_path, mode, meta


async def load_asr_rows(limit: int = MAX_ROWS) -> tuple[list[dict], dict]:
    from sqlalchemy import or_, select
    from database import async_session
    from models import EvidenceRecord

    async with async_session() as session:
        q = (
            select(
                EvidenceRecord.id,
                EvidenceRecord.search_keyword,
                EvidenceRecord.title,
                EvidenceRecord.blogger_name,
                EvidenceRecord.asr_text,
                EvidenceRecord.script_match_status,
            )
            .where(
                EvidenceRecord.search_keyword.like(f"%{KEYWORD}%"),
                EvidenceRecord.asr_text.is_not(None),
                EvidenceRecord.asr_text != "",
            )
            .order_by(EvidenceRecord.id.asc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        # also count totals
        from sqlalchemy import func

        total = (
            await session.execute(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.search_keyword.like(f"%{KEYWORD}%")
                )
            )
        ).scalar() or 0
        with_asr = (
            await session.execute(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.search_keyword.like(f"%{KEYWORD}%"),
                    EvidenceRecord.asr_text.is_not(None),
                    EvidenceRecord.asr_text != "",
                )
            )
        ).scalar() or 0
        with_media = (
            await session.execute(
                select(func.count(EvidenceRecord.id)).where(
                    EvidenceRecord.search_keyword.like(f"%{KEYWORD}%"),
                    or_(
                        EvidenceRecord.recording_audio_path != "",
                        EvidenceRecord.recording_video_path != "",
                    ),
                )
            )
        ).scalar() or 0

    items = [
        {
            "id": r.id,
            "search_keyword": r.search_keyword or "",
            "title": r.title or "",
            "blogger_name": r.blogger_name or "",
            "asr_text": r.asr_text or "",
            "script_match_status": r.script_match_status or "",
        }
        for r in rows
    ]
    return items, {"total": total, "with_asr": with_asr, "with_media": with_media}


def run_match(asr: str, script_path: Path) -> dict:
    from weixin.asr.script_matcher import match_segmented

    return match_segmented(asr, top_n=1, script_path=script_path)


def compare(rows: list[dict], raw_path: Path, cleaned_path: Path) -> list[dict]:
    results = []
    for i, row in enumerate(rows, 1):
        asr = row["asr_text"]
        print(f"[{i}/{len(rows)}] id={row['id']} asr_chars={len(asr)}")
        a = _summary(run_match(asr, raw_path))
        b = _summary(run_match(asr, cleaned_path))
        results.append(
            {
                "id": row["id"],
                "blogger_name": row["blogger_name"],
                "title": (row["title"] or "")[:40],
                "asr_chars": len(asr),
                "asr_preview": asr[:40].replace("\n", " "),
                "A_raw": a,
                "B_cleaned": b,
                "coverage_delta": round(b["coverage"] - a["coverage"], 4),
                "matched_delta": b["segments_matched"] - a["segments_matched"],
            }
        )
    return results


def write_report(clean_meta: dict, counts: dict, results: list[dict]) -> Path:
    matched_a = sum(1 for r in results if r["A_raw"]["status"] == "matched")
    matched_b = sum(1 for r in results if r["B_cleaned"]["status"] == "matched")
    avg_a = sum(r["A_raw"]["coverage"] for r in results) / len(results) if results else 0
    avg_b = sum(r["B_cleaned"]["coverage"] for r in results) / len(results) if results else 0

    improved = sorted(results, key=lambda r: r["coverage_delta"], reverse=True)[:3]
    worsened = sorted(results, key=lambda r: r["coverage_delta"])[:3]

    lines = []
    lines.append(f"# {KEYWORD} 未清洗 vs 清洗后 比对报告\n")
    lines.append("## 清洗摘要\n")
    lines.append(f"- mode: `{clean_meta.get('mode')}`")
    lines.append(
        f"- 原文: {clean_meta.get('raw_chars')} 字 / {clean_meta.get('raw_lines')} 非空行"
    )
    lines.append(
        f"- 清洗后: {clean_meta.get('cleaned_chars')} 字 / {clean_meta.get('cleaned_lines')} 非空行"
    )
    lines.append("")
    lines.append("## 证据样本\n")
    lines.append(
        f"- 该剧证据总数: {counts.get('total')}；有 ASR: {counts.get('with_asr')}；"
        f"有媒体: {counts.get('with_media')}；本次比对: {len(results)} 条"
    )
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- A 未清洗 matched: {matched_a}/{len(results)}，平均 coverage: {avg_a:.3f}")
    lines.append(f"- B 已清洗 matched: {matched_b}/{len(results)}，平均 coverage: {avg_b:.3f}")
    lines.append(f"- coverage 平均提升: {avg_b - avg_a:+.3f}")
    lines.append("")
    lines.append("## 逐条结果\n")
    lines.append(
        "| id | blogger | A status | A cov | A seg | B status | B cov | B seg | Δcov |"
    )
    lines.append("|---:|---|---|---:|---|---|---:|---|---:|")
    for r in results:
        a, b = r["A_raw"], r["B_cleaned"]
        lines.append(
            f"| {r['id']} | {r['blogger_name'][:12]} | {a['status']} | {a['coverage']:.2f} | "
            f"{a['segments_matched']}/{a['segments_total']} | {b['status']} | {b['coverage']:.2f} | "
            f"{b['segments_matched']}/{b['segments_total']} | {r['coverage_delta']:+.2f} |"
        )
    lines.append("")
    lines.append("## 清洗后变好（coverage 提升最多）\n")
    for r in improved:
        if r["coverage_delta"] <= 0:
            continue
        lines.append(
            f"- id={r['id']} Δcov={r['coverage_delta']:+.2f} "
            f"A={r['A_raw']['coverage']:.2f}→B={r['B_cleaned']['coverage']:.2f} "
            f"asr=`{r['asr_preview']}`"
        )
    lines.append("")
    lines.append("## 清洗后变差或持平（coverage 最低）\n")
    for r in worsened:
        lines.append(
            f"- id={r['id']} Δcov={r['coverage_delta']:+.2f} "
            f"A={r['A_raw']['coverage']:.2f}→B={r['B_cleaned']['coverage']:.2f} "
            f"asr=`{r['asr_preview']}`"
        )

    report = OUT_DIR / "report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT_DIR / "results.json").write_text(
        json.dumps(
            {"clean_meta": clean_meta, "counts": counts, "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


async def amain() -> int:
    print("1) copy raw")
    raw_path = ensure_raw()
    print(f"   raw -> {raw_path}")

    print("2) clean")
    cleaned_path, mode, clean_meta = clean_raw(raw_path)
    print(f"   mode={mode} meta={clean_meta}")
    print(f"   cleaned -> {cleaned_path}")

    print("3) load ASR from DB")
    rows, counts = await load_asr_rows()
    print(f"   counts={counts} loaded={len(rows)}")
    if not rows:
        report = OUT_DIR / "report.md"
        report.write_text(
            f"# {KEYWORD}\n\n无可用 ASR。counts={counts}\n"
            f"清洗已完成 mode={mode} lines={clean_meta.get('cleaned_lines')}\n",
            encoding="utf-8",
        )
        print("STOP: no ASR rows")
        return 2

    print("4) A/B match")
    results = compare(rows, raw_path, cleaned_path)
    report = write_report(clean_meta, counts, results)
    print(f"5) report -> {report}")
    print(report.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
