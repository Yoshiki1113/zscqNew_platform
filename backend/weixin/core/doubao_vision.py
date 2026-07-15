"""豆包视觉模型 — 用于替代 PaddleOCR 提取结构化字段

调用火山引擎 Ark API（OpenAI 兼容接口），将截图发送给豆包视觉模型，
让模型直接返回结构化 JSON 字段（博主名/公司名/视频标题/视频号ID 等）。

设计要点：
1. 同步调用 httpx.Client，由 collector 在 asyncio.run 内部直接调用
2. 豆包优先：成功则跳过 PaddleOCR，失败则由 collector 回退到 PaddleOCR
3. 图片预处理：长边缩放到 1600px + JPEG 85% 压缩，控制 base64 体积
4. JSON 解析容错：支持 ```json 代码块包裹、裸 JSON、自然语言混合
"""
from __future__ import annotations

import base64
import json
import os
import re
from io import BytesIO
from typing import Optional

import httpx

# 配置在 collector 导入时已可用（config 路径已由 main.py 设置）
try:
    from config import (
        ARK_API_KEY,
        ARK_MODEL,
        ARK_BASE_URL,
        ARK_VISION_TIMEOUT,
        ARK_VISION_ENABLED,
        ARK_VISION_MAX_IMAGE_SIZE,
        ARK_VISION_JPEG_QUALITY,
    )
except ImportError:
    # 兜底：直接读取环境变量，避免 config 未加载时报错
    ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
    ARK_MODEL = os.environ.get("ARK_MODEL", "doubao-seed-2-0-mini-260428")
    ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")
    ARK_VISION_TIMEOUT = int(os.environ.get("ARK_VISION_TIMEOUT", "60"))
    ARK_VISION_ENABLED = os.environ.get("ARK_VISION_ENABLED", "1") not in ("0", "false", "no")
    ARK_VISION_MAX_IMAGE_SIZE = int(os.environ.get("ARK_VISION_MAX_IMAGE_SIZE", "1600"))
    ARK_VISION_JPEG_QUALITY = int(os.environ.get("ARK_VISION_JPEG_QUALITY", "85"))


# 博主名过滤词（与 collector.is_probable_author_name 保持一致）
_AUTHOR_NOISE_TOKENS = (
    "关注", "私信", "视频号", "账号", "企业", "公司",
    "原创", "主页", "剧集", "作品", "粉丝", "获赞",
    "评论", "IP", "归属地", "资料", "搜索", "更多",
    "博主", "名称", "昵称",
)


def _encode_image(image_path: str) -> Optional[str]:
    """读取图片并 base64 编码（JPEG 压缩 + 长边缩放）"""
    if not os.path.isfile(image_path):
        print(f"[豆包] 图片不存在: {image_path}")
        return None
    try:
        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        max_side = max(img.size)
        if max_side > ARK_VISION_MAX_IMAGE_SIZE:
            ratio = ARK_VISION_MAX_IMAGE_SIZE / max_side
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=ARK_VISION_JPEG_QUALITY)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"[豆包] 图片编码失败 {image_path}: {e}")
        return None


def _call_doubao(image_path: str, prompt: str) -> Optional[str]:
    """调用豆包视觉 API，返回模型回复文本

    Args:
        image_path: 图片文件路径
        prompt: 提示词

    Returns:
        模型回复文本；失败返回 None
    """
    if not ARK_VISION_ENABLED:
        return None
    if not ARK_API_KEY:
        print("[豆包] ARK_API_KEY 未配置，跳过")
        return None

    image_b64 = _encode_image(image_path)
    if not image_b64:
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ARK_API_KEY}",
    }
    payload = {
        "model": ARK_MODEL,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "thinking": {"type": "disabled"},
    }

    try:
        with httpx.Client(timeout=ARK_VISION_TIMEOUT) as http:
            resp = http.post(
                f"{ARK_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
        if resp.status_code != 200:
            print(f"[豆包] HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        result = resp.json()
        for choice in result.get("choices", []):
            content = choice.get("message", {}).get("content", "")
            if content:
                return content
        return None
    except Exception as e:
        print(f"[豆包] API 调用失败: {e}")
        return None


def _parse_json_response(text: str) -> Optional[dict]:
    """从模型回复中解析 JSON

    支持：
    1. 纯 JSON
    2. ```json ... ``` 代码块包裹
    3. 文本中夹杂的 {...}
    """
    if not text:
        return None
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # 尝试从 ```json ... ``` 或 ``` ... ``` 中提取
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    # 尝试提取第一个 {...}（贪心匹配到最后一个 }）
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _clean_blogger_name(name: str) -> str:
    """清理豆包返回的博主名"""
    if not name:
        return ""
    # 去掉引号、换行、首尾空白
    name = name.strip().strip("\"'""''").split("\n")[0].strip()
    # 去掉可能的前缀（如"博主名称："）
    for sep in ("：", ":"):
        if sep in name:
            parts = name.split(sep, 1)
            if len(parts) == 2 and parts[0] in ("博主名称", "博主", "昵称", "名称"):
                name = parts[1].strip()
                break
    # 长度过滤
    if len(name) < 2 or len(name) > 32:
        return ""
    # 噪声词过滤
    if any(token in name for token in _AUTHOR_NOISE_TOKENS):
        return ""
    # 必须包含中文/英文/数字
    if not re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", name):
        return ""
    return name


# ═══════════════════════════════════════════════════════════════
# 场景化提取函数
# ═══════════════════════════════════════════════════════════════

def extract_blogger_name_from_card(image_path: str) -> Optional[str]:
    """从博主资料卡截图提取博主名称（昵称）

    用于：
    - 视频博主资料卡 profile_card_*.png
    - 引流博主资料卡 traffic_page_*.png
    """
    prompt = (
        "这是微信视频号的博主资料卡截图。请提取博主名称（昵称）。\n"
        "要求：\n"
        "1. 只返回博主名称本身，不要加任何前缀、引号或解释\n"
        "2. 不要返回公司名称、企业全称、视频号ID、关注按钮文字\n"
        "3. 如果无法识别，返回空字符串"
    )
    text = _call_doubao(image_path, prompt)
    if not text:
        return None
    name = _clean_blogger_name(text)
    if name:
        print(f"[豆包] 博主名称提取成功: {name}")
        return name
    print(f"[豆包] 博主名称提取失败，原文: {text[:80]!r}")
    return None


def extract_video_fields_from_play(image_path: str) -> Optional[dict]:
    """从视频播放页截图提取博主名/标题/发布时间/统计数

    Returns:
        {
            "blogger_name": str,
            "title": str,
            "publish_time": str,
            "like_count": str,
            "comment_count": str,
            "share_count": str,
        }
    """
    prompt = (
        "这是微信视频号的视频播放页截图。请提取以下字段，以 JSON 格式返回：\n"
        "{\n"
        '  "blogger_name": "博主名称（昵称，位于左下角头像旁）",\n'
        '  "title": "视频标题（描述性文字，通常较长，保留完整的 # 话题标签）",\n'
        '  "publish_time": "发布时间（如 2天前 或 2026-06-22）",\n'
        '  "like_count": "点赞数（如 1.2w 或 856）",\n'
        '  "comment_count": "评论数",\n'
        '  "share_count": "分享数"\n'
        "}\n"
        "要求：\n"
        "1. 只返回 JSON，不要加任何解释文字或 markdown 标记\n"
        "2. 数字保留原格式（如 1.2w、856）\n"
        "3. 找不到的字段返回空字符串\n"
        "4. 标题必须保留完整原始内容，包括 # 话题标签，不要删改"
    )
    text = _call_doubao(image_path, prompt)
    if not text:
        return None
    data = _parse_json_response(text)
    if not data:
        print(f"[豆包] 播放页字段 JSON 解析失败，原文: {text[:200]!r}")
        return None
    # 清理博主名
    if data.get("blogger_name"):
        cleaned = _clean_blogger_name(data["blogger_name"])
        data["blogger_name"] = cleaned
    # 统计数统一转字符串
    for key in ("like_count", "comment_count", "share_count"):
        if data.get(key) is not None:
            data[key] = str(data[key]).strip()
    print(f"[豆包] 播放页字段提取成功: 博主={data.get('blogger_name', '')[:20]} "
          f"标题={data.get('title', '')[:20]}")
    return data


def extract_profile_info(image_path: str) -> Optional[dict]:
    """从博主更多信息页截图提取视频号ID/企业全称/主体类型

    Returns:
        {
            "video_channel_id": str,    # 视频号ID（sph 开头或纯字母数字串）
            "company_full_name": str,   # 企业全称
            "subject_type": str,        # 企业 / 个人
        }
    """
    prompt = (
        "这是微信视频号博主信息页截图。请提取以下字段，以 JSON 格式返回：\n"
        "{\n"
        '  "video_channel_id": "视频号ID（通常以 sph 开头，或纯字母数字串）",\n'
        '  "company_full_name": "企业全称（仅企业主体有，含有限公司等字样）",\n'
        '  "subject_type": "主体类型：企业 或 个人"\n'
        "}\n"
        "要求：\n"
        "1. 只返回 JSON，不要加任何解释文字或 markdown 标记\n"
        "2. 字段不存在时返回空字符串\n"
        "3. 企业全称必须是完整的公司名称，包含 有限公司 或 有限责任公司 字样\n"
        "4. 主体类型只能填 企业 或 个人，不能填其他值"
    )
    text = _call_doubao(image_path, prompt)
    if not text:
        return None
    data = _parse_json_response(text)
    if not data:
        print(f"[豆包] 博主信息页 JSON 解析失败，原文: {text[:200]!r}")
        return None
    print(f"[豆包] 博主信息页提取成功: ID={data.get('video_channel_id', '')[:20]} "
          f"企业={data.get('company_full_name', '')[:20]} "
          f"类型={data.get('subject_type', '')}")
    return data


def extract_traffic_info(image_path: str) -> Optional[dict]:
    """从引流博主信息页截图提取视频号ID/企业全称/认证时间

    Returns:
        {
            "target_video_channel_id": str,
            "company_full_name": str,
            "company_verified_at": str,
        }
    """
    prompt = (
        "这是微信视频号博主信息页截图（该博主是引流目标账号）。请提取以下字段，以 JSON 格式返回：\n"
        "{\n"
        '  "target_video_channel_id": "视频号ID（通常以 sph 开头，或纯字母数字串）",\n'
        '  "company_full_name": "企业全称（含有限公司等字样）",\n'
        '  "company_verified_at": "认证时间（如 2023年6月15日）"\n'
        "}\n"
        "要求：\n"
        "1. 只返回 JSON，不要加任何解释文字或 markdown 标记\n"
        "2. 字段不存在时返回空字符串"
    )
    text = _call_doubao(image_path, prompt)
    if not text:
        return None
    data = _parse_json_response(text)
    if not data:
        print(f"[豆包] 引流信息页 JSON 解析失败，原文: {text[:200]!r}")
        return None
    print(f"[豆包] 引流信息页提取成功: ID={data.get('target_video_channel_id', '')[:20]} "
          f"企业={data.get('company_full_name', '')[:20]}")
    return data


def extract_traffic_video_name_from_popup(image_path: str) -> str:
    """从引流弹窗截图提取引流视频名称。

    引流弹窗是点击"免费剧集/全N集"标记后弹出的浮层，
    通常显示引流短剧的剧名、集数等信息。

    Args:
        image_path: 引流弹窗截图路径

    Returns:
        引流视频名称（纯文本），失败返回空字符串
    """
    prompt = (
        "这是微信视频号的引流弹窗截图（点击「免费剧集/全N集」等引流标记后弹出的浮层）。"
        "请提取引流视频的名称（剧名）。\n"
        "要求：\n"
        "1. 只返回视频名称本身，不要加任何解释文字、引号或 markdown 标记\n"
        "2. 视频名称通常是弹窗顶部或中央的标题文字，不包含集数、简介等\n"
        "3. 如果无法识别，返回空字符串"
    )
    text = _call_doubao(image_path, prompt)
    if not text:
        return ""
    # 去除可能的引号和首尾空白
    name = text.strip().strip('"').strip("'").strip(""").strip(""").strip()
    # 过滤明显的噪声文本
    _NOISE_TOKENS = ("免费", "全集", "观看", "剧集", "立即", "查看", "弹窗", "截图", "视频号")
    if name and any(token in name for token in _NOISE_TOKENS) and len(name) < 10:
        print(f"[豆包] 引流视频名称疑似噪声，丢弃: {name!r}")
        return ""
    if name:
        print(f"[豆包] 引流视频名称提取成功: {name}")
    return name


# ═══════════════════════════════════════════════════════════════
# 可用性检查（供 prewarm 调用）
# ═══════════════════════════════════════════════════════════════

def locate_traffic_marker(image_path: str) -> Optional[tuple[float, float, str]]:
    """[已废弃] 豆包定位引流标记坐标 — 已改用颜色过滤（collector.find_traffic_marker_candidates_by_color），保留备用"""
    """定位引流标记在截图中的归一化中心坐标

    返回:
        (center_x_ratio, center_y_ratio, marker_text) 或 None
        坐标为相对于图片宽高的 0-1 比例
    """
    prompt = (
        "这是微信视频号播放页截图。请找到屏幕中带有“免费剧集”或“全N集”文字的灰色提示条。\n"
        "该提示条通常位于屏幕中下部，左侧有一个橙色播放图标（▶），文字类似“免费剧集：XXX 全51集”。\n"
        "注意：不要误识别最底部的“可能含有AI生成内容”或其他灰色提示框，目标必须包含“免费剧集”字样。\n"
        "返回该提示条的几何中心点坐标和四个角的比例坐标，坐标范围 0.0-1.0。\n"
        "只返回 JSON 格式，不要任何解释：\n"
        '{"found": true, "center_x": 0.35, "center_y": 0.74, "left": 0.05, "top": 0.72, "right": 0.65, "bottom": 0.76, "text": "免费剧集：XXX 全N集"}\n'
        "如果没找到，返回：{\"found\": false}"
    )
    text = _call_doubao(image_path, prompt)
    if not text:
        return None
    data = _parse_json_response(text)
    if not data or not data.get("found"):
        print(f"[豆包] 未识别到引流标记: {text[:200]}")
        return None
    try:
        cx = float(data.get("center_x", 0))
        cy = float(data.get("center_y", 0))
        # 如果有 bounding box，用 bbox 中心更稳
        left = data.get("left")
        right = data.get("right")
        top = data.get("top")
        bottom = data.get("bottom")
        if all(v is not None for v in (left, right, top, bottom)):
            cx = (float(left) + float(right)) / 2
            cy = (float(top) + float(bottom)) / 2
        marker_text = str(data.get("text", "")).strip()
        if 0 <= cx <= 1 and 0 <= cy <= 1:
            return (cx, cy, marker_text)
    except (ValueError, TypeError):
        pass
    print(f"[豆包] 引流标记坐标解析失败: {text[:200]}")
    return None


def check_availability() -> dict:
    """检查豆包视觉 API 是否可用（不发送图片，只发一条纯文本请求）"""
    result = {
        "enabled": ARK_VISION_ENABLED,
        "configured": bool(ARK_API_KEY),
        "model": ARK_MODEL,
        "base_url": ARK_BASE_URL,
        "ok": False,
        "error": "",
    }
    if not ARK_VISION_ENABLED:
        result["error"] = "ARK_VISION_ENABLED=0"
        return result
    if not ARK_API_KEY:
        result["error"] = "ARK_API_KEY 未配置"
        return result

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ARK_API_KEY}",
    }
    payload = {
        "model": ARK_MODEL,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "ping"}],
        "thinking": {"type": "disabled"},
    }
    try:
        with httpx.Client(timeout=15) as http:
            resp = http.post(
                f"{ARK_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
        if resp.status_code == 200:
            result["ok"] = True
        else:
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        result["error"] = str(e)
    return result


def find_goto_weixin_button(image_path: str) -> tuple | None:
    """[已废弃] 豆包识别"前往微信"按钮位置 — 已改用固定坐标（main.click_goto_weixin_button），保留备用"""
    """使用豆包视觉识别浏览器弹窗中"前往微信"按钮的中心位置

    手机浏览器打开微信视频号链接后会弹出"可前往微信观看此内容"弹窗，
    弹窗底部从左到右有两个按钮："取消"和"前往微信"。

    Args:
        image_path: 手机截图路径

    Returns:
        (x, y) 按钮中心相对于整张图片的归一化坐标（0~1），找不到返回 None
    """
    if not ARK_VISION_ENABLED or not ARK_API_KEY:
        return None

    b64 = _encode_image(image_path)
    if not b64:
        return None

    prompt = (
        "这张截图是手机浏览器打开微信视频号分享链接后弹出的页面。"
        "页面上会有一个弹窗，提示\"可前往微信观看此内容\"，弹窗底部从左到右有两个按钮："
        "\"取消\"和\"前往微信\"。\n"
        "请识别\"前往微信\"按钮（右侧那个按钮）的中心位置，"
        "返回按钮中心点相对于整张图片的坐标比例（0~1 的小数，x 为水平方向，y 为垂直方向）。\n"
        "严格只返回 JSON，格式：{\"x\": 0.72, \"y\": 0.62}。"
        "如果找不到该按钮或图片不是这种弹窗，返回：{\"x\": -1, \"y\": -1}。"
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ARK_API_KEY}",
    }
    payload = {
        "model": ARK_MODEL,
        "max_tokens": 64,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": prompt},
            ],
        }],
    }

    import httpx
    try:
        with httpx.Client(timeout=ARK_VISION_TIMEOUT) as http:
            resp = http.post(f"{ARK_BASE_URL}/chat/completions", headers=headers, json=payload)
        if resp.status_code != 200:
            print(f"[豆包] 前往微信按钮 HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        result = resp.json()
        for choice in result.get("choices", []):
            content = choice.get("message", {}).get("content", "").strip()
            if not content:
                continue
            m = re.search(r"\{[^}]+\}", content)
            if not m:
                print(f"[豆包] 回复无法解析: {content!r}")
                continue
            obj = json.loads(m.group(0))
            x = float(obj.get("x", -1))
            y = float(obj.get("y", -1))
            if x < 0 or y < 0:
                print(f"[豆包] 识别为找不到按钮: {obj}")
                return None
            return (x, y)
    except Exception as e:
        print(f"[豆包] 前往微信按钮识别失败: {e}")
    return None
