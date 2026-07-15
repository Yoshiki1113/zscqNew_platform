@echo off
chcp 65001 >nul
cd /d "%~dp0\backend"

echo.
echo ================================================
echo   嘉剧荟 - 短剧侵权识别平台 - 一键清理
echo ================================================
echo.

call conda activate zscq
if %errorlevel% neq 0 (
    echo [错误] 无法激活 conda 环境 zscq
    pause
    exit /b 1
)

python cleanup.py
