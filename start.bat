@echo off
chcp 65001 >nul 2>&1

set MODE=%~1
if "%MODE%"=="" set MODE=both

cd /d "%~dp0"

:: ===== 找 Python 3 =====
set PY_CMD=

:: 1) Windows Python Launcher
py -3 --version >nul 2>&1
if errorlevel 1 goto :try_python3
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :try_python3
set PY_CMD=py -3
set PY_CMD_W=py -3w
goto :found_py

:try_python3
:: 2) python3
python3 --version >nul 2>&1
if errorlevel 1 goto :try_python
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :try_python
set PY_CMD=python3
set PY_CMD_W=pythonw
goto :found_py

:try_python
:: 3) python (必须是 3.x)
python --version 2>&1 | find "Python 3" >nul
if errorlevel 1 goto :no_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :no_py
set PY_CMD=python
set PY_CMD_W=pythonw
goto :found_py

:no_py
echo [ERROR] 需要 Python 3.7+，未找到。
echo 请从 https://www.python.org/downloads/ 安装
pause
exit /b 1

:found_py
:: ===== 安装依赖 =====
%PY_CMD% -c "import serial, psutil" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 正在安装依赖 (pyserial, psutil)...
    %PY_CMD% -m pip install pyserial psutil -q --trusted-host pypi.org --trusted-host files.pythonhosted.org 2>nul
    %PY_CMD% -c "import serial, psutil" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] 尝试使用国内镜像...
        %PY_CMD% -m pip install pyserial psutil -q -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn 2>nul
    )
    %PY_CMD% -c "import serial, psutil" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] 依赖安装失败，部分功能可能不可用
    ) else (
        echo [OK] 依赖安装完成
    )
)

:: ===== 启动模式 =====

:: Floating ball only
if /i "%MODE%"=="ball" (
    title Claude Monitor - Ball
    echo [INFO] 启动桌面悬浮球...
    start "" "%PY_CMD_W%" "%CD%\floating_ball.py"
    goto :eof
)

:: Console only
if /i "%MODE%"=="console" (
    title Claude Monitor - Console
    echo [INFO] 启动控制台监控...
    %PY_CMD% monitor.py
    pause
    goto :eof
)

:: GUI only (no console)
if /i "%MODE%"=="gui" (
    title Claude Monitor - GUI
    echo [INFO] 启动桌面窗口...
    start "" "%PY_CMD_W%" "%CD%\gui.py"
    goto :eof
)

:: Both: GUI + console (default)
if /i "%MODE%"=="both" (
    title Claude Code Monitor
    echo ========================================
    echo   Claude Code Monitor
    echo ========================================
    echo.
    start "" "%PY_CMD_W%" "%CD%\gui.py"
    timeout /t 2 /nobreak >nul
    %PY_CMD% monitor.py
    echo.
    pause
    goto :eof
)

:: Desktop: floating ball + GUI background
if /i "%MODE%"=="desktop" (
    title Claude Monitor - Desktop
    echo ========================================
    echo   Claude Monitor - Desktop Mode
    echo ========================================
    echo.
    start "" "%PY_CMD_W%" "%CD%\floating_ball.py"
    timeout /t 1 /nobreak >nul
    start "" "%PY_CMD_W%" "%CD%\gui.py"
    echo [INFO] 悬浮球 + GUI 已在后台运行
    echo 右键悬浮球可退出
    pause
    goto :eof
)

echo Usage: start.bat [ball^|console^|gui^|both^|desktop]
echo   (default)  both     - GUI窗口 + 控制台
echo   ball       - 仅桌面悬浮球（无窗口）
echo   console    - 仅控制台监控
echo   gui        - 仅GUI窗口（无控制台）
echo   desktop    - 悬浮球 + GUI（无控制台）
pause
