@echo off
chcp 65001 >nul
cd /d "%~dp0\backend"

echo ================================================
echo   嘉剧荟 - 短剧侵权识别平台 - 后端服务
echo ================================================
echo.

echo [1/4] 激活 conda 环境 zscq...
call conda activate zscq
if %errorlevel% neq 0 (
    echo [错误] 无法激活 conda 环境 zscq，请确认环境已创建！
    pause
    exit /b 1
)
echo   当前 Python:
python --version
echo.

echo [2/4] 安装 Python 依赖...
pip install -r requirements.txt -q

echo.
echo [3/4] 启动 FastAPI 服务...
echo   地址: http://localhost:8000
echo   API文档: http://localhost:8000/docs
echo.
echo [4/4] 等待模型预热、环境就绪...
echo.
REM --reload-dir . 只监控 backend 源码，不监控 evidence_data/ 文件产出
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .

pause
