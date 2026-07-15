@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo   嘉剧荟 - 短剧侵权识别平台
echo ================================================
echo.

echo [1/5] 激活 conda 环境 zscq...
call conda activate zscq
if %errorlevel% neq 0 (
    echo [错误] 无法激活 conda 环境 zscq，请确认环境已创建！
    pause
    exit /b 1
)
echo   当前 Python:
python --version
echo.

echo [2/5] 安装后端依赖...
cd backend
pip install -r requirements.txt -q
cd ..
echo.

echo [3/5] 安装前端依赖...
cd frontend
if not exist "node_modules\" (
    echo   首次运行，安装 npm 依赖...
    call npm install
)
echo.

echo [4/5] 构建前端...
call npm run build
cd ..
echo   前端构建完成 -^> frontend\dist\
echo.

echo [5/5] 启动服务...
echo.
echo   地址: http://localhost:8000
echo   API文档: http://localhost:8000/docs
echo   前端页面: http://localhost:8000
echo.
echo   ── 启动后自动预热 ──
echo   1. 初始化数据库 & 检查僵尸任务...
echo   2. PaddleOCR 模型加载（首次约 20-60 秒，后续约 5-10 秒）...
echo   3. OCR Worker 子进程启动 & 预热...
echo   4. 豆包视觉 API 连通性检查...
echo   5. 讯飞云 ASR 配置检查...
echo   6. 剧本台词数据检查...
echo.
echo   等待控制台输出 "[init] ✅ 全部就绪" 后即可正常使用
echo ================================================
echo.
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .
pause
