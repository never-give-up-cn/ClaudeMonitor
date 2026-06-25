@echo off
chcp 65001 >nul

set MODE=%~1
if "%MODE%"=="" set MODE=both

cd /d "%~dp0"

:: find python (prefer pythonw for no-console modes)
set PY_CMD=python
set PY_CMD_W=pythonw
if exist "%SystemRoot%\py.exe" set PY_CMD=py -3
where pythonw >nul 2>&1 || set PY_CMD_W=%PY_CMD%

:: check python
%PY_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3 not found.
    pause
    exit /b 1
)

:: install deps silently
%PY_CMD% -c "import serial, psutil" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    %PY_CMD% -m pip install pyserial psutil -q
)

:: ===== Floating ball only (hidden console) =====
if /i "%MODE%"=="ball" (
    title Claude Monitor Ball
    echo [INFO] Starting floating ball...
    start "" "%PY_CMD_W%" "%CD%\floating_ball.py"
    goto :eof
)

:: ===== Console only =====
if /i "%MODE%"=="console" (
    title Claude Monitor
    echo [INFO] Starting console monitor...
    %PY_CMD% monitor.py
    pause
    goto :eof
)

:: ===== GUI only (no console) =====
if /i "%MODE%"=="gui" (
    title Claude Monitor
    echo [INFO] Starting GUI window...
    start "" "%PY_CMD_W%" "%CD%\gui.py"
    goto :eof
)

:: ===== Both (default: GUI + console) =====
if /i "%MODE%"=="both" (
    title Claude Code Monitor
    echo ========================================
    echo   Claude Code Monitor
    echo ========================================
    echo.
    echo [INFO] Starting GUI window + Console...
    start "" "%PY_CMD_W%" "%CD%\gui.py"
    timeout /t 2 /nobreak >nul
    %PY_CMD% monitor.py
    echo.
    echo [INFO] Console monitor stopped.
    pause
    goto :eof
)

:: ===== Ball + GUI (floating ball + GUI in background) =====
if /i "%MODE%"=="desktop" (
    title Claude Monitor Desktop
    echo ========================================
    echo   Claude Monitor - Desktop Mode
    echo ========================================
    echo.
    echo [INFO] Starting floating ball...
    start "" "%PY_CMD_W%" "%CD%\floating_ball.py"
    timeout /t 1 /nobreak >nul
    echo [INFO] Starting GUI in background...
    start "" "%PY_CMD_W%" "%CD%\gui.py"
    echo [INFO] Both running in background.
    echo Close floating ball from its right-click menu.
    pause
    goto :eof
)

:: Fallback
echo Usage: start.bat [ball^|console^|gui^|both^|desktop]
echo   (default)  both     - GUI window + Console
echo   ball       Floating ball only (no console)
echo   console    Console monitor only
echo   gui        GUI window only (hidden console)
echo   desktop    Floating ball + GUI (no console)
pause
