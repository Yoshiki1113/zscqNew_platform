# 嘉剧荟 — 短剧侵权识别平台

> 微信视频号知识产权侵权证据采集与审核平台

---

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 系统架构](#2-系统架构)
- [3. 后端技术详解](#3-后端技术详解)
- [4. 前端技术概述](#4-前端技术概述)
- [5. 数据模型](#5-数据模型)
- [6. API 接口](#6-api-接口)
- [7. 核心业务流程](#7-核心业务流程)
- [8. 目录结构](#8-目录结构)
- [9. 部署与启动](#9-部署与启动)

---

## 1. 项目概述

### 1.1 背景

短剧行业侵权现象严重，侵权方通过微信视频号等平台发布盗版内容，需要高效、自动化的取证手段来固定证据。本项目构建了一个完整的 **Web 可视化取证平台**，将现有的命令行采集脚本封装为可远程调用的后端服务，并提供 Web 界面用于任务管理、实时监控、证据浏览和人工复核。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **二阶段采集** | 阶段一：搜索 → 收集视频链接；阶段二：逐链接完整取证（录屏/截图/OCR/引流/博主信息） |
| **ASR 台词比对** | 语音转文字后与剧本拼音+字符双维度匹配，自动判定侵权疑似度 |
| **引流检测** | OCR 识别"免费剧集""全XX集"等引流标记，追踪目标账号 |
| **侵权线索匹配** | 与黑名单 Excel 导入的账号+作品名精确匹配，命中直接标记高度疑似 |
| **证据包生成** | 每条视频输出 JSON 数据包 + HTML 预览页面 + 截图/录屏文件 |
| **人工复核** | 侵权/未侵权标注，支持单条和批量操作 |
| **博主聚合** | 按视频号 ID 聚类统计各博主的侵权视频数量 |
| **实时监控** | WebSocket 推送任务执行日志、进度、当前截图至前端 |

### 1.3 设计原则

- **代码复用最大化**：不重写 `weixin/core/` 已验证的采集逻辑，`WeixinCollector` 做薄封装层
- **平台隔离**：平台数据库独立于采集模块数据库，通过事件回调异步通信
- **扩展预留**：架构保留多平台接入接口，后续可接入快手、抖音

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                 可视化前端 (Vue 3 + Element Plus)             │
│    首页 │ 链接池 │ 任务列表 │ 执行监控 │ 证据列表 │ 复核池    │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTP REST / WebSocket
┌──────────────────────────┴──────────────────────────────────┐
│              后端 API (Python FastAPI + asyncio)             │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌────────────┐  │
│  │ 任务管理  │ │ 证据查询  │ │ 复核系统 │ │ 博主聚合   │  │
│  └─────┬─────┘ └─────┬─────┘ └────┬─────┘ └─────┬──────┘  │
│        └──────────────┴────────────┴─────────────┘          │
│                           │ SQLAlchemy ORM                  │
│                    ┌──────┴──────┐                          │
│                    │   SQLite    │                          │
│                    └──────┬──────┘                          │
│  ┌────────────────────────┴──────────────────────────┐     │
│  │              取证引擎层 (engine/)                   │     │
│  │  ┌─────────────────────────────────────────────┐  │     │
│  │  │ TaskScheduler  →  asyncio 任务队列 + 状态机  │  │     │
│  │  │ TaskRunner     →  单任务生命周期管理          │  │     │
│  │  └────────────────────┬────────────────────────┘  │     │
│  │  ┌────────────────────┴────────────────────────┐  │     │
│  │  │ WeixinCollector                              │  │     │
│  │  │ 封装 weixin/core/ — collector/navigator/store │  │     │
│  │  └────────────────────┬────────────────────────┘  │     │
│  │  ┌────────────────────┴────────────────────────┐  │     │
│  │  │ DeviceManager  —  ADB + scrcpy + AScript MCP│  │     │
│  │  └─────────────────────────────────────────────┘  │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 后端技术详解

### 3.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| **Python** | 3.11+ | 主要语言 |
| **FastAPI** | ≥0.110 | 异步 Web 框架，自动生成 OpenAPI 文档 |
| **Uvicorn** | ≥0.40 | ASGI 服务器 |
| **SQLAlchemy** | ≥2.0 | 异步 ORM，核心查询用 `select()` + `outerjoin()` + 相关子查询 |
| **aiosqlite** | ≥0.19 | SQLite 异步驱动 |
| **websockets** | ≥12.0 | WebSocket 实时日志推送 |
| **Pillow** | ≥9.0 | 图像处理（豆包视觉模型图片预处理） |
| **loguru** | ≥0.7 | 结构化日志 |
| **httpx** | ≥0.27 | 异步 HTTP 客户端 |

**采集层依赖**（`weixin/` 目录内）：
- **PaddleOCR** — 离线 OCR 文字识别
- **sherpa-onnx** — SenseVoice / Paraformer 离线语音识别模型
- **pypinyin + rapidfuzz** — 拼音转换 + 模糊匹配（剧本比对核心）
- **difflib** — 字符级相似度确认
- **ADB + scrcpy** — Android 设备控制与录屏
- **豆包视觉模型**（火山引擎 Ark API）— 结构化字段提取替代 PaddleOCR

### 3.2 核心模块

#### 3.2.1 数据库层 (`database.py` + `models/`)

使用 SQLAlchemy 2.0 异步 ORM，声明式模型。

**数据库连接**：通过 `async_sessionmaker` 创建异步 session，`get_db()` 作为 FastAPI `Depends` 注入。

**自动迁移**：`init_db()` 调用 `Base.metadata.create_all()` 建表，同时执行增量 SQL 兼容已有数据库：

```python
# 例：已有 tasks 表加 phase 列
await conn.run_sync(
    lambda c: c.exec_driver_sql("ALTER TABLE tasks ADD COLUMN phase INTEGER DEFAULT 1")
)
```

#### 3.2.2 任务调度器 (`engine/task_scheduler.py`)

纯 asyncio 实现，不引入 Celery 等重依赖。

**核心类：**

| 类 | 职责 |
|----|------|
| `TaskScheduler` | 全局单例，管理 `dict[int, TaskRunner]`，提供 `start_task` / `stop_task` / `start_phase2` |
| `TaskRunner` | 单任务实例，管理采集器生命周期、WebSocket 客户端、日志广播 |

**状态机：**

```
pending → running → links_collected → running(phase2) → completed
                    ↓                  ↓
                  failed             failed
                    ↓                  ↓
                  stopped            stopped
```

**阶段一执行流程：**
1. `start_task()` → `TaskRunner.run()` → `WeixinCollector.run()`
2. 采集器在线程池中运行（通过 `asyncio.to_thread` 等价方式），收集视频链接
3. 完成后状态设置为 `links_collected`，调用 `_link_records()` 将占位记录的 `task_id` 从 `-1` 更新为真实 ID

**阶段二执行流程：**
1. `start_phase2()` → 将任务 `phase` 设为 2 → `runner` 重新配置
2. `WeixinCollector.run_phase2()` 从 `video_links` 表逐条读取链接
3. 通过 ADB intent 打开 → 浏览器弹窗 → 点击"前往微信" → 完整取证（录屏/截图/OCR/ASR）

**线程安全日志**：采集器在独立线程运行，使用 `queue.Queue` 线程安全队列 + 异步 `_pump_log_queue()` 泵将日志桥接到 asyncio 上下文，再通过 WebSocket 广播到前端。

#### 3.2.3 微信采集器 (`engine/weixin_collector.py`)

封装 `weixin/core/` 目录下已验证的采集逻辑，**不重写**。

**两阶段详解：**

**阶段一 — `_run_phase1()`：**
1. 连接设备（WiFi ADB + AScript MCP）
2. 打开微信 → 进入视频号 → 搜索关键词
3. 点击首个搜索结果 → 进入视频播放页
4. 点击分享按钮 → 复制视频链接
5. 滑动至下一条视频 → 重复 3-4
6. 链接存入 `video_links` 表（初始化时 `task_id = -1`，结束后由 `_link_records()` 关联）

**阶段二 — `run_phase2()`：**
1. 从 `video_links` 表读取待处理链接（`evidence_record_id IS NULL`）
2. 通过 ADB `am start` intent 打开每条链接
3. 浏览器弹窗 → OCR 识别"前往微信"按钮 → 点击
4. 视频播放页确认（UI 树 + 截图双验证）
5. **逐条完整取证**：
   - 录屏（scrcpy `--record`，默认 240 秒/条）
   - 截图序列（播放页、博主资料卡、分享面板、引流标记页）
   - OCR 实时提取博主名、视频号 ID、标题、引流标记
   - 豆包视觉模型结构化字段提取（替代 PaddleOCR）
6. 证据落盘（JSON + HTML）→ 写入平台数据库
7. 触发 ASR 转写 → 剧本台词比对 → 计算侵权评分

**日志回调**：通过 `log_callback`（异步）和 `sync_log_callback`（线程安全）双通道，将采集日志实时推送到 `TaskRunner`，再由 WebSocket 广播到前端。

#### 3.2.4 ASR 与剧本比对 (`weixin/asr/`)

**ASR 引擎优先级**：SenseVoice → Paraformer → 讯飞云 ASR

| 引擎 | 类型 | 优势 |
|------|------|------|
| SenseVoice | 离线 (sherpa-onnx) | 多语言，精度高 |
| Paraformer | 离线 (sherpa-onnx) | 中文优化，速度快 |
| 讯飞云 ASR | 云端 WebSocket | 高精度兜底 |

**剧本比对引擎** (`script_matcher.py`)：

```
ASR 文本 → 4层分句策略 → N 个片段（6~40字）
    ↓
剧本索引（600~800句，预计算拼音）
    ↓
第1层：拼音转换（pypinyin，无声调）
    ↓
第2层：拼音窗口匹配（rapidfuzz.partial_ratio，权重 0.60）
    ↓
第3层：字符级确认（difflib.SequenceMatcher，权重 0.40）
    ↓
综合得分 = pinyin × 0.60 + char × 0.40
```

**侵权评分计算：**
```python
score = coverage × 0.35 + best_score × 0.40 + min(segments_matched / 5, 1.0) × 0.25
# ≥0.70 → 高度疑似
# ≥0.50 → 疑似
# ≥0.30 → 待观察
# <0.30 → 无
```

#### 3.2.5 证据记录写入 (`weixin_collector.py` `_save_to_platform_db()`)

每条视频取证完成后，将 `weixin EvidenceRecord` 转换为平台 `EvidenceRecord` 写入数据库：

1. **基本信息**：搜索关键词、视频标识符（SHA1）、指纹（MD5）
2. **视频信息**：博主名、视频号 ID、标题、链接、点赞/评论/分享数
3. **博主信息**：资料卡名称、账号、主体类型（企业/个人）、企业全称
4. **引流信息**：引流标记文本、目标博主名、目标企业名
5. **媒体文件路径**：录屏、音频、截图列表
6. **ASR/剧本**：转写文本、使用模型、剧本匹配详情
7. **侵权评分**：综合得分、疑似等级、判定原因

**黑名单匹配**：同时检查 `infringement_clues` 表，如果引流博主名 + 作品名匹配到黑名单记录，直接设为高度疑似（score=1.0）。

#### 3.2.6 API 路由层 (`api/`)

| 文件 | 职责 |
|------|------|
| `tasks.py` | 任务 CRUD + start/stop/retry + start_phase2 + create_from_clues + video_links |
| `evidence.py` | 证据列表（分页+多条件筛选+统计）+ 详情 |
| `reviews.py` | 单条/批量复核 + 操作日志（ReviewLog） |
| `authors.py` | 博主聚合列表 + 下钻证据 |
| `devices.py` | 设备列表 + 扫描 + 前置检查 |
| `clues.py` | 侵权线索导入 + 查询 |
| `link_pool.py` | 链接池批次管理 + 手动/线索导入 + 从批次创建任务 |
| `websocket.py` | WebSocket 实时日志推送（历史回放 + 持续推送 + 心跳） |

**查询优化**：任务列表使用相关子查询统计证据数，避免多表 JOIN 的笛卡尔积：
```sql
SELECT tasks.*,
  (SELECT COUNT(*) FROM evidence_records WHERE task_id = tasks.id) AS evidence_count
FROM tasks
WHERE tasks.phase = ?
ORDER BY tasks.created_at DESC
```

#### 3.2.7 设备管理 (`engine/device_manager.py`)

- ADB 扫描：通过 `adb devices` 发现可用设备
- AScript MCP 连接：通过 WiFi IP + 端口建立 MCP 会话
- 状态心跳：定时检查设备在线状态、微信进程、视频号页面可达性
- 前置检查：ADB 连接 → AScript 通信 → 录屏可用 → 微信已启动 → 存储空间

#### 3.2.8 证据包构建 (`engine/evidence_builder.py`)

为每条证据记录生成统一的证据包：

- **JSON 数据包**：结构化字段（视频/博主/引流/媒体/剧本/截图/复核），写入 `evidence_data/tasks/{task_id}/{video_identifier}/result_*.json`
- **HTML 预览页**：美观的只读证据报告，含录屏播放器、截图画廊、ASR 原文、剧本匹配结果

#### 3.2.9 僵尸任务恢复 (`main.py` `lifespan`)

后端重启时自动处理：
1. 数据库中 `running` 状态的任务 → 重置为 `stopped`（调度器内存状态已丢失）
2. 初始化设备管理器 + 调度器
3. 预热 AI 模型（SenseVoice/Paraformer/PaddleOCR）

---

## 4. 前端技术概述

### 4.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| **Vue 3** | ^3.5 | Composition API + `<script setup>` |
| **Vue Router** | ^4.5 | SPA 路由 |
| **Pinia** | ^2.3 | 状态管理 |
| **Element Plus** | ^2.9 | UI 组件库 |
| **Vite** | ^6.2 | 构建工具 |
| **Axios** | ^1.7 | HTTP 客户端 |

### 4.2 页面路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | 首页 | 输入剧名+选择设备，一键发起阶段一链接采集 |
| `/link-pool` | 链接池 | 批次管理：手动创建/从线索导入/选择批次启动阶段二 |
| `/tasks?phase=1` | 一阶段任务 | 仅展示链接采集任务 |
| `/tasks?phase=2` | 二阶段任务 | 仅展示视频取证任务（含视频数+证据数） |
| `/tasks/:id` | 执行监控 | WebSocket 实时日志终端 + 进度条 + 当前截图 |
| `/evidence` | 证据列表 | 卡片式证据浏览，支持按任务/审核状态/关键词/博主筛选 |
| `/evidence/:id` | 证据详情 | 完整证据包（录屏/截图/ASR/JSON） |
| `/review-pool` | 复核池 | 待复核样本逐条处理 + 批量标注 |
| `/authors` | 博主聚合 | 按博主侵权统计分析，支持展开下钻 |

### 4.3 交互设计

- **即时操作**：证据卡片内嵌快捷按钮，侵权/未侵权一键标注
- **实时反馈**：执行监控页 WebSocket 推送实时日志、进度百分比、最新截图
- **筛选联动**：证据列表支持多条件自由组合筛选，统计数据实时响应筛选条件
- **状态持久化**：最近访问任务 ID 存入 localStorage，侧边栏"执行监控"始终指向上次任务

---

## 5. 数据模型

### 5.1 模型一览

| 表 | 模型 | 说明 |
|----|------|------|
| `tasks` | `Task` | 取证任务，含二阶段状态（phase=1/2） |
| `evidence_records` | `EvidenceRecord` | 证据记录，每条视频对应一行 |
| `video_links` | `VideoLink` | 阶段一收集的视频链接暂存 |
| `link_batches` | `LinkBatch` | 链接批次（一组链接的集合） |
| `infringement_clues` | `InfringementClue` | 侵权线索黑名单（Excel 导入） |
| `review_logs` | `ReviewLog` | 复核操作审计日志 |
| `author_clusters` | `AuthorCluster` | 博主聚合统计 |
| `devices` | `Device` | 设备信息与状态 |

### 5.2 Task 关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `Integer PK` | 自增主键 |
| `keyword` | `String(200)` | 搜索剧名 |
| `status` | `String(20)` | pending→running→links_collected→completed / failed / stopped |
| `phase` | `Integer` | 1=阶段一（链接采集），2=阶段二（视频取证） |
| `collect_mode` | `String(20)` | 固定 `"link_first"`，二阶段采集模式 |
| `max_videos` | `Integer` | 最大采集数，0=全量 |
| `hold_seconds` | `Integer` | 每条视频停留秒数（默认240） |
| `enable_asr` | `Boolean` | 是否启用 ASR 台词比对 |
| `skip_search` | `Boolean` | 是否跳过搜索直接从当前视频开始 |
| `device_id` | `String(100)` | 执行设备 ADB serial |
| `error_message` | `Text` | 错误详情 |

### 5.3 EvidenceRecord 关键字段

| 分类 | 字段 | 说明 |
|------|------|------|
| **标识** | `video_identifier` (SHA1) | 稳定去重标识 |
| | `fingerprint` (MD5) | 二次去重指纹 |
| **视频** | `blogger_name`, `title`, `video_link` | 视频基础信息 |
| | `video_channel_id` | 视频号 ID |
| | `like_count`, `comment_count`, `share_count` | 互动数据 |
| **博主** | `profile_name`, `subject_type`, `company_full_name` | 博主主体信息 |
| **引流** | `has_traffic_marker`, `traffic_marker_text` | 引流标记检测 |
| | `target_blogger_name`, `target_company_name` | 引流目标追踪 |
| **媒体** | `recording_video_path`, `recording_audio_path` | 录屏/音频路径 |
| | `asr_text`, `asr_model` | ASR 转写结果 |
| **剧本** | `script_match_status`, `script_match_similarity` | 剧本匹配结果 |
| | `script_match_segments_json` | 逐句匹配细节 |
| **侵权** | `infringement_score`, `infringement_level` | 机器自动判定 |
| | `infringement_reason` | 原因（如：匹配到侵权线索） |
| **复核** | `review_status`, `reviewer`, `review_notes` | 人工审核 |
| **文件** | `screenshots_json`, `json_path`, `html_path` | 证据文件路径 |

---

## 6. API 接口

### 6.1 任务管理 (`/api/tasks`)

| 方法 | 路径 | 说明 | 关键参数 |
|------|------|------|----------|
| `GET` | `/tasks` | 任务列表 | `page`, `page_size`, `status`, `phase` |
| `POST` | `/tasks` | 创建一阶段任务 | `keyword`, `device_id`, `max_videos` |
| `GET` | `/tasks/{id}` | 任务详情 | — |
| `DELETE` | `/tasks/{id}` | 删除任务及关联 | — |
| `POST` | `/tasks/{id}/start` | 启动阶段一 | — |
| `POST` | `/tasks/{id}/stop` | 停止执行 | — |
| `POST` | `/tasks/{id}/retry` | 重试失败任务 | — |
| `POST` | `/tasks/{id}/start-phase2` | 启动阶段二 | `hold_seconds`, `enable_asr` |
| `GET` | `/tasks/{id}/video-links` | 阶段一已收集链接 | — |
| `POST` | `/tasks/create-from-clues` | 从侵权线索创建任务 | `device_id`, `max_videos` |

### 6.2 证据查询 (`/api/evidence`)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/evidence` | 证据列表（分页+筛选），含统计信息 |
| `GET` | `/evidence/{id}` | 证据详情（完整字段） |

**统计返回字段**：`total`（总数）、`infringement`（人工标注侵权）、`high`（高度疑似）、`mid`（疑似）、`low`（待观察）

### 6.3 链接池 (`/api/link-pool`)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/batches` | 批次列表（含各批次待处理/总数） |
| `POST` | `/batches` | 手动创建批次 |
| `DELETE` | `/batches/{id}` | 删除批次及未采集链接 |
| `GET` | `/batches/{id}/links` | 批次内链接明细 |
| `POST` | `/batches/{id}/add-link` | 手动添加链接 |
| `POST` | `/import-from-clues` | 从侵权线索导入链接到新批次 |
| `POST` | `/create-task` | 选择批次创建阶段二任务 |

### 6.4 其他

| 模块 | 路径前缀 | 主要接口 |
|------|----------|----------|
| 复核 | `/api/reviews` | `GET /pool`, `PUT /{id}`, `POST /batch` |
| 博主 | `/api/authors` | `GET /` (列表), `GET /{id}` (详情) |
| 设备 | `/api/devices` | `GET /` (列表), `POST /scan` |
| 线索 | `/api/clues` | `GET /` (列表), `GET /with-links` |
| WebSocket | `/ws/tasks/{id}` | 实时日志推送 + 历史回放 |
| 文件 | `/files/{path}` | 静态文件服务（截图/录屏/HTML） |

---

## 7. 核心业务流程

### 7.1 完整取证流程

```
┌─────────────────────────────────────────────────┐
│  1. 首页输入剧名 + 选择设备 → 创建任务           │
│     POST /api/tasks → phase=1, status=pending    │
├─────────────────────────────────────────────────┤
│  2. 自动启动任务 → status=running                │
│     后台 asyncio 线程执行阶段一：                │
│     打开微信 → 搜索 → 逐条复制链接               │
│     → 链接写入 video_links (task_id=-1)          │
│     → 完成: status=links_collected               │
│     → _link_records: task_id:-1 → 真实ID         │
├─────────────────────────────────────────────────┤
│  3. 用户进入链接池 / 任务详情页                  │
│     选择链接 → 配置参数（停留时长/ASR）          │
│     → POST /tasks/{id}/start-phase2              │
│     → phase=2, status=running                    │
├─────────────────────────────────────────────────┤
│  4. 后台执行阶段二：逐条完整取证                  │
│     intent 打开链接 → 录屏 → 截图序列            │
│     → OCR/视觉模型提取字段                       │
│     → 证据落盘(JSON+HTML) → 写入DB               │
│     → ASR → 剧本比对 → 侵权评分                  │
│     → 黑名单匹配 → 完成: status=completed        │
├─────────────────────────────────────────────────┤
│  5. 证据列表浏览 + 详情查看                      │
│     → 人工复核（侵权/未侵权）                    │
│     → 标记操作记录 ReviewLog                     │
├─────────────────────────────────────────────────┤
│  6. 博主聚合分析                                 │
│     → 按 video_channel_id 聚类统计               │
│     → 下钻查看某博主所有侵权视频                 │
└─────────────────────────────────────────────────┘
```

### 7.2 侵权线索导入流程

```
上传 Excel → 解析写入 infringement_clues
    → 链接池: "从线索导入" → 创建批次 (video_links)
    → 或者: POST /tasks/create-from-clues → 直接创建二阶段任务
```

### 7.3 黑名单匹配时机

采集器在每条证据写入数据库时，检查 `infringement_clues` 表：
- **匹配条件**：引流目标博主名 == 黑名单账号名 AND 引流视频名包含黑名单作品名
- **命中结果**：`infringement_level = "高度疑似"`, `infringement_score = 1.0`, `infringement_reason` 记录匹配详情

也可通过 `rematch_clues.py` 脚本对已有证据批量重新匹配。

---

## 8. 目录结构

```
platform/
├── README.md
├── 开发计划.md
├── 台词文本比对逻辑.md
│
├── backend/                              # Python 后端
│   ├── main.py                           # FastAPI 入口 + lifespan
│   ├── config.py                         # 全局配置（路径/设备/模型/API Key）
│   ├── database.py                       # SQLAlchemy async engine + session
│   ├── requirements.txt
│   ├── prewarm.py                        # 模型预热
│   ├── import_clues.py                   # Excel 导入侵权线索脚本
│   ├── rematch_clues.py                  # 重新匹配侵权线索脚本
│   │
│   ├── api/                              # REST API 路由
│   │   ├── tasks.py                      # 任务管理 + 阶段控制
│   │   ├── evidence.py                   # 证据查询 + 统计
│   │   ├── reviews.py                    # 复核管理
│   │   ├── authors.py                    # 博主聚合
│   │   ├── devices.py                    # 设备管理
│   │   ├── clues.py                      # 侵权线索
│   │   ├── link_pool.py                  # 链接池批次管理
│   │   └── websocket.py                  # WebSocket 实时日志
│   │
│   ├── models/                           # SQLAlchemy ORM 模型
│   │   └── __init__.py                   # Task/EvidenceRecord/VideoLink/LinkBatch/...
│   │
│   ├── engine/                           # 取证引擎
│   │   ├── weixin_collector.py           # 微信采集器（封装 weixin/core/）
│   │   ├── device_manager.py             # ADB/AScript MCP 设备管理
│   │   ├── task_scheduler.py             # asyncio 任务调度器
│   │   └── evidence_builder.py           # 证据包构建器 (JSON + HTML)
│   │
│   └── weixin/                           # 微信采集核心（已有模块）
│       ├── core/                         # 采集/导航/OCR/媒体/存储
│       ├── asr/                          # ASR 引擎 + 剧本比对
│       ├── db/                           # weixin 本地 MySQL 模型
│       └── utils/                        # 文本质量检查等工具
│
├── frontend/                             # Vue 3 前端
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.js                       # 入口
│       ├── App.vue                       # 根组件 + 侧边栏导航
│       ├── router/index.js               # 路由配置
│       ├── api/index.js                  # 后端 API 封装
│       ├── stores/app.js                 # Pinia 状态管理
│       ├── views/                        # 页面组件
│       │   ├── HomePage.vue              # 首页（创建一阶段任务）
│       │   ├── LinkPoolPage.vue          # 链接池（批次管理 + 启动二阶段）
│       │   ├── TaskListPage.vue          # 任务列表（一/二阶段分列展示）
│       │   ├── TaskRunPage.vue           # 执行监控（WebSocket 实时）
│       │   ├── ResultListPage.vue        # 证据列表 + 统计 + 筛选
│       │   ├── EvidenceDetailPage.vue    # 证据详情
│       │   ├── ReviewPoolPage.vue        # 复核池
│       │   └── AuthorClusterPage.vue     # 博主聚合
│       ├── components/DeviceStatus.vue   # 设备状态组件
│       ├── styles/main.css               # 全局样式
│       └── utils/time.js                 # 时间格式化工具
│
├── evidence_data/                        # 证据存储 + 数据库
│   ├── db/platform.db                    # SQLite 数据库
│   ├── tasks/{task_id}/{video_id}/       # 证据包（JSON+HTML+截图+录屏）
│   ├── screenshots/
│   ├── recordings/
│   ├── jsons/
│   ├── scripts/                          # 台词剧本
│   └── asr/                              # ASR 输出
│
├── test/                                 # 测试
├── run_backend.bat                       # Windows 后端启动
└── run_frontend.bat                      # Windows 前端启动
```

---

## 9. 部署与启动

### 9.1 手机端环境

#### 9.1.1 硬件要求

| 要求 | 说明 |
|------|------|
| Android 手机 | Android 10+，已开启"开发者选项"和"USB 调试" |
| 微信 | 已登录，微信视频号功能可正常使用 |
| 网络 | 手机和 PC 在**同一 WiFi** 下（或首次用 USB 连一次后走 WiFi） |

#### 9.1.2 开启开发者选项 & USB 调试

```
设置 → 关于手机 → 连续点击"版本号"7次 → 返回 → 开发者选项
  → 开启「USB 调试」
  → 开启「USB 调试（安全设置）」  （部分手机需要）
  → 开启「USB 安装」              （部分手机需要）
```

#### 9.1.3 安装 AScript App

AScript 是运行在手机端的 Android 自动化 App，提供 MCP 通信桥、无障碍服务、OCR 引擎和屏幕捕获能力。**手机取证的底层执行全依赖它。**

**安装步骤：**

1. 下载 AScript APK（具体版本和渠道请咨询项目管理员）
2. 安装到手机：`adb install ascript.apk` 或直接传 APK 文件到手机安装
3. 打开 AScript App，完成初始化
4. **开启无障碍服务**：设置 → 无障碍 → 已安装的服务 → AScript → 开启
5. **开启悬浮窗权限**：设置 → 应用 → AScript → 悬浮窗权限 → 允许
6. 确认 AScript App 显示"服务已启动"或类似状态指示

**AScript 关键配置：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 监听端口 | `9096` | MCP 通信端口，PC 通过 `手机IP:9096` 连接 |
| 连接模式 | LocalIP（WiFi） | 日常使用 WiFi 即可，无需插 USB 线 |
| 无障碍服务 | **必须开启** | 不开则无法执行点击、滑动、UI 树读取 |
| 录屏权限 | 首次调用弹窗 | 首次调用 `screen.capture_cv()` 时会弹出 MediaProjection 授权窗，需点击"立即开始" |
| 电池优化 | 设为"无限制" | 防止后台被杀，导致采集中断 |

**验证 AScript 是否正常：**

```
1. 手机端：AScript App 显示"服务运行中"
2. PC 端 TCP 探测：telnet 手机IP 9096 → 能连通
3. 浏览器访问后端 → 首页"前置检查" → "AScript端口可达" ✅
```

#### 9.1.4 微信准备

1. 微信号已登录（避免使用新号，可能被风控限制功能）
2. 进入"发现"→"视频号"，确认能正常刷到视频、打开播放页
3. 设置 → 应用 → 微信 → 电池 → **无限制**（防止后台被杀）

### 9.2 PC 端环境

#### 9.2.1 操作系统要求

| 系统 | 说明 |
|------|------|
| Windows 10/11 | 推荐，scrcpy + ADB 兼容性最好 |
| macOS / Linux | 理论可行，需自行适配路径和驱动 |

#### 9.2.2 基础软件

| 软件 | 最低版本 | 安装方式 | 用途 |
|------|----------|----------|------|
| **Python** | 3.11+ | [python.org](https://python.org) 或 `conda` | 后端运行 |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org) | 前端构建 |
| **scrcpy** | 3.0+ | [github.com/Genymobile/scrcpy](https://github.com/Genymobile/scrcpy/releases) | **录屏**：PC 端录制，可带音频 |
| **ffmpeg** | 任意 | `winget install ffmpeg` 或 [ffmpeg.org](https://ffmpeg.org) | **音频提取**：从录屏视频中分离音频供 ASR 使用 |

> **scrcpy 安装**：下载 `scrcpy-win64-v3.x.x.zip` 解压到固定目录（如 `C:\scrcpy-win64-v3.3.3`），在 `backend/config.py` 中配置 `SCRCPY_DIR`。scrcpy 自带的 `adb.exe` 会被平台自动使用。

#### 9.2.3 Python 依赖

```bash
cd platform/backend
pip install -r requirements.txt
```

**核心依赖说明：**

| 包 | 用途 |
|----|------|
| `fastapi` + `uvicorn` | Web 框架 + ASGI 服务器 |
| `sqlalchemy` + `aiosqlite` | 异步 ORM + SQLite 驱动 |
| `websockets` | WebSocket 实时日志推送 |
| `Pillow` | 图像处理（视觉模型图片预处理） |
| `httpx` | 异步 HTTP 客户端 |
| `loguru` | 结构化日志 |
| `python-multipart` + `aiofiles` | 文件上传 + 异步文件操作 |

> **采集层额外依赖**（按需安装，不在 `requirements.txt`）：`pypinyin`、`rapidfuzz`、`opencv-python`、`paddleocr`、`sherpa-onnx`、`numpy` 等，由 `weixin/core/` 内部管理。

#### 9.2.4 前端依赖

```bash
cd platform/frontend
npm install
```

| 包 | 用途 |
|----|------|
| `vue` + `vue-router` + `pinia` | 前端框架 + 路由 + 状态管理 |
| `element-plus` + `@element-plus/icons-vue` | UI 组件库 + 图标 |
| `axios` | HTTP 客户端 |
| `vite` + `@vitejs/plugin-vue` | 构建工具 |

#### 9.2.5 AScript MCP 通信包（PC 端）

PC 端需要安装 AScript 对应的 MCP Python 包，用于与手机端 AScript App 通过 MCP 协议通信：

```bash
pip install ascript-mcp
# 具体包名以 AScript 官方文档为准
```

> 安装后可通过 `python -m ascript_mcp.local` 验证 —— 会启动 MCP Server，通过 WiFi (手机IP:9096) 与手机端 AScript App 建立连接。

#### 9.2.6 ADB 连接手机

**方式一：USB（推荐首次设置）**

```bash
# 手机用 USB 数据线连接 PC
adb devices
# 应输出：xxxxxxxx    device
```

**方式二：WiFi（日常使用，不需要插线）**

```bash
# 1. 先 USB 连一次，开启 TCP 调试
adb tcpip 5555

# 2. 查看手机 WiFi IP（手机：设置 → WLAN → 当前网络 → IP地址）
# 或通过 adb 获取：
adb shell ip addr show wlan0

# 3. WiFi 连接（不需要 USB 了）
adb connect 192.168.x.x:5555

# 4. 验证
adb devices
# 应输出：192.168.x.x:5555    device
```

> **注意**：手机重启后 TCP 调试端口会关闭，需要重新 USB 连接一次执行 `adb tcpip 5555`。部分手机支持在开发者选项中直接开启"网络 ADB 调试"来永久生效。

#### 9.2.7 ASR 离线语音模型（可选）

ASR 台词比对功能需要离线语音识别模型。不配置时证据采集不受影响，仅缺少台词文本和剧本比对结果。

| 模型 | 路径配置 | 优势 |
|------|----------|------|
| **SenseVoice** | `SENSEVOICE_MODEL_DIR` | 首选，多语言高精度 |
| **Paraformer** | `PARAFORMER_MODEL_DIR` | 中文优化，速度快 |

下载：[sherpa-onnx releases](https://github.com/k2-fsa/sherpa-onnx/releases)

```bash
# 模型目录结构示例
D:\models\sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\
├── model.onnx
├── tokens.txt
└── ...
```

#### 9.2.8 豆包视觉模型（可选）

用于替代 PaddleOCR 提取博主资料卡、引流标记等结构化字段。不开则自动退回到 PaddleOCR。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `ARK_API_KEY` | 火山引擎 API Key | 内置测试 Key |
| `ARK_MODEL` | 模型 ID | `doubao-seed-2-0-mini-260428` |
| `ARK_VISION_ENABLED` | `0` 关闭回退到 PaddleOCR | `1` |

> API Key 在 [console.volcengine.com/ark](https://console.volcengine.com/ark) 申请。

### 9.3 启动与验证

#### 9.3.1 启动

```bash
# 终端 1：后端
cd platform/backend
pip install -r requirements.txt
python main.py
# 或双击 run_backend.bat

# 终端 2：前端
cd platform/frontend
npm install
npm run dev
# 或双击 run_frontend.bat
```

后端运行在 `http://localhost:8000`，前端运行在 `http://localhost:5173`。

#### 9.3.2 验证步骤

按以下顺序逐项验证：

```
1️⃣ 后端基础验证
   → 访问 http://localhost:8000/api/health → {"status":"ok"}

2️⃣ 前端基础验证
   → 访问 http://localhost:5173 → 看到"取证工作台"首页

3️⃣ 设备连接验证
   → 首页左侧底部应显示手机型号和 IP（✅在线）
   → 如果没有：点击设备面板的"重新扫描"按钮

4️⃣ 前置检查验证
   → 点击"前置检查"按钮
   → ADB连接 ✅  |  微信视频号前台 ✅  |  屏幕点亮 ✅
   → 存储空间 ✅  |  scrcpy可用 ✅     |  AScript端口可达 ✅

5️⃣ AScript 录屏授权验证（单独按钮，约5-15秒）
   → 点击"AScript录屏授权检查"
   → 手机弹出"要开始使用AScript录屏吗？" → 点击"立即开始"
   → 前端显示 录屏授权检查通过 ✅

6️⃣ 功能验证
   → 输入剧名 → 选择设备 → 点击"开始收集链接"
   → 跳转执行监控页 → 实时日志开始输出 → 手机开始自动操作微信
```

### 9.4 配置文件参考

所有配置集中管理在 `backend/config.py`，支持环境变量覆盖。

**核心配置：**

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `PLATFORM_DATABASE_URL` | 数据库连接 | SQLite `platform.db` |
| `PLATFORM_DEVICE_IP` | 默认设备 IP（留空自动扫描） | — |
| `PLATFORM_PHONE_PORT` | AScript App 监听端口 | `9096` |
| `PLATFORM_MAX_VIDEOS` | 默认采集视频数 | `5` |
| `PLATFORM_HOLD_SECONDS` | 每条视频停留秒数 | `240` |
| `PLATFORM_HOST` / `PLATFORM_PORT` | 服务地址 | `0.0.0.0:8000` |

**外部工具路径：**

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `PLATFORM_SCRCPY_DIR` | scrcpy 目录 | `C:\scrcpy-win64-v3.3.3` |
| `PLATFORM_FFMPEG_PATH` | ffmpeg 路径 | 系统 PATH |
| `PLATFORM_FFPROBE_PATH` | ffprobe 路径 | 系统 PATH |

**ASR 模型路径：**

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SENSEVOICE_MODEL_DIR` | SenseVoice 模型目录 | — |
| `PLATFORM_SENSEVOICE_MODEL_SEARCH_PATHS` | 搜索路径 | 硬编码路径，建议设为环境变量 |
| `PARAFORMER_MODEL_DIR` | Paraformer 模型目录 | — |
| `PLATFORM_PARAFORMER_MODEL_SEARCH_PATHS` | 搜索路径 | 同上 |

**云服务 API：**

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `ARK_API_KEY` | 豆包视觉模型 Key | 内置测试 Key |
| `ARK_MODEL` | 视觉模型 ID | `doubao-seed-2-0-mini-260428` |
| `ARK_VISION_ENABLED` | 是否启用（`0` 关闭） | `1` |
| `XUNFEI_APPID` | 讯飞 ASR AppID | — |
| `XUNFEI_APIKEY` | 讯飞 ASR API Key | — |
| `XUNFEI_APISECRET` | 讯飞 ASR API Secret | — |

---

## 附：侵权评分算法

```
综合得分 = coverage × 0.35 + best_similarity × 0.40 + min(matched_segments/5, 1.0) × 0.25

其中：
  coverage         — ASR 片段匹配率（matched / total）
  best_similarity  — 拼音×0.55 + 字符×0.45（最佳匹配句）
  matched_segments — 匹配到的片段数（封顶5）

分级：
  ≥0.70 → 高度疑似
  ≥0.50 → 疑似
  ≥0.30 → 待观察
  <0.30 → 无

黑名单匹配 → 直接 高度疑似（score=1.0）
```

> 详细剧本比对算法见 [台词文本比对逻辑.md](./台词文本比对逻辑.md)  
> ADB 与 AScript 技术对比见 [ADBvsAScript.md](./ADBvsAScript.md)
