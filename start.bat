@echo off
title Remote Monitor Agent Installer
echo ========================================
echo   Remote Monitor Agent Installer
echo ========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Downloading Python 3.12...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe -OutFile %TEMP%\python-installer.exe"
    if not exist %TEMP%\python-installer.exe (
        echo Download failed.
        pause
        exit /b 1
    )
    echo Installing Python...
    %TEMP%\python-installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del %TEMP%\python-installer.exe
    echo.
    echo Python installed. Close this window, open a new one, and run start.bat again.
    pause
    exit /b 0
)
echo Python found.

echo.
echo Downloading files...
powershell -NoProfile -Command "Invoke-WebRequest -Uri https://raw.githubusercontent.com/oliveman-au/remote-monitor/main/agent.py -OutFile agent.py"
powershell -NoProfile -Command "Invoke-WebRequest -Uri https://raw.githubusercontent.com/oliveman-au/remote-monitor/main/requirements.txt -OutFile requirements.txt"
powershell -NoProfile -Command "Invoke-WebRequest -Uri https://raw.githubusercontent.com/oliveman-au/remote-monitor/main/version.txt -OutFile version.txt"

if not exist agent.py (
    echo Download failed. Is the repo public?
    pause
    exit /b 1
)

echo.
echo Installing packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo Setting up startup...
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
copy /Y agent.py "%STARTUP%\RemoteMonitorAgent.pyw"
copy /Y version.txt "%STARTUP%\version.txt"
echo @echo off > "%STARTUP%\RemoteMonitorAgent.bat"
echo start /min pythonw "%STARTUP%\RemoteMonitorAgent.pyw" >> "%STARTUP%\RemoteMonitorAgent.bat"

echo.
echo Done. Agent will start on next login.
pause
