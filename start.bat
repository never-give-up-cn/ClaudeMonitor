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
    echo [ERROR] Python 3 not found.
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
    title Claude Monitor
    echo [INFO] Starting console monitor...
    %PY_CMD% monitor.py
    pause
    goto :eof
)

:: ===== GUI only =====
if /i "%MODE%"=="gui" (
    title Claude Monitor
    echo [INFO] Starting GUI window...
    start "Claude GUI" %PY_CMD% gui.py
    goto :eof
)

:: ===== Both (default) =====
title Claude Code Monitor
echo ========================================
echo   Claude Code Monitor
echo ========================================
echo.

:: Launch GUI window in a new window
echo [INFO] Starting GUI window...
start "Claude GUI" %PY_CMD% gui.py

:: Wait for GUI to initialize
timeout /t 2 /nobreak >nul

:: Launch console monitor in current window
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
