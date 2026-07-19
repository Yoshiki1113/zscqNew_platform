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
    from engine.script_rematch import run_script_match

    asr_text = (record.media_info or {}).get("asr_text", "")
    keyword = getattr(record, "search_keyword", "") or ""
    record.media_info["script_match"] = run_script_match(asr_text, keyword)
