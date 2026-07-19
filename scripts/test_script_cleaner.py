# -*- coding: utf-8 -*-
"""本地验证台词清洗：弃子归来震万城.doc → 与样例 txt 粗对比。

用法（在项目根或 backend 下）:
  conda activate zscq
  python scripts/test_script_cleaner.py
  python scripts/test_script_cleaner.py --fallback-only   # 不调 LLM
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

SAMPLE_DOC = ROOT / "docs" / "samples" / "弃子归来震万城.doc"
SAMPLE_TXT = ROOT / "docs" / "samples" / "弃子归来震万城.txt"
OUT_DIR = ROOT / "docs" / "samples" / "_cleaner_out"


def _coverage(ref_lines: list[str], hyp_lines: list[str]) -> dict:
    """行级粗对比：参考行有多少在 hyp 中作为子串命中。"""
    hyp_joined = "\n".join(hyp_lines)
    hits = 0
    miss_samples: list[str] = []
    for line in ref_lines:
        if not line.strip():
            continue
        # 去掉首尾省略号差异后做包含判断
        key = line.strip().replace("…", "").replace(".", "")
        if key and key[: min(12, len(key))] in hyp_joined.replace("…", "").replace(".", ""):
            hits += 1
        elif line.strip() in hyp_joined:
            hits += 1
        else:
            if len(miss_samples) < 8:
                miss_samples.append(line.strip()[:60])
    total = len([x for x in ref_lines if x.strip()])
    return {
        "ref_lines": total,
        "hyp_lines": len(hyp_lines),
        "hits": hits,
        "coverage": (hits / total) if total else 0.0,
        "miss_samples": miss_samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback-only", action="store_true", help="仅测规则兜底")
    parser.add_argument("--doc", type=Path, default=SAMPLE_DOC)
    parser.add_argument("--ref", type=Path, default=SAMPLE_TXT)
    args = parser.parse_args()

    if not args.doc.is_file():
        print(f"缺少样例 doc: {args.doc}")
        return 1
    if not args.ref.is_file():
        print(f"缺少参考 txt: {args.ref}")
        return 1

    from weixin.asr.script_cleaner import (
        clean_script_to_dialogues,
        extract_script_bytes,
        _rule_fallback_clean,
        _normalize_dialogue_lines,
    )

    print(f"读取: {args.doc} ({args.doc.stat().st_size} bytes)")
    raw = extract_script_bytes(args.doc.read_bytes(), args.doc.name)
    print(f"原文抽取: {len(raw)} 字, 前 120 字预览:\n{raw[:120]!r}\n")

    if args.fallback_only:
        cleaned = "\n".join(_normalize_dialogue_lines(_rule_fallback_clean(raw)))
        mode = "fallback"
    else:
        cleaned, mode = clean_script_to_dialogues(raw)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"弃子归来震万城.cleaned.{mode}.txt"
    out_path.write_text(cleaned, encoding="utf-8")
    print(f"清洗模式: {mode}")
    print(f"清洗结果: {len(cleaned)} 字 / {len(cleaned.splitlines())} 行 → {out_path}")

    ref_lines = args.ref.read_text(encoding="utf-8").splitlines()
    hyp_lines = [x for x in cleaned.splitlines() if x.strip()]
    stats = _coverage(ref_lines, hyp_lines)
    print(
        f"覆盖率: {stats['coverage']:.1%} "
        f"({stats['hits']}/{stats['ref_lines']}), hyp_lines={stats['hyp_lines']}"
    )
    if stats["miss_samples"]:
        print("未命中抽样:")
        for s in stats["miss_samples"]:
            print(f"  - {s}")

    # 粗门槛：LLM 路径期望 >= 40%；规则兜底可能更低
    threshold = 0.15 if args.fallback_only else 0.35
    if stats["coverage"] < threshold:
        print(f"FAIL: 覆盖率低于 {threshold:.0%}")
        return 2
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
