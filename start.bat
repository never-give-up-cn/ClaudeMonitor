@echo off
chcp 65001 >nul

set MODE=%~1
if "%MODE%"=="" set MODE=gui

cd /d "%~dp0"

:: find python
set PY_CMD=python
where python3 >nul 2>&1
if %errorlevel% equ 0 set PY_CMD=python3

where %PY_CMD% >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.7+
    pause
    exit /b 1
)

:: install deps
%PY_CMD% -c "import serial, psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing dependencies...
    %PY_CMD% -m pip install pyserial psutil -q
)

if /i "%MODE%"=="console" (
    title Claude Monitor - Console
    echo ========================================
    echo   Claude Code Monitor (Console)
    echo ========================================
    echo.
    %PY_CMD% monitor.py
    pause
) else (
    title Claude Monitor
    echo ========================================
    echo   Claude Code Monitor (Desktop)
    echo ========================================
    echo.
    echo [INFO] Launching status window...
    start "" %PY_CMD% gui.py
)
