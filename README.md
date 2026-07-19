# 嘉剧荟 — 短剧侵权识别平台

> 微信视频号知识产权侵权证据采集、ASR 台词比对、多角色复核与推送平台

一期多角色范围见 [`docs/多角色前端一期冻结.md`](docs/多角色前端一期冻结.md)。

---

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 系统架构](#2-系统架构)
- [3. 技术栈](#3-技术栈)
- [4. 多角色与主流程](#4-多角色与主流程)
- [5. 核心业务流程详解](#5-核心业务流程详解)
- [6. 数据与存储](#6-数据与存储)
- [7. API 一览](#7-api-一览)
- [8. 目录结构](#8-目录结构)
- [9. 部署与启动](#9-部署与启动)
- [10. 关键配置](#10-关键配置)
- [11. 运维注意](#11-运维注意)

---

## 1. 项目概述

### 1.1 背景

短剧侵权方常通过微信视频号发布盗版切片并引流。本平台将手机自动化取证封装为 Web 服务，覆盖：**工单 → 搜链/挂链 → 录屏取证 → ASR 与剧本比对 → 公司复核 → 推送公安**。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **多角色前端** | 公安 / 公司 / 取证（一期角色切换，无真实登录） |
| **工单包导入** | Excel 剧名 + 台词 doc/docx；认领后异步 LLM 清洗入库 |
| **二阶段采集** | 一阶段搜链入库；二阶段 intent 打开 → 前往微信 → 录屏/截图/引流/ASR |
| **断点续采** | 同任务跳过已入库链接；续采前清理未引用的半截媒体 |
| **ASR / 台词比对** | 讯飞转写 + 拼音/字符剧本匹配；支持一键补转写、一键补比对 |
| **引流取证** | 颜色/OCR 定位「免费剧集」类标记，采集目标账号与企业信息 |
| **线索黑名单** | 引流博主 + 作品名匹配导入线索，命中拉高侵权分 |
| **推送链路** | 取证 → 公司核查池 → 公司标「侵权」→ 取证推公安 |
| **实时监控** | WebSocket 推送任务日志与进度 |

### 1.3 设计原则

- **复用 `weixin/core`**：`WeixinCollector` 为薄封装，采集逻辑集中在已验证模块
- **台词与采集解耦**：二阶段可不挡「台词未就绪」；脚本 ready 后可用一键比对补齐
- **扩展预留**：帮我取证 UI 预留多平台，一期仅微信视频号

---

## 2. 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│  前端 Vue3 + Element Plus（角色：police / company / collector） │
│  工单 │ 调度台 │ 链接池 │ 任务监控 │ 证据 │ 核查池 │ 公安驾驶舱  │
└────────────────────────────┬─────────────────────────────────┘
                             │  REST / WebSocket /files
┌────────────────────────────┴─────────────────────────────────┐
│  FastAPI + asyncio                                           │
│  api/  工单·任务·链接池·证据·复核·设备·线索·驾驶舱               │
│  engine/  TaskScheduler · WeixinCollector · DeviceManager    │
│           script_clean_jobs · script_rematch · orphan_cleanup│
│  weixin/core  导航·OCR·录屏·取证·存证                          │
│  weixin/asr   讯飞 ASR · 剧本匹配 · LLM 台词清洗               │
└────────────────────────────┬─────────────────────────────────┘
                             │
              MySQL  │  evidence_data/  │  手机 ADB+AScript+scrcpy
```

---

## 3. 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3、Vue Router、Pinia、Element Plus、Vite、Axios |
| 后端 | Python 3.11+、FastAPI、Uvicorn、SQLAlchemy 2.0 async |
| 数据库 | MySQL 8（`aiomysql`，见 `PLATFORM_DATABASE_URL`） |
| 手机控制 | ADB、AScript MCP（默认端口 9096）、scrcpy、ffmpeg |
| OCR / 视觉 | PaddleOCR 子进程；豆包 Ark 视觉（可关 `ARK_VISION_ENABLED`） |
| ASR | 讯飞云 IAT v2（主路径）；可选 SenseVoice 预热 |
| 剧本匹配 | pypinyin + rapidfuzz；LLM 清洗见 `script_cleaner.py` |

---

## 4. 多角色与主流程

一期鉴权为 **角色切换器（localStorage）**，不做真实登录。

| 角色 | 入口 | 主要职责 |
|------|------|----------|
| **公司** `company` | `/company` | 上传工单包、帮我取证、核查池复核（侵权/未侵权） |
| **取证** `collector` | `/collector` | 认领工单、一阶段搜链、二阶段取证、推送公司/公安 |
| **公安** `police` | `/police` | 驾驶舱、已推送线索、只读证据 |
| 版权 / 文旅 | 占位 | 一期不做 |

### 主链路（冻结）

```
公司提交工单包
    →（可选：帮我取证挂链接  或  取证端一阶段搜链）
    → 二阶段取证（录屏/ASR/比对）
    → 取证「一键推送公司复核」
    → 公司在核查池标注侵权/未侵权
    → 取证将「公司标侵权」证据推送公安
```

调度全人工，无自动派单；公安不派单。

---

## 5. 核心业务流程详解

### 5.1 工单与台词库

1. **导入工单包** `POST /api/work-orders/import-package`  
   - zip：`剧名列表.xlsx` + 每剧一个同名 `doc/docx`  
   - 每剧一条工单，`status=submitted`  
   - 台词状态：`none` / `pending` / `ready`（内容哈希命中缓存可直接 ready）

2. **帮我取证** `POST /api/work-orders/help-collect`  
   - Excel：剧名 + 侵权视频链接；写入链接池批次 `WO-{工单号}`

3. **认领触发清洗** `POST /api/work-orders/{id}/assign`  
   - 异步 `script_clean_jobs`：LLM 清洗 → `evidence_data/scripts/{剧名}/_script_raw.txt`  
   - 状态：`pending` → `cleaning` → `ready` | `failed`

4. **比对用台词路径**（`script_matcher._resolve_script_path`）  
   - 优先 `SCRIPTS_DIR/{keyword}/_script_raw.txt`  
   - 其次 `{keyword}.txt` 或目录内任意 txt  
   - 找不到 → `script_unavailable`（不瞎用默认剧本）

### 5.2 一阶段：搜链

- 取证端认领后启动一阶段任务（按剧名搜微信视频号）
- 链接写入 `video_links`，工单批次名 `WO-{工单号}`
- 任务状态：`pending` → `running` → `links_collected`
- 触底后会 ADB 返回桌面若干次，便于下一条任务

### 5.3 二阶段：逐链接取证

入口：`POST /api/tasks/{id}/start-phase2`，或链接池 `POST /api/link-pool/create-task`。

对每条 `evidence_record_id IS NULL` 的链接：

| 步骤 | 行为 |
|------|------|
| 1 | ADB intent 打开分享链接 |
| 2 | 等待弹窗（默认 8s）→ **固定坐标**点「前往微信」（可配 `GOTO_WEIXIN_*`） |
| 3 | 等待进播放页（默认 5s） |
| 4 | 开始 scrcpy 录屏 → 完整取证（博主/截图/分享等） |
| 5 | 引流：HSV 找橙/黄播放标，失败则区域 OCR；点击后采落地页 |
| 6 | **停留 `hold_seconds`（默认 240s）** → 停录屏 → 可选引流时段音频置零 |
| 7 | 启用 ASR 时：抽 wav → 讯飞转写 → 剧本比对 → 侵权分 |
| 8 | 入库 `EvidenceRecord`；线索黑名单可拉高分数 |
| 9 | `go_home` 后 **再等 5s** 再处理下一条 |

**说明：** 创建二阶段任务不再强制台词 ready；无台词时 ASR 仍可跑，比对为 `script_unavailable`，之后用一键比对补齐。

### 5.4 断点续采与孤儿媒体

- **续采条件**：任务 `stopped`/`failed` 且 `phase==2`，仍有未采链接；请求体 `resume: true`
- **续采前**：`orphan_media_cleanup.cleanup_task_orphan_media`  
  - 保留本任务已挂 `evidence_records` 引用的文件  
  - 删除未引用且 `mtime >= started_at` 的截图/录屏/json/asr  
- **单条失败/停止**：按 slug 清半截截图与录屏（`cleanup_slug_media`）
- **不**做「整任务证据全删重来」

### 5.5 一键 ASR / 一键台词比对

证据列表（取证端）：

| 按钮 | API | 行为 |
|------|-----|------|
| **一键ASR转写** | `POST /api/evidence/batch-asr` | `asr_text` 空且有媒体 → 只转写，**不比对** |
| **一键台词比对** | `POST /api/evidence/rematch-scripts` | 按剧名加载台词库；无 ASR 先转写再比对；有 ASR 直接比对 |

筛选与列表一致：可选 `work_order_id` / `task_id` / `keyword`。前端超时约 30 分钟。

实现模块：`backend/engine/script_rematch.py`。

### 5.6 复核与推送

| 动作 | 规则 |
|------|------|
| 推送公司 | 二阶段证据；`push-company` / `push-company-all` |
| 公司复核 | 核查池标注 `侵权` / `未侵权` |
| 推送公安 | 须已推公司且公司复核为「侵权」 |
| 公安侧 | 驾驶舱统计 + 已推送线索只读 |

### 5.7 引流与「前往微信」实现要点（现状）

| 点击 | 现状 | 风险 |
|------|------|------|
| 前往微信 | 固定坐标 + 分辨率缩放 | 弹窗未出/浏览器差异易点偏 |
| 引流标记 | 主：颜色找橙/黄小图标；备：固定区 OCR「免费剧集/全N集」 | 仅文案无图标、字幕黄块易误检 |

豆包定位按钮/标记的代码仍保留但已标废弃，运行时不以豆包点这两处。

---

## 6. 数据与存储

### 6.1 数据库（MySQL）

主要表（见 `backend/models/__init__.py`）：

- `tasks` — 采集任务（phase、hold_seconds、enable_asr、工单关联等）
- `video_links` — 一阶段/导入链接；`evidence_record_id` 表示是否已采
- `evidence_records` — 证据字段、ASR、剧本比对、推送与复核状态
- `work_orders` — 工单与 `script_status` / 清洗时间 / 错误
- `link_batches` — 链接批次（含 `WO-*`）
- 复核、线索、设备等相关表

启动时 `database.py` 会做增量列迁移；重启会把残留 `running` 任务置为 `stopped`。

### 6.2 文件目录 `evidence_data/`

根路径：`PLATFORM_EVIDENCE_DATA_DIR`（默认项目下 `evidence_data/`）。

| 子目录 | 内容 |
|--------|------|
| `screenshots/` | 播放页/资料卡/引流等截图 |
| `recordings/` | scrcpy 视频与抽音 wav |
| `jsons/` | JSON + HTML 证据包 |
| `asr/` | `.asr.txt` / `.asr.json` |
| `scripts/{剧名}/` | `_script_raw.txt`、`_source.*`、`_meta.json` |
| `work_orders/` | 工单包上传与附件 |
| `tasks/` | 按任务组织的包（若使用） |
| `temp/` | 临时文件 |

媒体在库中多为相对 `evidence_data` 的路径；补 ASR 时会再 resolve 绝对路径。

---

## 7. API 一览

前缀 `/api`（OpenAPI：`http://localhost:8000/docs`）。WebSocket：`/ws/tasks/{id}`。静态媒体：`/files/...`。

| 模块 | 重要接口 |
|------|----------|
| 工单 | `import-package`、`help-collect`、`assign`、附件与链接导入 |
| 任务 | CRUD、`start`/`stop`/`retry`、**`start-phase2`（含 resume）**、video-links |
| 链接池 | batches、import-from-clues、**`create-task`** |
| 证据 | list/detail、**`batch-asr`**、**`rematch-scripts`**、push-company、push |
| 复核 | pool、单条/批量标注 |
| 设备 | 扫描、预检、AScript |
| 线索 | 黑名单导入 |
| 驾驶舱 | `GET /dashboard/police` |
| 健康 | `GET /api/health` |

---

## 8. 目录结构

```
zscqNew_platform/
├── README.md
├── .env                          # 本地环境（勿提交密钥）
├── run.bat / run_backend.bat / run_frontend.bat / run.sh
├── backend/
│   ├── main.py                   # FastAPI 入口、生命周期、静态托管
│   ├── config.py                 # 路径与默认参数
│   ├── database.py               # 异步引擎与迁移
│   ├── models/                   # ORM
│   ├── api/                      # REST 路由
│   ├── engine/
│   │   ├── task_scheduler.py     # 任务调度、清理延迟
│   │   ├── weixin_collector.py   # 一/二阶段封装
│   │   ├── device_manager.py
│   │   ├── script_clean_jobs.py  # 台词异步清洗
│   │   ├── script_rematch.py     # 一键 ASR / 补比对
│   │   └── orphan_media_cleanup.py
│   └── weixin/
│       ├── core/                 # 采集、OCR、录屏、存证
│       └── asr/                  # 讯飞、匹配、清洗
├── frontend/src/
│   ├── views/company|collector|police/
│   ├── api/index.js
│   └── stores/auth.js            # 角色切换
├── evidence_data/                # 运行时数据（体积大，一般不入库）
├── docs/                         # 冻结文档、样例
└── scripts/                      # 种子数据与测试脚本
```

---

## 9. 部署与启动

### 9.1 依赖

- Python 3.11+（推荐 conda 环境 `zscq`）
- Node.js（前端开发）
- MySQL 8，库名如 `zscq`
- 本机：ADB、scrcpy、ffmpeg；手机：AScript（MCP 端口默认 9096）、微信
- 可选：讯飞 ASR 密钥、火山引擎 Ark（视觉 + 台词清洗）

### 9.2 环境变量

项目根或 `backend/` 下 `.env`（已有环境变量优先，不覆盖）。至少配置：

```env
PLATFORM_DATABASE_URL=mysql+aiomysql://user:pass@127.0.0.1:3306/zscq
PLATFORM_SCRCPY_DIR=D:\path\to\scrcpy
PLATFORM_DEVICE_IP=192.168.x.x
# 可选：PLATFORM_DEVICE_SERIAL、XUNFEI_*、ARK_API_KEY 等
```

完整键见 [`backend/config.py`](backend/config.py)。

### 9.3 启动方式

| 方式 | 说明 |
|------|------|
| `run_backend.bat` | 后端 `http://0.0.0.0:8000` |
| `run_frontend.bat` | 前端 Vite `http://localhost:5173`（代理 `/api` `/ws` `/files`） |
| `run.bat` / `run.sh` | 构建前端并由后端同端口托管 |

健康检查：`GET http://localhost:8000/api/health` → `{"status":"ok"}`。

演示工单：

```bat
python scripts\seed_demo_work_order.py
```

---

## 10. 关键配置

| 变量 | 默认 | 含义 |
|------|------|------|
| `PLATFORM_HOLD_SECONDS` | 240 | 每条视频取证后停留秒数（录屏时长主体） |
| `PLATFORM_MAX_VIDEOS` | 5 | 一阶段默认最大条数 |
| `PLATFORM_TASK_CLEANUP_DELAY` | 300 | 任务结束后保留 runner/日志秒数（便于回放）；结束后立即可续采 |
| `PLATFORM_INTENT_POPUP_WAIT` | 8 | intent 后等浏览器弹窗 |
| `PLATFORM_INTENT_WECHAT_WAIT` | 5 | 点「前往微信」后等进微信 |
| `PLATFORM_GOTO_WEIXIN_FALLBACK_X/Y` | 754 / 1361 | 前往微信点击坐标（1080×2400 基准） |
| `PLATFORM_OCR_WORKER_TIMEOUT_SECONDS` | 120 | OCR 子进程超时 |
| `ARK_VISION_ENABLED` | 1 | 豆包视觉字段提取开关 |
| `PLATFORM_XUNFEI_MAX_AUDIO_SECONDS` | 60 | 讯飞单段上限（内部切块） |

采集器还会设置：`WEIXIN_REALTIME_TRAFFIC_OCR=1`、`WEIXIN_POST_EVIDENCE_HOLD_SECONDS` 等。

---

## 11. 运维注意

1. **后端重启**：内存中的运行任务丢失；启动时把 DB 中 `running` 纠为 `stopped`，可用断点续采。
2. **无线 ADB**：延迟与抖动大于 USB，固定坐标点击更易失败。
3. **批量 ASR/比对**：耗时长，勿在高峰重复狂点；前端超时已放宽到约 30 分钟。
4. **孤儿清理**：仅续采/单条失败路径清理未入库文件，勿手删已入库证据目录。
5. **密钥**：勿把 `.env`、讯飞/Ark Key 提交进仓库。
6. **二期未做**：真实鉴权、工单自动完结、抖音等平台采集、版权/文旅业务页。

---

## 附录：证据评分（简要）

剧本匹配成功后，`script_rematch.compute_infringement_from_script_match` 综合 coverage、拼音/字符分、命中段数得到 `infringement_score`，映射为：高度疑似 / 疑似 / 待观察 / 无。若入库时已匹配侵权线索黑名单，补比对不覆盖该理由。
