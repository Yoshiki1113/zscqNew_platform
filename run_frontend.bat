@echo off
setlocal EnableExtensions
cd /d "%~dp0frontend" || (
  echo [ERROR] cannot cd to frontend
  pause
  exit /b 1
)

echo ================================================
echo   zscq platform - frontend
echo ================================================
echo.

if not exist "package.json" (
  echo [ERROR] package.json not found in frontend
  pause
  exit /b 1
)

if not exist "node_modules\" (
  echo [1/2] First run: npm install...
  call npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed
    pause
    exit /b 1
  )
) else (
  echo [1/2] node_modules exists, skip install.
)

echo.
echo [2/2] Starting Vite on http://localhost:5173
echo.
call npm run dev
pause
exit /b 0
