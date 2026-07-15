"""Script-vs-ASR text matching engine for Weixin video evidence system.

Three-layer matching strategy:
  1. Pinyin conversion – convert both query and script lines to pinyin,
     naturally filtering ASR homophone errors (e.g. 宗→松 both map to zong/song).
  2. rapidfuzz partial_ratio on pinyin – fast approximate match to collect
     top-K candidates from ~2000 dialog lines.
  3. difflib.SequenceMatcher on character level – fine-grained confirmation,
     combined with pinyin score for the final ranking.

Usage:
    from script_matcher import match_query
    result = match_query("宗也配说普渡众生", top_n=3)
    # Returns list of dicts with script_text, similarity_score, episode, scene, etc.

    # Or use the class directly for repeated queries:
    from script_matcher import get_index
    idx = get_index()
    result = idx.match("some asr text")
"""

from __future__ import annotations

import re
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import builtins as _builtins

_emit_callback = None


def _log(*args, **kwargs):
    """同 print 并可选推送到平台前端。"""
    msg = " ".join(str(a) for a in args)
    _builtins.print(msg, **kwargs)
    if _emit_callback and msg:
        if msg.startswith(("[", "  [")):
            try:
                _emit_callback(msg)
            except Exception:
                pass


# 替换本模块内所有 print 调用为 _log
print = _log

# --- Module-level singleton index ---
_index: Optional["ScriptIndex"] = None
_index_keyword: str = ""  # 记录当前索引对应的剧名

# 优先使用平台配置的 SCRIPTS_DIR（按剧名分目录），回退到 __file__ 相对路径
try:
    from config import SCRIPTS_DIR as _cfg_scripts_dir
    _SCRIPTS_DIR = os.environ.get("SCRIPTS_DIR", str(_cfg_scripts_dir))
    _DEFAULT_SCRIPT_PATH = _cfg_scripts_dir / "_default_script.txt"
except ImportError:
    _SCRIPTS_DIR = os.environ.get("SCRIPTS_DIR", "")
    _DEFAULT_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "evidence_data" / "scripts" / "_default_script.txt"


def _resolve_script_path(keyword: str = "", script_path: str | Path | None = None) -> Path | None:
    """根据剧名解析台词文件路径。

    优先级：
    1. 显式传入的 script_path
    2. SCRIPTS_DIR 环境变量 → scripts/{keyword}.txt
    3. SCRIPT_RAW_PATH 环境变量（单文件模式）
    找不到则返回 None，不随便用默认剧本
    """
    if script_path:
        return Path(script_path)
    if _SCRIPTS_DIR and keyword:
        p = Path(_SCRIPTS_DIR) / f"{keyword}.txt"
        if p.exists():
            return p
    env_path = os.environ.get("SCRIPT_RAW_PATH", "")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
    return None  # 找不到就不匹配，不兜底


def get_index(keyword: str = "", script_path: str | Path | None = None) -> "ScriptIndex | None":
    """Return the module-level singleton ScriptIndex, recreating if keyword changed.
    找不到剧本文件时返回 None。
    """
    global _index, _index_keyword
    path = _resolve_script_path(keyword, script_path)
    if path is None:
        return None
    if _index is None or _index_keyword != keyword or str(_index.script_path) != str(path):
        _index = ScriptIndex(path)
        _index_keyword = keyword
    return _index


def match_query(query_text: str, top_n: int = 3, min_pinyin_score: float = 0.40,
                keyword: str = "", script_path: str | Path | None = None) -> list[dict]:
    """Convenience wrapper: match an ASR text against the script.

    Args:
        query_text:  ASR-transcribed Chinese text.
        top_n:       Max number of results to return.
        min_pinyin_score: Minimum pinyin ratio to consider a candidate.
        keyword:     剧名（搜索关键词），用于在 scripts/{keyword}/ 目录下查找台词文件。
        script_path: 直接指定台词文件路径（优先级高于 keyword）。

    Returns up to *top_n* results, each a dict with:
        script_text, similarity_score, episode, scene, location,
        characters, char_start, char_end, pinyin_score, char_score
    """
    idx = get_index(keyword, script_path)
    if idx is None:
        return []
    return idx.match(query_text, top_n=top_n, min_pinyin_score=min_pinyin_score)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DialogLine:
    """One parsed dialog line with its context."""
    text: str                          # fully cleaned text (no parens, for matching)
    display_text: str = ""             # original text with parens kept (for display)
    character: str = ""                # speaker name
    pinyin: str = ""                   # space-joined pinyin syllables (no tones)
    clean_text: str = ""               # punctuation-stripped text for char-level matching
    pinyin_syllables: list = field(default_factory=list)  # per-character pinyin list
    episode: str = ""                  # e.g. "第1集"
    scene: str = ""                    # e.g. "1-1"
    location: str = ""                 # e.g. "顾家别墅客厅"
    characters: list[str] = field(default_factory=list)  # scene-level character list
    char_start: int = 0                # byte offset in cleaned script text
    char_end: int = 0                  # byte offset end
    line_index: int = 0                # 0-based line index


# ---------------------------------------------------------------------------
# Script parser & indexer
# ---------------------------------------------------------------------------

class ScriptIndex:
    """Load and index the script text for fast pinyin-based matching."""

    # Regex patterns for script parsing
    _RE_EPISODE = re.compile(r"^第(\d+)集[:：]\s*(.+)$")
    _RE_SCENE = re.compile(r"^(\d+-\d+)\s+([日夜])\s+([内外])\s*(.+)$")
    _RE_CHARACTERS = re.compile(r"^出场人物[:：]\s*(.+)$")
    _RE_STAGE_DIRECTION = re.compile(r"^▲")
    _RE_DIALOG = re.compile(
        r"^([^\uff08：:\n▲]+)"             # character name (stop at full-width paren or colon)
        r"(?:\s*[\uff08(][^\uff09)]*[\uff09)])?"  # optional parenthetical (action/OS)
        r"[:：]\s*(.+)$"                      # colon + dialog text
    )
    _RE_PAREN_CONTENT = re.compile(r"[\uff08(][^\uff09)]*[\uff09)]")  # strip parenthetical notes
    # Reject lines that look like character bios / descriptions
    _RE_NON_DIALOG = re.compile(
        r"^(身份标签|外形数据|身高|体重|形象|穿着风格|人设性格|参考形象)"
    )

    def __init__(self, script_path: str | Path):
        self.script_path = Path(script_path)
        self.lines: list[DialogLine] = []
        self._pinyin_to_idx: dict[str, list[int]] = {}  # pinyin prefix → line indices
        self._load_and_parse()
        self._build_index()

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _load_and_parse(self) -> None:
        """Load raw script, extract dialog lines with context."""
        raw_text = self.script_path.read_text(encoding="utf-8")

        # Split into logical lines (Windows/Linux newlines)
        raw_lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        # Detect format: structured script has episode headers like "第1集：..."
        has_episode = any(
            self._RE_EPISODE.match(line.strip()) for line in raw_lines if line.strip()
        )

        if has_episode:
            self._load_structured(raw_lines)
        else:
            self._load_plain_text(raw_lines)

    def _load_structured(self, raw_lines: list[str]) -> None:
        """Parse the structured script format with episode/scene/character metadata."""
        # Accumulate context as we scan
        current_episode = ""
        current_scene = ""
        current_location = ""
        current_characters: list[str] = []
        in_script_body = False  # True after first episode header

        char_offset = 0
        line_index = 0

        for raw_line in raw_lines:
            stripped = raw_line.strip()
            char_offset += len(raw_line.encode("utf-8"))  # approximate tracking

            # Skip empty lines
            if not stripped:
                continue

            # Episode header: 第1集：...
            m = self._RE_EPISODE.match(stripped)
            if m:
                current_episode = f"第{m.group(1)}集"
                in_script_body = True  # Enter script body
                continue

            # Skip all content before the first episode header (front matter: bios, intros)
            if not in_script_body:
                continue

            # Scene header: 1-1 日 内 顾家别墅客厅
            m = self._RE_SCENE.match(stripped)
            if m:
                current_scene = m.group(1)
                current_location = m.group(4).strip()
                continue

            # Character list: 出场人物：...
            m = self._RE_CHARACTERS.match(stripped)
            if m:
                chars_str = m.group(1)
                current_characters = [
                    c.strip() for c in chars_str.replace("、", ",").split(",") if c.strip()
                ]
                continue

            # Skip stage directions and non-dialog metadata
            if self._RE_STAGE_DIRECTION.match(stripped):
                continue
            if self._RE_NON_DIALOG.match(stripped):
                continue

            # Try to match a dialog line
            m = self._RE_DIALOG.match(stripped)
            if not m:
                continue

            char_name = m.group(1).strip()
            dialog_text = m.group(2).strip()

            # Preserve original (with parens) for display
            display_text = dialog_text

            # Fully clean: strip ALL parenthetical stage directions
            # e.g. "（声音嘶哑）流年，二十年了（抽泣），可你呢？" → "流年，二十年了，可你呢？"
            dialog_text = self._RE_PAREN_CONTENT.sub("", dialog_text).strip()

            # Skip lines that look like descriptions rather than speech
            if self._is_description_line(stripped, char_name, dialog_text):
                continue

            self._add_dialog_line(
                text=dialog_text,
                display_text=display_text,
                character=char_name,
                episode=current_episode,
                scene=current_scene,
                location=current_location,
                characters=list(current_characters),
                char_offset=char_offset,
                raw_line=raw_line,
                line_index=line_index,
            )
            line_index += 1

    def _load_plain_text(self, raw_lines: list[str]) -> None:
        """Parse a plain-text script file (one dialog line per line, no metadata).

        The current _script_raw.txt has been converted to a plain dialog format:
        each non-empty line is a line of speech.  There are no episode/scene
        headers, so we split long lines into sentence-level chunks for better
        ASR matching and index each chunk as a DialogLine with empty metadata.
        """
        char_offset = 0
        line_index = 0

        for raw_line in raw_lines:
            stripped = raw_line.strip()
            char_offset += len(raw_line.encode("utf-8"))
            if not stripped:
                continue

            # Skip lines that are just stage directions or punctuation
            if self._RE_STAGE_DIRECTION.match(stripped):
                continue
            if self._RE_NON_DIALOG.match(stripped):
                continue
            # Note: we intentionally do NOT reject long lines here.
            # _script_raw.txt is now guaranteed to be pure dialog text; long lines
            # are simply long speeches and should be split into sentence chunks.

            # Split long lines into sentence chunks for better granularity
            sentence_chunks = self._split_into_sentences(stripped)
            if not sentence_chunks:
                sentence_chunks = [stripped]

            for chunk in sentence_chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue
                # Reject chunks that are essentially punctuation-only
                clean_check = re.sub(
                    r"[，。！？、；：\u201c\u201d\u2018\u2019（）\s]", "", chunk
                )
                if len(clean_check) < 2:
                    continue

                self._add_dialog_line(
                    text=chunk,
                    display_text=chunk,
                    character="",
                    episode="",
                    scene="",
                    location="",
                    characters=[],
                    char_offset=char_offset,
                    raw_line=raw_line,
                    line_index=line_index,
                )
                line_index += 1

    @staticmethod
    def _split_into_sentences(text: str) -> list[str]:
        """Split a line of text into sentence-level chunks.

        Uses Chinese sentence-ending punctuation.  Keeps the punctuation with
        the preceding chunk so the meaning is preserved.
        """
        # Split on sentence-ending punctuation, but keep the delimiter
        parts = re.split(r"([。！？\n]+)", text)
        chunks = []
        current = ""
        for part in parts:
            if re.match(r"[。！？\n]+", part):
                current += part
                if current.strip():
                    chunks.append(current.strip())
                current = ""
            else:
                current += part
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _add_dialog_line(
        self,
        text: str,
        display_text: str,
        character: str,
        episode: str,
        scene: str,
        location: str,
        characters: list[str],
        char_offset: int,
        raw_line: str,
        line_index: int,
    ) -> None:
        """Build a DialogLine dataclass and append it to the index."""
        # Convert to pinyin from fully cleaned text
        from pypinyin import lazy_pinyin
        pinyin_syllables = lazy_pinyin(text, errors="ignore")
        pinyin_syl_list = [p for p in pinyin_syllables if p and p != " "]
        pinyin_str = " ".join(pinyin_syl_list)
        # Clean text: strip punctuation for char-level matching
        clean = re.sub(r"[，。！？、；：\u201c\u201d\u2018\u2019（）\s]", "", text)

        # Skip lines with essentially no pinyin content or too few characters.
        # Very short lines (e.g. "你……") are prone to false positives with
        # partial_ratio, so we require at least 4 meaningful characters.
        if len(pinyin_str.replace(" ", "")) < 2 or len(clean) < 4:
            return

        dl = DialogLine(
            text=text,
            display_text=display_text,
            character=character,
            pinyin=pinyin_str,
            clean_text=clean,
            pinyin_syllables=pinyin_syl_list,
            episode=episode,
            scene=scene,
            location=location,
            characters=list(characters),
            char_start=char_offset - len(raw_line.encode("utf-8")),
            char_end=char_offset,
            line_index=line_index,
        )
        self.lines.append(dl)

    @staticmethod
    def _is_description_line(raw_line: str, char_name: str, dialog_text: str) -> bool:
        """Heuristic: reject lines that are character descriptions, not speech."""
        desc_markers = (
            "身份标签", "外形数据", "身高：", "体重：", "形象：",
            "穿着风格", "人设性格", "参考形象", "性格：", "简介",
        )
        if any(m in raw_line for m in desc_markers):
            return True
        # Very long "dialog" (>200 chars) is likely description
        if len(dialog_text) > 200:
            return True
        return False

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """Build a prefix index on pinyin for fast candidate filtering."""
        for i, dl in enumerate(self.lines):
            pinyin_no_space = dl.pinyin.replace(" ", "")
            # Index by first 2 pinyin chars as quick filter
            prefix = pinyin_no_space[:4] if len(pinyin_no_space) >= 4 else pinyin_no_space
            self._pinyin_to_idx.setdefault(prefix, []).append(i)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    # Window extraction constants
    _LENGTH_RATIO = 1.1    # script window = ceil(query_len * 1.1)
    _STRIDE_DIVISOR = 3    # stride = window_len // divisor
    _WEIGHT_PINYIN = 0.6   # pinyin weight in combined score
    _WEIGHT_CHAR = 0.4     # char-level weight

    def match(
        self,
        query_text: str,
        top_n: int = 3,
        min_pinyin_score: float = 0.40,
    ) -> list[dict]:
        """Match *query_text* against the script using length-normalized windowing.

        For each candidate dialog line, we extract sliding windows of size
        ≈ ceil(query_char_len * 1.1) so that query and target are similar
        length.  This eliminates the noise from matching a 15-char ASR
        fragment against a 150-char monologue.

        Parameters:
            query_text: ASR-transcribed Chinese text.
            top_n:      Max number of results to return.
            min_pinyin_score: Minimum pinyin ratio to consider a candidate.

        Returns:
            List of result dicts sorted by similarity_score descending.
        """
        if not query_text or not self.lines:
            return []

        # ---- Layer 1: query pinyin + clean text ----
        from pypinyin import lazy_pinyin
        query_pinyin_raw = lazy_pinyin(query_text, errors="ignore")
        query_py_list = [p for p in query_pinyin_raw if p and p != " "]
        if not query_py_list:
            return []
        query_py_nospace = "".join(query_py_list)
        query_clean = re.sub(r"[，。！？、；：\u201c\u201d\u2018\u2019（）\s]", "", query_text)
        query_char_len = len(query_clean)

        # Target window character count: ceil(query_chars * 1.1)
        target_chars = max(int(query_char_len * self._LENGTH_RATIO) + 1, query_char_len + 2)

        # ---- Layer 2: length-normalized pinyin window matching ----
        from rapidfuzz import fuzz

        # With partial_ratio, the script line can be shorter or longer than the
        # query.  Scan the entire index (typically <1000 lines) to avoid missing
        # matches that happen to start at a different position in the line.
        candidates: list[tuple[int, float, str, int]] = []

        for i, dl in enumerate(self.lines):
            clean = dl.clean_text
            py_list = dl.pinyin_syllables
            line_char_len = len(clean)

            # Line too short: use full line as-is.  Use partial_ratio so that a
            # long ASR segment can still match a short script line when the line
            # is contained inside the segment.
            if line_char_len <= target_chars:
                py_win = "".join(py_list)
                score = fuzz.partial_ratio(query_py_nospace, py_win) / 100.0
                if score >= min_pinyin_score:
                    candidates.append((i, score, clean, 0))
                continue

            # Line longer: extract sliding windows of target_chars characters
            stride = max(1, target_chars // self._STRIDE_DIVISOR)
            best_score = 0.0
            best_clean_win = ""
            best_win_start = 0

            for start in range(0, line_char_len - target_chars + 1, stride):
                end = start + target_chars
                clean_win = clean[start:end]
                # Corresponding pinyin: need character-aligned slicing
                # Since clean_text strips punctuation, we can't directly slice py_list.
                # We approximate by slicing py_list proportionally and then trimming.
                # Simpler: regenerate pinyin for the window
                py_win = "".join(lazy_pinyin(clean_win, errors="ignore"))
                score = fuzz.partial_ratio(query_py_nospace, py_win) / 100.0
                if score > best_score:
                    best_score = score
                    best_clean_win = clean_win
                    best_win_start = start

            if best_score >= min_pinyin_score:
                candidates.append((i, best_score, best_clean_win, best_win_start))

        if not candidates:
            return []

        # ---- Layer 3: char-level confirmation on length-matched windows ----
        candidates.sort(key=lambda x: x[1], reverse=True)
        top_k = candidates[:max(top_n * 3, 10)]

        results = []
        for line_idx, pinyin_score, clean_win, win_start in top_k:
            dl = self.lines[line_idx]

            char_score = 0.0
            if query_clean and clean_win:
                sm = SequenceMatcher(None, query_clean, clean_win)
                char_score = sm.ratio()  # SequenceMatcher.ratio() 是对称的，无需交换参数

            combined_score = pinyin_score * self._WEIGHT_PINYIN + char_score * self._WEIGHT_CHAR

            results.append({
                "script_text": dl.display_text,  # original text with parens for display
                "script_text_clean": dl.text,    # cleaned text used for matching
                "character": dl.character,
                "similarity_score": round(combined_score, 4),
                "pinyin_score": round(pinyin_score, 4),
                "char_score": round(char_score, 4),
                "episode": dl.episode,
                "scene": dl.scene,
                "location": dl.location,
                "characters": dl.characters,
                "char_start": dl.char_start,
                "char_end": dl.char_end,
                "line_index": dl.line_index,
                "matched_window": clean_win,
                "target_chars": target_chars,
            })

        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:top_n]


def match_segmented(
    query_text: str,
    top_n: int = 3,
    min_pinyin_score: float = 0.40,
    min_combined_score: float = 0.50,
    keyword: str = "",
    script_path: str | Path | None = None,
) -> dict:
    """分段匹配：将长 ASR 文本按句子切分后逐段匹配剧本。

    解决整段 500+ 字 ASR 文本跟单句 30 字剧本对比时，
    rapidfuzz.ratio 因长度差异过大而失效的问题。

    Returns:
        {
            "status": "matched" | "not_found",
            "segments_total": int,        # 总片段数
            "segments_matched": int,      # 匹配到的片段数
            "coverage": float,            # 覆盖率 = matched/total
            "avg_similarity": float,      # 匹配片段的平均相似度
            "best_match": dict | None,    # 单句最佳匹配（兼容旧字段）
            "segments": [                 # 逐句匹配详情
                {
                    "asr_segment": str,
                    "script_text": str,
                    "similarity": float,
                    "character": str,
                    "episode": str,
                    "scene": str,
                },
                ...
            ],
        }
    """
    if not query_text:
        return {"status": "not_found", "segments_total": 0, "segments_matched": 0,
                "coverage": 0.0, "avg_similarity": 0.0, "best_match": None, "segments": []}

    path = _resolve_script_path(keyword, script_path)
    if not path:
        _emit(f"剧名「{keyword}」的台词文件不存在，跳过比对")
        return {"status": "script_unavailable", "segments_total": 0, "segments_matched": 0,
                "coverage": 0.0, "avg_similarity": 0.0, "best_match": None, "segments": []}

    idx = get_index(keyword, script_path)

    # --- 多层切分：句号 → 逗号 → 固定字数强制分块 ---
    # 第1层：按句号/感叹号/问号/换行切分
    raw_segments = re.split(r"[。！？\n]+", query_text)
    segments = [s.strip() for s in raw_segments if len(s.strip()) >= 4]

    # 第2层：句号切分太少时，尝试整段按逗号切分
    if len(segments) <= 2:
        comma_segs = [s.strip() for s in re.split(r"[，,]+", query_text) if len(s.strip()) >= 6]
        if len(comma_segs) > len(segments):
            segments = comma_segs

    # 第3层：仍只有一个大段 → 按固定字数强制切分（滑动窗口）
    if len(segments) <= 1:
        chunk_size = 15
        overlap = 3
        text = segments[0] if segments else query_text.strip()
        segments = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            seg = text[start:end].strip()
            if len(seg) >= 6:
                segments.append(seg)
            start += chunk_size - overlap

    # 第4层：即便已经分成多句，过长的单句（>40字）继续按逗号切分，
    # 避免 ASR 把两句粘成一个长串后只匹配到其中一句。
    final_segments: list[str] = []
    for seg in segments:
        if len(seg) > 40:
            comma_parts = [s.strip() for s in re.split(r"[，,]+", seg) if len(s.strip()) >= 6]
            final_segments.extend(comma_parts if comma_parts else [seg])
        else:
            final_segments.append(seg)
    segments = final_segments

    if not segments:
        segments = [query_text.strip()[:120]]  # 最后兜底

    total = len(segments)
    matched_results: list[dict] = []
    best_overall = None
    best_overall_score = 0.0

    for seg in segments:
        results = idx.match(seg, top_n=1, min_pinyin_score=min_pinyin_score)
        if results and results[0]["similarity_score"] >= min_combined_score:
            r = results[0]
            matched_results.append({
                "asr_segment": seg[:80],
                "script_text": r.get("script_text", ""),
                "similarity": r.get("similarity_score", 0.0),
                "character": r.get("character", ""),
                "episode": r.get("episode", ""),
                "scene": r.get("scene", ""),
                "location": r.get("location", ""),
            })
            if r["similarity_score"] > best_overall_score:
                best_overall_score = r["similarity_score"]
                best_overall = r

    matched_count = len(matched_results)
    coverage = matched_count / total if total > 0 else 0.0
    avg_sim = (
        sum(m["similarity"] for m in matched_results) / matched_count
        if matched_results else 0.0
    )

    status = "matched" if coverage >= 0.15 else "not_found"

    return {
        "status": status,
        "segments_total": total,
        "segments_matched": matched_count,
        "coverage": round(coverage, 4),
        "avg_similarity": round(avg_sim, 4),
        "best_match": best_overall,
        "segments": matched_results,
    }


# ---------------------------------------------------------------------------
# Standalone CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    idx = get_index()
    if idx is None:
        print("[script_matcher] 未找到剧本文件，退出")
        sys.exit(1)
    print(f"[script_matcher] Loaded {len(idx.lines)} dialog lines from script.\n")

    # Test with sample ASR texts from three_way_comparison.json
    test_queries = [
        "松也配说普度众生这倒是尤浅胆怯真想看看他如何收场用是我的小伙钱都让他们打造精神神像了那都是血汗钱啊是",
        "松也配以说普度众生，这道士有情弹气，真想看看他如何收场。又是我的小伙钳都让他们打造金神神像了，那都是虚汗钱。",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"{'='*70}")
        print(f"Query {i} ({len(query)} chars): {query[:60]}...")
        print(f"{'='*70}")
        results = match_query(query, top_n=3)
        for j, r in enumerate(results, 1):
            print(f"\n  #{j}  similarity={r['similarity_score']:.2%}  "
                  f"(pinyin={r['pinyin_score']:.2%}  char={r['char_score']:.2%})")
            print(f"        episode={r['episode']}  scene={r['scene']}  location={r['location']}")
            print(f"        speaker={r['character']}  characters={r['characters']}")
            print(f"        text: {r['script_text'][:80]}...")
        if not results:
            print("  (no matches found)")
        print()
