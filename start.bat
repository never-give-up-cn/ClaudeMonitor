@echo off
chcp 65001 >nul 2>&1

set MODE=%~1
if "%MODE%"=="" set MODE=both

cd /d "%~dp0"

:: ===== Find Python 3 =====
set PY_CMD=

:: 1) py launcher
py -3 --version >nul 2>&1
if errorlevel 1 goto :try_python3
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :try_python3
set PY_CMD=py -3
set PY_CMD_W=pyw -3
set PY_USE_CMD=/c
goto :found_py

:try_python3
:: 2) python3
python3 --version >nul 2>&1
if errorlevel 1 goto :try_python
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :try_python
set PY_CMD=python3
set PY_CMD_W=pythonw
set PY_USE_CMD=
goto :found_py

:try_python
:: 3) python
python --version 2>&1 | find "Python 3" >nul
if errorlevel 1 goto :no_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :no_py
set PY_CMD=python
set PY_CMD_W=pythonw
set PY_USE_CMD=
goto :found_py

:no_py
echo [ERROR] Python 3.7+ not found.
pause
exit /b 1

:found_py
:: ===== Install deps =====
%PY_CMD% -c "import serial, psutil" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing pyserial, psutil...
    %PY_CMD% -m pip install pyserial psutil -q --trusted-host pypi.org --trusted-host files.pythonhosted.org 2>nul
    %PY_CMD% -c "import serial, psutil" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Trying mirror...
        %PY_CMD% -m pip install pyserial psutil -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
    )
    %PY_CMD% -c "import serial, psutil" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Deps install failed
    )
)

:: ===== Launch helpers =====
set RUN_BALL=%PY_CMD_W% "%CD%\floating_ball.py"
set RUN_GUI=%PY_CMD_W% "%CD%\gui.py"
if not "%PY_USE_CMD%"=="" (
    set RUN_BALL=cmd /c %PY_CMD_W% "%CD%\floating_ball.py"
    set RUN_GUI=cmd /c %PY_CMD_W% "%CD%\gui.py"
)

:: ===== Launch mode =====

if /i "%MODE%"=="ball" (
    title Claude Monitor - Ball
    start "" %RUN_BALL%
    exit /b 0
)

if /i "%MODE%"=="console" (
    title Claude Monitor - Console
    %PY_CMD% monitor.py
    pause
    exit /b 0
)

if /i "%MODE%"=="gui" (
    title Claude Monitor - GUI
    start "" %RUN_GUI%
    exit /b 0
)

if /i "%MODE%"=="both" (
    title Claude Code Monitor
    echo ========================================
    echo   Claude Code Monitor
    echo ========================================
    echo.
    start "" %RUN_GUI%
    timeout /t 2 /nobreak >nul
    %PY_CMD% monitor.py
    echo.
    pause
    exit /b 0
)

if /i "%MODE%"=="desktop" (
    title Claude Monitor - Desktop
    echo ========================================
    echo   Claude Monitor - Desktop Mode
    echo ========================================
    echo.
    start "" %RUN_BALL%
    timeout /t 1 /nobreak >nul
    start "" %RUN_GUI%
    echo [INFO] Running in background
    pause
    exit /b 0
)

echo Usage: start.bat [ball^|console^|gui^|both^|desktop]
pause
