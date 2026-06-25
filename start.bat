@echo off
chcp 65001 >nul

set MODE=%~1
if "%MODE%"=="" set MODE=gui

cd /d "%~dp0"

:: check python3
where python3 >nul 2>&1
if %errorlevel% neq 0 (
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found. Please install Python 3.7+
        pause
        exit /b 1
    )
    set PYTHON=python
) else (
    set PYTHON=python3
)

:: install deps
%PYTHON% -c "import serial, psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing dependencies...
    %PYTHON% -m pip install pyserial psutil -q
)

if /i "%MODE%"=="console" (
    title Claude Monitor - Console
    echo ========================================
    echo   Claude Code Status Monitor (Console)
    echo ========================================
    echo.
    %PYTHON% monitor.py
    pause
) else (
    title Claude Monitor - Desktop
    echo ========================================
    echo   Claude Code Status Monitor (Desktop)
    echo ========================================
    echo.
    start /b pythonw gui.py 2>nul || %PYTHON% gui.py
)
