"""证据包构建器 — 统一证据 JSON + HTML 生成"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import EVIDENCE_DIR


class EvidenceBuilder:
    """
    证据包构建器

    为证据记录生成统一的 JSON 数据包和 HTML 预览页面。
    复用 weixin/core/store.py 的格式，同时扩展平台特有字段。
    """

    @staticmethod
    def build_json(record_dict: dict, output_dir: Optional[Path] = None) -> str:
        """
        生成证据 JSON 数据包

        Args:
            record_dict: 证据记录 dict（来自数据库或 weixin EvidenceRecord）
            output_dir: 输出目录，默认使用 EVIDENCE_DIR / task_id / video_identifier

        Returns:
            JSON 文件路径
        """
        vid = record_dict.get("video_identifier", "") or record_dict.get("candidate", {}).get("video_identifier", "")
        task_id = record_dict.get("task_id", 0)
        timestamp = record_dict.get("capture_timestamp", "") or datetime.now().strftime("%Y%m%d_%H%M%S")

        # 输出目录
        if output_dir is None:
            safe_vid = vid[:16] if vid else f"unknown_{timestamp}"
            output_dir = EVIDENCE_DIR / str(task_id) / safe_vid

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 构建证据包
        evidence_package = {
            "platform": "weixin",
            "task_id": task_id,
            "video_identifier": vid,
            "created_at": datetime.now().isoformat(),
            # 视频信息
            "video": {
                "blogger_name": record_dict.get("blogger_name", ""),
                "video_channel_id": record_dict.get("video_channel_id", ""),
                "title": record_dict.get("title", ""),
                "video_link": record_dict.get("video_link", ""),
                "publish_time": record_dict.get("publish_time", ""),
                "like_count": record_dict.get("like_count", ""),
                "comment_count": record_dict.get("comment_count", ""),
                "share_count": record_dict.get("share_count", ""),
                "favorite_count": record_dict.get("favorite_count", ""),
            },
            # 博主信息
            "profile": {
                "name": record_dict.get("profile_name", ""),
                "account": record_dict.get("profile_account", ""),
                "subject_type": record_dict.get("subject_type", ""),
                "company_full_name": record_dict.get("company_full_name", ""),
            },
            # 引流信息
            "traffic": {
                "has_traffic_marker": record_dict.get("has_traffic_marker", False),
                "marker_text": record_dict.get("traffic_marker_text", ""),
                "target_blogger_name": record_dict.get("target_blogger_name", ""),
                "target_video_channel_id": record_dict.get("target_video_channel_id", ""),
                "target_company_name": record_dict.get("target_company_name", ""),
                "target_company_verified_at": record_dict.get("target_company_verified_at", ""),
            },
            # 媒体信息
            "media": {
                "recording_video_path": record_dict.get("recording_video_path", ""),
                "recording_audio_path": record_dict.get("recording_audio_path", ""),
                "recording_duration_seconds": record_dict.get("recording_duration_seconds", 0),
                "has_audio": record_dict.get("has_audio", False),
                "asr_text": record_dict.get("asr_text", ""),
                "asr_model": record_dict.get("asr_model", ""),
            },
            # 剧本比对
            "script_match": {
                "status": record_dict.get("script_match_status", "pending"),
                "similarity": record_dict.get("script_match_similarity", 0.0),
                "episode": record_dict.get("script_match_episode", ""),
                "scene": record_dict.get("script_match_scene", ""),
            },
            # 截图列表
            "screenshots": EvidenceBuilder._parse_screenshots(record_dict),
            # 复核状态
            "review": {
                "status": record_dict.get("review_status", ""),
                "reviewer": record_dict.get("reviewer", ""),
                "notes": record_dict.get("review_notes", ""),
            },
        }

        # 写入文件
        safe_vid = vid[:16] if vid else f"unknown_{timestamp}"
        filename = f"result_{safe_vid}.json"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(evidence_package, f, ensure_ascii=False, indent=2)

        return str(filepath)

    @staticmethod
    def build_html(record_dict: dict, json_path: Optional[str] = None) -> str:
        """
        生成证据 HTML 预览页面

        Args:
            record_dict: 证据记录 dict
            json_path: 已生成的 JSON 文件路径（用于确定输出目录）

        Returns:
            HTML 文件路径
        """
        vid = record_dict.get("video_identifier", "") or record_dict.get("candidate", {}).get("video_identifier", "")
        task_id = record_dict.get("task_id", 0)

        # 输出目录
        if json_path:
            output_dir = Path(json_path).parent
        else:
            safe_vid = vid[:16] if vid else "unknown"
            output_dir = EVIDENCE_DIR / str(task_id) / safe_vid

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 提取数据
        video = {
            "title": record_dict.get("title", "未知标题"),
            "blogger_name": record_dict.get("blogger_name", "未知博主"),
            "video_channel_id": record_dict.get("video_channel_id", ""),
            "publish_time": record_dict.get("publish_time", ""),
            "like_count": record_dict.get("like_count", ""),
            "comment_count": record_dict.get("comment_count", ""),
            "share_count": record_dict.get("share_count", ""),
            "video_link": record_dict.get("video_link", ""),
        }
        profile = {
            "name": record_dict.get("profile_name", ""),
            "account": record_dict.get("profile_account", ""),
            "subject_type": record_dict.get("subject_type", ""),
            "company_full_name": record_dict.get("company_full_name", ""),
        }
        traffic = {
            "has_marker": record_dict.get("has_traffic_marker", False),
            "marker_text": record_dict.get("traffic_marker_text", ""),
            "target_name": record_dict.get("target_blogger_name", ""),
            "target_company": record_dict.get("target_company_name", ""),
        }
        asr_text = record_dict.get("asr_text", "") or ""
        script_match = {
            "status": record_dict.get("script_match_status", ""),
            "similarity": record_dict.get("script_match_similarity", 0),
            "episode": record_dict.get("script_match_episode", ""),
            "scene": record_dict.get("script_match_scene", ""),
        }
        screenshots = EvidenceBuilder._parse_screenshots(record_dict)
        recording_path = record_dict.get("recording_video_path", "")
        review_status = record_dict.get("review_status", "")

        review_color = {
            "侵权": "#cf222e",
            "未侵权": "#2da44e",
            "": "#d29922",
        }.get(review_status, "#d29922")

        # 截图画廊 HTML
        screenshots_html = ""
        if screenshots:
            screenshots_html = '<div class="screenshot-gallery">\n'
            for i, s in enumerate(screenshots):
                src = s if isinstance(s, str) else s.get("path", "")
                label = s.get("label", f"截图{i+1}") if isinstance(s, dict) else f"截图{i+1}"
                screenshots_html += f'  <div class="screenshot-item"><img src="{src}" /><span>{label}</span></div>\n'
            screenshots_html += '</div>\n'

        # 录屏播放器
        recorder_html = ""
        if recording_path:
            recorder_html = f'<video controls width="100%"><source src="{recording_path}" type="video/mp4"></video>'

        # 剧本匹配结果
        script_html = ""
        if script_match.get("status") == "matched":
            script_html = f"""
            <div class="script-match matched">
                <strong>剧本已匹配</strong> — 相似度: {script_match.get('similarity', 0):.1%}，
                集号: {script_match.get('episode', '')}，场景: {script_match.get('scene', '')}
            </div>"""
        elif script_match.get("status") == "not_found":
            script_html = '<div class="script-match not-found"><strong>未匹配到剧本</strong></div>'

        # 完整 HTML
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>证据报告 - {video.get('title', '')}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; background: #f6f4ef; color: #22211f; padding: 20px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .header {{ background: #fffdf8; border-radius: 8px; padding: 24px; margin-bottom: 20px; border: 1px solid #ddd5c8; }}
  .header h1 {{ font-size: 20px; margin-bottom: 8px; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; color: white; background: {review_color}; }}
  .section {{ background: #fffdf8; border-radius: 8px; padding: 20px; margin-bottom: 16px; border: 1px solid #ddd5c8; }}
  .section h2 {{ font-size: 16px; margin-bottom: 12px; color: #1f6f68; }}
  .kv-list {{ display: grid; grid-template-columns: 120px 1fr; gap: 8px 16px; }}
  .kv-list dt {{ color: #6d675f; font-size: 13px; }}
  .kv-list dd {{ font-size: 14px; }}
  .screenshot-gallery {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .screenshot-item {{ width: 180px; text-align: center; }}
  .screenshot-item img {{ width: 100%; border-radius: 4px; border: 1px solid #ddd5c8; }}
  .screenshot-item span {{ font-size: 11px; color: #6d675f; }}
  .script-match {{ padding: 12px; border-radius: 4px; font-size: 14px; }}
  .script-match.matched {{ background: #e6ffec; border: 1px solid #2da44e; }}
  .script-match.not-found {{ background: #fff5e6; border: 1px solid #d29922; }}
  .asr-text {{ background: #f8f9fa; padding: 16px; border-radius: 4px; font-size: 14px; line-height: 1.8; }}
  .footer {{ text-align: center; color: #6d675f; font-size: 12px; padding: 20px; }}
</style>
</head>
<body>
<div class="container">

  <!-- 头部 -->
  <div class="header">
    <h1>{video.get('title', '证据报告')}</h1>
    <p style="color:#6d675f;font-size:13px;">
      ID: {vid[:16] if vid else 'N/A'} &nbsp;|&nbsp;
      采集时间: {record_dict.get('capture_timestamp', '')} &nbsp;|&nbsp;
      <span class="badge">{review_status}</span>
    </p>
  </div>

  <!-- 视频信息 -->
  <div class="section">
    <h2>视频信息</h2>
    <dl class="kv-list">
      <dt>博主</dt><dd>{video.get('blogger_name', '')}</dd>
      <dt>视频号ID</dt><dd><code>{video.get('video_channel_id', '')}</code></dd>
      <dt>发布时间</dt><dd>{video.get('publish_time', '')}</dd>
      <dt>喜欢</dt><dd>{video.get('like_count', '')}</dd>
      <dt>评论</dt><dd>{video.get('comment_count', '')}</dd>
      <dt>分享</dt><dd>{video.get('share_count', '')}</dd>
      <dt>链接</dt><dd style="word-break:break-all;"><a href="{video.get('video_link', '#')}">{video.get('video_link', '')}</a></dd>
    </dl>
  </div>

  <!-- 博主信息 -->
  <div class="section">
    <h2>博主信息</h2>
    <dl class="kv-list">
      <dt>名称</dt><dd>{profile.get('name', '')}</dd>
      <dt>ID</dt><dd>{profile.get('account', '')}</dd>
      <dt>主体类型</dt><dd>{profile.get('subject_type', '')}</dd>
      <dt>企业全称</dt><dd>{profile.get('company_full_name', '')}</dd>
    </dl>
  </div>

  <!-- 引流信息 -->
  {"<div class='section'><h2>引流信息</h2><dl class='kv-list'><dt>引流标记</dt><dd>" + traffic.get('marker_text', '') + "</dd><dt>目标博主</dt><dd>" + traffic.get('target_name', '') + "</dd><dt>目标企业</dt><dd>" + traffic.get('target_company', '') + "</dd></dl></div>" if traffic.get('has_marker') else ""}

  <!-- 录屏播放器 -->
  {"<div class='section'><h2>录屏</h2>" + recorder_html + "</div>" if recorder_html else ""}

  <!-- 截图画廊 -->
  {"<div class='section'><h2>截图 (" + str(len(screenshots)) + ")</h2>" + screenshots_html + "</div>" if screenshots_html else ""}

  <!-- ASR 转写 -->
  {"<div class='section'><h2>ASR 转写</h2><div class='asr-text'>" + asr_text + "</div></div>" if asr_text else ""}

  <!-- 剧本匹配 -->
  {script_html}

  <!-- 页脚 -->
  <div class="footer">
    由嘉剧荟自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  </div>

</div>
</body>
</html>"""

        # 写入文件
        safe_vid = vid[:16] if vid else "unknown"
        filename = f"result_{safe_vid}.html"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        return str(filepath)

    @staticmethod
    def _parse_screenshots(record_dict: dict) -> list:
        """解析截图列表"""
        raw = record_dict.get("screenshots_json", "[]")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(raw, list):
            return raw
        # 尝试从 record dict 的 candidate/media_info 中提取
        screenshots = record_dict.get("screenshots", [])
        if screenshots:
            return screenshots
        return []
