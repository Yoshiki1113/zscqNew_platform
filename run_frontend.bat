@echo off
chcp 65001 >nul
cd /d "%~dp0\frontend"

echo ================================================
echo   嘉剧荟 - 短剧侵权识别平台 - 前端服务
echo ================================================
echo.

if not exist "node_modules\" (
    echo [1/2] 首次运行，安装前端依赖...
    npm install
) else (
    echo [1/2] 依赖已安装，跳过。
)

echo.
echo [2/2] 启动 Vite 开发服务器...
echo   地址: http://localhost:5173
echo.
npm run dev

pause
