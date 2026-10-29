@echo off
title Remote Monitor Agent Installer
echo ========================================
echo   Remote Monitor Agent Installer
echo ========================================
echo.

REM ---------- Check / Install Python ----------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Downloading and installing Python 3.12...
    echo.
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '%TEMP%\python-installer.exe'"
    if not exist "%TEMP%\python-installer.exe" (
        echo Failed to download Python installer.
        pause
        exit /b 1
    )
    echo Installing Python (this may take a minute)...
    "%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del "%TEMP%\python-installer.exe" >nul 2>&1
    echo Python installed.
    echo Please close this window, open a new Command Prompt, and run start.bat again.
    pause
    exit /b 0
) else (
    echo Python found.
)

REM ---------- Download agent files ----------
echo.
echo Downloading agent files from GitHub...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/oliveman-au/remote-monitor/main/agent.py' -OutFile agent.py"
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/oliveman-au/remote-monitor/main/requirements.txt' -OutFile requirements.txt"
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/oliveman-au/remote-monitor/main/version.txt' -OutFile version.txt"

if not exist agent.py (
    echo.
    echo Failed to download agent.py.
    echo Make sure the GitHub repo is public:
    echo https://github.com/oliveman-au/remote-monitor
    pause
    exit /b 1
)

REM ---------- Install dependencies ----------
echo.
echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

REM ---------- Create startup entry ----------
echo.
echo Creating startup entry...
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
copy /Y agent.py "%STARTUP%\RemoteMonitorAgent.pyw" >nul
copy /Y version.txt "%STARTUP%\version.txt" >nul

echo @echo off > "%STARTUP%\RemoteMonitorAgent.bat"
echo start /min pythonw "%STARTUP%\RemoteMonitorAgent.pyw" >> "%STARTUP%\RemoteMonitorAgent.bat"

echo.
echo ========================================
echo   Installation complete
echo ========================================
echo Agent will start on next login.
echo It will auto-update from GitHub every minute.
echo You can remove it anytime by deleting the files in the Startup folder.
echo.
pause
