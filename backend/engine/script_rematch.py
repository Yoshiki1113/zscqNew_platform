# -*- coding: utf-8 -*-
"""证据台词补比对：复用 ASR 文本 + 剧名台词库，写回 script_match 与侵权分。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

REMATCH_STATUSES = (
    "script_unavailable",
    "pending",
    "error",
    "not_found",
    "",
)


def run_script_match(asr_text: str, keyword: str) -> dict:
    """对已有 ASR 文本按剧名比对台词，返回 script_match dict。"""
    from weixin.asr.script_matcher import match_segmented, match_query

    text = (asr_text or "").strip()
    kw = (keyword or "").strip()
    if not text:
        return {"status": "not_found", "error": "no asr_text"}

    try:
        result = match_segmented(text, top_n=1, keyword=kw)
        legacy = match_query(text, top_n=3, keyword=kw)
    except FileNotFoundError:
        return {"status": "script_unavailable"}
    except ImportError as e:
        return {"status": "script_unavailable", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e)}

    status = result.get("status") or "not_found"
    if status == "script_unavailable":
        return {
            "status": "script_unavailable",
            "best_match": None,
            "top_candidates": [],
            "segments_matched": 0,
            "segments_total": 0,
            "coverage": 0.0,
            "avg_similarity": 0.0,
            "segments": [],
        }
    if status == "matched":
        return {
            "status": "matched",
            "best_match": result.get("best_match"),
            "top_candidates": legacy if legacy else [],
            "segments_matched": result.get("segments_matched", 0),
            "segments_total": result.get("segments_total", 0),
            "coverage": result.get("coverage", 0.0),
            "avg_similarity": result.get("avg_similarity", 0.0),
            "segments": result.get("segments", []),
        }
    return {
        "status": "not_found",
        "best_match": None,
        "top_candidates": legacy if legacy else [],
        "segments_matched": 0,
        "segments_total": result.get("segments_total", 0),
        "coverage": 0.0,
        "avg_similarity": 0.0,
        "segments": [],
    }


def compute_infringement_from_script_match(sm: dict) -> tuple[float, str]:
    """根据 script_match 计算 (score, level)。与采证入库公式一致。"""
    sm = sm or {}
    best = sm.get("best_match") or {}
    coverage = float(sm.get("coverage", 0) or 0) if sm.get("status") == "matched" else 0.0
    bp = float(best.get("pinyin_score", 0) or 0)
    bc = float(best.get("char_score", 0) or 0)
    bs = bp * 0.55 + bc * 0.45
    segs = sm.get("segments_matched", 0) or 0
    score = round(coverage * 0.35 + bs * 0.40 + min(segs / 5, 1.0) * 0.25, 4)
    if score >= 0.70:
        level = "高度疑似"
    elif score >= 0.50:
        level = "疑似"
    elif score >= 0.30:
        level = "待观察"
    else:
        level = "无"
    return score, level


def apply_match_to_evidence_row(row, sm: dict, asr_fallback: str = "") -> None:
    """将 script_match 写回 EvidenceRecord 行，并更新侵权分（不覆盖线索拉高的人工理由时仍重算分）。"""
    sm = sm or {}
    best = sm.get("best_match") or {}
    status = sm.get("status") or "pending"
    row.script_match_status = status
    row.script_match_similarity = float(
        sm.get("coverage")
        or best.get("similarity_score")
        or best.get("score")
        or 0.0
    )
    row.script_match_pinyin_score = float(best.get("pinyin_score", 0) or 0)
    row.script_match_char_score = float(best.get("char_score", 0) or 0)
    row.script_match_segments_matched = int(sm.get("segments_matched", 0) or 0)
    row.script_match_segments_total = int(sm.get("segments_total", 0) or 0)
    row.script_match_episode = best.get("episode", "") or ""
    row.script_match_scene = best.get("scene", "") or ""
    row.script_match_character = best.get("character", "") or ""
    row.script_match_location = best.get("location", "") or ""
    script_text = best.get("script_text") or ""
    if not script_text and asr_fallback:
        script_text = (asr_fallback or "")[:200]
    row.script_match_script_text = script_text
    row.script_match_segments_json = json.dumps(sm.get("segments") or [], ensure_ascii=False)

    score, level = compute_infringement_from_script_match(sm)
    # 若此前因线索黑名单写死 1.0，补比对不覆盖该理由；否则按比对结果更新
    reason = (getattr(row, "infringement_reason", None) or "").strip()
    if reason.startswith("匹配到侵权线索"):
        return
    row.infringement_score = score
    row.infringement_level = level


def _abs_under_evidence(raw: str) -> Optional[Path]:
    from config import EVIDENCE_DATA_DIR

    if not raw:
        return None
    p = Path(str(raw).replace("\\", "/"))
    if not p.is_absolute():
        p = EVIDENCE_DATA_DIR / p
    try:
        p = p.resolve()
    except Exception:
        return None
    return p if p.is_file() else None


def resolve_media_paths(row) -> tuple[Optional[Path], Optional[Path]]:
    """返回 (video_abs, audio_abs)，文件不存在则为 None。"""
    video = _abs_under_evidence(getattr(row, "recording_video_path", None) or "")
    audio = _abs_under_evidence(getattr(row, "recording_audio_path", None) or "")
    return video, audio


def ensure_script_for_keyword(keyword: str) -> bool:
    """按剧名解析台词库，可加载则 True。"""
    from weixin.asr.script_matcher import get_index

    kw = (keyword or "").strip()
    if not kw:
        return False
    try:
        return get_index(kw) is not None
    except Exception:
        return False


def ensure_wav_for_row(row) -> Optional[Path]:
    """有 wav 用之；否则从 mp4 抽音频并回写 recording_audio_path。"""
    from config import EVIDENCE_DATA_DIR

    video, audio = resolve_media_paths(row)
    if audio is not None:
        return audio
    if video is None:
        return None
    try:
        from weixin.core.media_capture import extract_audio

        wav = extract_audio(video)
    except Exception as e:
        print(f"[rematch] extract_audio 失败 id={getattr(row, 'id', '?')}: {e}")
        return None
    if wav is None or not Path(wav).is_file():
        return None
    wav_path = Path(wav).resolve()
    try:
        rel = str(wav_path.relative_to(EVIDENCE_DATA_DIR)).replace("\\", "/")
    except ValueError:
        rel = str(wav_path)
    row.recording_audio_path = rel
    row.has_audio = True
    return wav_path


def transcribe_evidence_row(row) -> str:
    """讯飞转写写回 row.asr_text / asr_model，不做台词比对。失败返回空串。"""
    from config import ASR_DIR
    import weixin.asr.xunfei as xunfei
    from weixin.asr.xunfei import core_transcribe_for_record

    wav = ensure_wav_for_row(row)
    if wav is None:
        return ""

    vid = (getattr(row, "video_identifier", None) or "").strip()
    if not vid:
        vid = f"evidence_{getattr(row, 'id', 0)}"

    class _Rec:
        def __init__(self):
            self.media_info = {}
            self.candidate = {"video_identifier": vid}

    rec = _Rec()
    xunfei.MEDIA_DIR = ASR_DIR
    try:
        core_transcribe_for_record(rec, str(wav), vid)
    except Exception as e:
        print(f"[rematch] ASR 失败 id={getattr(row, 'id', '?')}: {e}")
        return ""

    text = (rec.media_info.get("asr_text") or "").strip()
    if text:
        row.asr_text = text
        row.asr_model = rec.media_info.get("asr_model") or "xunfei-iat-v2"
    return text


def batch_asr_evidence_rows(rows: list) -> dict:
    """对一批无 ASR 的证据只转写、无比对。"""
    summary = {
        "total": len(rows),
        "transcribed": 0,
        "skipped_no_media": 0,
        "skipped_has_asr": 0,
        "error": 0,
    }
    for row in rows:
        if (getattr(row, "asr_text", None) or "").strip():
            summary["skipped_has_asr"] += 1
            continue
        video, audio = resolve_media_paths(row)
        if video is None and audio is None:
            # 路径可能相对且尚未 resolve 成功；仍尝试 ensure_wav
            pass
        try:
            text = transcribe_evidence_row(row)
        except Exception as e:
            print(f"[batch-asr] 异常 id={getattr(row, 'id', '?')}: {e}")
            summary["error"] += 1
            continue
        if text:
            summary["transcribed"] += 1
        else:
            summary["skipped_no_media"] += 1
    return summary


def rematch_evidence_rows(rows: list) -> dict:
    """对一批 EvidenceRecord 补比对：无 ASR 先转写再比对；有则直接比对。"""
    summary = {
        "total_candidates": len(rows),
        "matched": 0,
        "not_found": 0,
        "still_unavailable": 0,
        "skipped_no_asr": 0,
        "skipped_no_keyword": 0,
        "transcribed": 0,
        "error": 0,
    }
    for row in rows:
        keyword = (getattr(row, "search_keyword", None) or "").strip()
        if not keyword:
            summary["skipped_no_keyword"] += 1
            continue

        # 预加载台词库（找不到时后续 match 会返回 script_unavailable）
        ensure_script_for_keyword(keyword)

        asr = (getattr(row, "asr_text", None) or "").strip()
        if not asr:
            try:
                asr = transcribe_evidence_row(row)
            except Exception as e:
                print(f"[rematch] 补转写异常 id={getattr(row, 'id', '?')}: {e}")
                summary["error"] += 1
                continue
            if asr:
                summary["transcribed"] += 1
            else:
                summary["skipped_no_asr"] += 1
                continue

        sm = run_script_match(asr, keyword)
        apply_match_to_evidence_row(row, sm, asr_fallback=asr)
        st = sm.get("status") or ""
        if st == "matched":
            summary["matched"] += 1
        elif st == "script_unavailable":
            summary["still_unavailable"] += 1
        elif st == "error":
            summary["error"] += 1
        else:
            summary["not_found"] += 1
    return summary
