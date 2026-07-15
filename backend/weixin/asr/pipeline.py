"""ASR pipeline — 讯飞云 ASR + 剧本比对"""
from __future__ import annotations


def run_asr_pipeline(record, wav_path: str, video_identifier: str) -> None:
    """Run ASR with iFlytek cloud, then script matching.

    After successful transcription, script matching is automatically triggered.
    """
    # iFlytek cloud ASR
    from .xunfei import core_transcribe_for_record
    core_transcribe_for_record(record, wav_path, video_identifier)
    _run_script_match(record)


def _run_script_match(record) -> None:
    """Match ASR text against the reference script using segmented matching.

    Populates record.media_info['script_match'].
    """
    try:
        from .script_matcher import match_segmented, match_query
        asr_text = record.media_info.get("asr_text", "")
        if not asr_text:
            record.media_info["script_match"] = {"status": "not_found", "error": "no asr_text"}
            return

        keyword = getattr(record, 'search_keyword', '') or ''

        result = match_segmented(asr_text, top_n=1, keyword=keyword)
        legacy = match_query(asr_text, top_n=3, keyword=keyword)

        if result["status"] == "matched":
            record.media_info["script_match"] = {
                "status": "matched",
                "best_match": result["best_match"],
                "top_candidates": legacy if legacy else [],
                "segments_matched": result["segments_matched"],
                "segments_total": result["segments_total"],
                "coverage": result["coverage"],
                "avg_similarity": result["avg_similarity"],
                "segments": result["segments"],
            }
        else:
            record.media_info["script_match"] = {
                "status": "not_found",
                "best_match": None,
                "top_candidates": legacy,
                "segments_matched": 0,
                "segments_total": result["segments_total"],
                "coverage": 0.0,
                "avg_similarity": 0.0,
                "segments": [],
            }
    except FileNotFoundError:
        record.media_info["script_match"] = {"status": "script_unavailable"}
    except ImportError as e:
        record.media_info["script_match"] = {"status": "script_unavailable", "error": str(e)}
    except Exception as e:
        record.media_info["script_match"] = {"status": "error", "error": str(e)}
