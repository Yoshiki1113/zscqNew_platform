@echo off
setlocal EnableExtensions
cd /d "%~dp0" || (
  echo [ERROR] cannot cd to project root
  pause
  exit /b 1
)

echo ================================================
echo   zscq platform - build frontend + start backend
echo ================================================
echo.

call :resolve_python
if errorlevel 1 (
  echo [ERROR] zscq python not found. Run: conda activate zscq
  pause
  exit /b 1
)

echo [1/4] Python: %PY%
"%PY%" --version
echo.

echo [2/4] Installing backend requirements...
pushd backend
"%PY%" -m pip install -r requirements.txt -q
popd
echo.

echo [3/4] Building frontend...
pushd frontend
if not exist "node_modules\" call npm install
call npm run build
if errorlevel 1 (
  echo [ERROR] frontend build failed
  popd
  pause
  exit /b 1
)
popd
echo   frontend build OK -^> frontend\dist\
echo.

echo [4/4] Starting FastAPI on http://localhost:8000
echo   API docs: http://localhost:8000/docs
echo   Frontend: http://localhost:8000  (served by FastAPI after build)
echo.
pushd backend
"%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir .
popd
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
