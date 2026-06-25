@echo off
chcp 65001 >nul 2>&1

set MODE=%~1
if "%MODE%"=="" set MODE=both

cd /d "%~dp0"

:: ===== Find Python 3 =====
set PY_CMD=
set PY_CMD_W=

:: 1) py launcher (Windows embeddable)
py -3 --version >nul 2>&1
if errorlevel 1 goto :try_python3
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :try_python3
set PY_CMD=py -3
set PY_CMD_W=pyw -3
goto :found_py

:try_python3
:: 2) python3
python3 --version >nul 2>&1
if errorlevel 1 goto :try_python
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :try_python
set PY_CMD=python3
where pythonw >nul 2>&1 && set PY_CMD_W=pythonw || set PY_CMD_W=python3
goto :found_py

:try_python
:: 3) python (must be 3.x)
python --version 2>&1 | find "Python 3" >nul
if errorlevel 1 goto :no_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if errorlevel 1 goto :no_py
set PY_CMD=python
where pythonw >nul 2>&1 && set PY_CMD_W=pythonw || set PY_CMD_W=python
goto :found_py

:no_py
echo [ERROR] Python 3.7+ not found.
echo Install from https://www.python.org/downloads/
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
        echo [WARN] Deps install failed, some features may not work
    )
)

:: ===== Launch mode =====

:: Ball only
if /i "%MODE%"=="ball" (
    title Claude Monitor - Ball
    start "" "%PY_CMD_W%" "%CD%\floating_ball.py"
    exit /b 0
)

:: Console only
if /i "%MODE%"=="console" (
    title Claude Monitor - Console
    %PY_CMD% monitor.py
    pause
    exit /b 0
)

:: GUI only (no console)
if /i "%MODE%"=="gui" (
    title Claude Monitor - GUI
    start "" "%PY_CMD_W%" "%CD%\gui.py"
    exit /b 0
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
    exit /b 0
)

:: Desktop: ball + GUI
if /i "%MODE%"=="desktop" (
    title Claude Monitor - Desktop
    echo ========================================
    echo   Claude Monitor - Desktop Mode
    echo ========================================
    echo.
    start "" "%PY_CMD_W%" "%CD%\floating_ball.py"
    timeout /t 1 /nobreak >nul
    start "" "%PY_CMD_W%" "%CD%\gui.py"
    echo [INFO] Floating ball + GUI running in background
    pause
    exit /b 0
)

echo Usage: start.bat [ball^|console^|gui^|both^|desktop]
echo   (default)  both     - GUI + Console
echo   ball       - Floating ball only (no window)
echo   console    - Console monitor only
echo   gui        - GUI only (no console)
echo   desktop    - Ball + GUI (no console)
pause
