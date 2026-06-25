@echo off
chcp 65001 >nul
title Claude Code 状态监控器

set MODE=%~1
if "%MODE%"=="" set MODE=gui

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 检测 Python3
python3 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python3，请安装 Python 3.7+
    pause
    exit /b 1
)

:: 检测依赖
python3 -c "import serial, psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 正在安装依赖...
    python3 -m pip install pyserial psutil -q
)

if /i "%MODE%"=="console" (
    title Claude Code 状态监控器 - 控制台版
    echo ========================================
    echo   Claude Code 工作状态监控器 (控制台版)
    echo   启动时间: %date% %time%
    echo   监控目录: %USERPROFILE%\Desktop
    echo.
    echo   按 Ctrl+C 停止监控
    echo ========================================
    echo.
    python3 monitor.py
    pause
) else (
    title Claude Code 状态监控器 - 桌面窗口版
    echo ========================================
    echo   Claude Code 工作状态监控器 (桌面窗口版)
    echo   启动时间: %date% %time%
    echo ========================================
    echo.
    start /b pythonw gui.py 2>nul || python3 gui.py
)
