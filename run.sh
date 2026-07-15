#!/bin/bash
# ──────────────────────────────────────────────
# 嘉剧荟 - 短剧侵权识别平台 启动脚本（Linux/macOS）
# ──────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  嘉剧荟 - 短剧侵权识别平台"
echo "============================================"
echo ""

# ── 1. Python 虚拟环境 ──
echo "[1/4] 初始化 Python 虚拟环境..."
if [ ! -d "backend/venv" ]; then
    python3 -m venv backend/venv
fi
source backend/venv/bin/activate
echo "  当前 Python: $(python3 --version)"
echo ""

# ── 2. 后端依赖 ──
echo "[2/4] 安装后端依赖..."
pip install -q -r backend/requirements.txt
pip install -q ascript-mcp
echo ""

# ── 3. 前端依赖 + 构建 ──
echo "[3/4] 安装前端依赖并构建..."
if [ ! -d "frontend/node_modules" ]; then
    echo "  首次运行，安装 npm 依赖..."
    cd frontend && npm install && cd ..
fi
cd frontend && npm run build && cd ..
echo "  前端构建完成 -> frontend/dist/"
echo ""

# ── 4. 启动服务 ──
echo "[4/4] 启动服务..."
echo ""
echo "  地址: http://localhost:8000"
echo "  API文档: http://localhost:8000/docs"
echo "  前端页面: http://localhost:8000"
echo ""
echo "  ── 启动后自动预热 ──"
echo "  1. 初始化数据库 & 检查僵尸任务..."
echo "  2. PaddleOCR 模型加载（首次约 20-60 秒，后续约 5-10 秒）..."
echo "  3. OCR Worker 子进程启动 & 预热..."
echo "  4. 豆包视觉 API 连通性检查..."
echo "  5. 讯飞云 ASR 配置检查..."
echo "  6. 剧本台词数据检查..."
echo ""
echo "  等待控制台输出 '[init] ✅ 全部就绪' 后即可正常使用"
echo "============================================"
echo ""
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .
