@echo off
setlocal EnableExtensions
cd /d "%~dp0backend" || (
  echo [ERROR] cannot cd to backend
  pause
  exit /b 1
)

echo ================================================
echo   zscq platform - backend
echo ================================================
echo.

call :resolve_python
if errorlevel 1 (
  echo [ERROR] zscq python not found. Run: conda activate zscq
  pause
  exit /b 1
)

echo [1/3] Python: %PY%
"%PY%" --version
echo.

echo [2/3] Installing requirements...
"%PY%" -m pip install -r requirements.txt -q
echo.

echo [3/3] Starting FastAPI on http://localhost:8000
echo   Docs: http://localhost:8000/docs
echo.
"%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .
pause
exit /b 0

:resolve_python
set "PY="
if exist "%USERPROFILE%\anaconda3\envs\zscq\python.exe" set "PY=%USERPROFILE%\anaconda3\envs\zscq\python.exe"
if exist "%USERPROFILE%\miniconda3\envs\zscq\python.exe" set "PY=%USERPROFILE%\miniconda3\envs\zscq\python.exe"
if exist "C:\Users\sp\anaconda3\envs\zscq\python.exe" set "PY=C:\Users\sp\anaconda3\envs\zscq\python.exe"
if defined PY exit /b 0
where python >nul 2>&1
if errorlevel 1 exit /b 1
for /f "delims=" %%i in ('where python') do (
  set "PY=%%i"
  exit /b 0
)
exit /b 1
