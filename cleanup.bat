@echo off
setlocal EnableExtensions
cd /d "%~dp0backend" || (
  echo [ERROR] cannot cd to backend
  pause
  exit /b 1
)

echo ================================================
echo   zscq platform - cleanup
echo ================================================
echo.

set "PY="
if exist "%USERPROFILE%\anaconda3\envs\zscq\python.exe" set "PY=%USERPROFILE%\anaconda3\envs\zscq\python.exe"
if exist "%USERPROFILE%\miniconda3\envs\zscq\python.exe" set "PY=%USERPROFILE%\miniconda3\envs\zscq\python.exe"
if exist "C:\Users\sp\anaconda3\envs\zscq\python.exe" set "PY=C:\Users\sp\anaconda3\envs\zscq\python.exe"
if not defined PY set "PY=python"

"%PY%" cleanup.py
pause
exit /b 0
