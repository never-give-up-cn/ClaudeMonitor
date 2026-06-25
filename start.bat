@echo off
chcp 65001 >nul

set MODE=%~1
if "%MODE%"=="" set MODE=both

cd /d "%~dp0"

:: find real python path (resolve App Execution Alias)
set PY_CMD=python
for /f "delims=" %%i in ('where python3 2^>nul') do set PY_CMD=%%i
if "%PY_CMD%"=="" for /f "delims=" %%i in ('where python 2^>nul') do set PY_CMD=%%i
if "%PY_CMD%"=="" (
    echo [ERROR] Python not found. Install Python 3.7+
    pause
    exit /b 1
)

echo [INFO] Using Python: %PY_CMD%

:: install deps
%PY_CMD% -c "import serial, psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing dependencies...
    "%PY_CMD%" -m pip install pyserial psutil -q
)

:: ===== Console only =====
if /i "%MODE%"=="console" (
    title Claude Monitor - Console
    echo ========================================
    echo   Claude Code Monitor (Console)
    echo ========================================
    echo.
    "%PY_CMD%" monitor.py
    pause
    goto :eof
)

:: ===== GUI only =====
if /i "%MODE%"=="gui" (
    title Claude Monitor - Desktop
    echo ========================================
    echo   Claude Code Monitor (Desktop)
    echo ========================================
    echo.
    start "Claude GUI" "%PY_CMD%" gui.py
    goto :eof
)

:: ===== Both (default) =====
title Claude Code Monitor
echo ========================================
echo   Claude Code Monitor
echo ========================================
echo.

:: Launch GUI in a new window (uses real python path, no encoding issues)
echo [INFO] Starting GUI window...
start "Claude GUI" "%PY_CMD%" gui.py

:: Wait for GUI to initialize
timeout /t 3 /nobreak >nul

:: Launch console monitor in foreground
echo [INFO] Starting console monitor...
echo -------------------------------------------------
echo  GUI + Console both running
echo  Close this window = stop console monitor
echo -------------------------------------------------
echo.
"%PY_CMD%" monitor.py

echo.
echo [INFO] Console monitor stopped.
pause
