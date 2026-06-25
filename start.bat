@echo off
chcp 65001 >nul

set MODE=%~1
if "%MODE%"=="" set MODE=both

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

:: ===== Console only =====
if /i "%MODE%"=="console" (
    title Claude Monitor - Console
    echo ========================================
    echo   Claude Code Monitor (Console)
    echo ========================================
    echo.
    %PY_CMD% monitor.py
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
    start /b %PY_CMD% gui.py >"%CD%\gui.log" 2>&1
    echo [INFO] GUI started. Check desktop for window.
    timeout /t 3 /nobreak >nul
    goto :eof
)

:: ===== Both (default) =====
title Claude Code Monitor
echo ========================================
echo   Claude Code Monitor
echo ========================================
echo.

:: Launch GUI in background
echo [INFO] Starting GUI window...
start /b %PY_CMD% gui.py >"%CD%\gui.log" 2>&1

:: Wait for GUI to initialize
timeout /t 2 /nobreak >nul

:: Check log for errors silently
findstr /m "Traceback" "%CD%\gui.log" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARN] gui.py had errors. Check gui.log
) else (
    echo [INFO] GUI is running.
)

:: Launch console monitor in foreground
echo.
echo [INFO] Starting console monitor...
echo -------------------------------------------------
echo  GUI window + Console both running
echo  Close this window = stop console monitor
echo -------------------------------------------------
echo.
%PY_CMD% monitor.py

echo.
echo [INFO] Console monitor stopped.
pause
