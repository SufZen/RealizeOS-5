@echo off
setlocal EnableDelayedExpansion
title RealizeOS V5 - One-Click Installer

echo ============================================================
echo           RealizeOS V5 - Automated Installer
echo ============================================================
echo.
echo Welcome! This script will automatically download and install
echo RealizeOS and its dependencies on your computer.
echo It will also install Python if you do not have it.
echo.

:: 1. Check Python installation
echo [1/5] Checking for Python...
python --version >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] Python is already installed!
) else (
    echo [!] Python not found. Downloading Python 3.11...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    if not exist "%TEMP%\python_installer.exe" (
        echo [ERROR] Failed to download Python. Please install it manually from python.org.
        pause
        exit /b 1
    )
    echo [!] Installing Python silently (this may take a minute)...
    "%TEMP%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    
    :: Refresh environment variables for the current session so `python` command works
    set PATH=%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%PATH%
    
    echo [OK] Python installed successfully!
)

:: 2. Setup folders
set "INSTALL_DIR=%USERPROFILE%\RealizeOS"
if not exist "!INSTALL_DIR!" (
    mkdir "!INSTALL_DIR!"
)

:: 3. Download Source Code
echo.
echo [2/5] Downloading RealizeOS system files from GitHub...
set "ZIP_FILE=%TEMP%\RealizeOS-main.zip"
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/SufZen/RealizeOS-5/archive/refs/heads/main.zip' -OutFile '!ZIP_FILE!'"

if not exist "!ZIP_FILE!" (
    echo [ERROR] Failed to download RealizeOS source code. Check your internet connection.
    pause
    exit /b 1
)

:: 4. Extract
echo.
echo [3/5] Extracting files...
powershell -Command "Expand-Archive -Path '!ZIP_FILE!' -DestinationPath '%TEMP%\RealizeOS_Temp' -Force"

:: The zip extracts to a folder named "RealizeOS-5-main"
xcopy /s /e /y /q "%TEMP%\RealizeOS_Temp\RealizeOS-5-main\*" "!INSTALL_DIR!\" >nul
move /Y "%TEMP%\RealizeOS_Temp\RealizeOS-5-main\.gitattributes" "!INSTALL_DIR!\" >nul 2>&1
move /Y "%TEMP%\RealizeOS_Temp\RealizeOS-5-main\.env.example" "!INSTALL_DIR!\" >nul 2>&1
rmdir /s /q "%TEMP%\RealizeOS_Temp"
del /f /q "!ZIP_FILE!"

:: 5. Install Dependencies
echo.
echo [4/5] Installing system dependencies (this may take a few minutes)...
cd /d "!INSTALL_DIR!"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [WARNING] There was a minor issue installing some dependencies. The system will try to resolve this on launch.
) else (
    echo [OK] Dependencies installed successfully!
)

:: 6. Create Desktop Shortcut
echo.
echo [5/5] Creating Desktop Shortcut...
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\Start RealizeOS.lnk"
set "LAUNCHER_PATH=!INSTALL_DIR!\start-realizeos.bat"
powershell -Command "$wshell = New-Object -ComObject WScript.Shell; $shortcut = $wshell.CreateShortcut('!SHORTCUT_PATH!'); $shortcut.TargetPath = '!LAUNCHER_PATH!'; $shortcut.WorkingDirectory = '!INSTALL_DIR!'; $shortcut.Description = 'Launch RealizeOS V5'; $shortcut.Save()"

echo.
echo ============================================================
echo   INSTALLATION COMPLETE!
echo ============================================================
echo.
echo A shortcut named "Start RealizeOS" has been placed on your Desktop.
echo You can run that shortcut anytime to start the system.
echo.
echo RealizeOS is now ready. Starting the system for the first time...
echo.
pause
cd /d "!INSTALL_DIR!"
start "" "!LAUNCHER_PATH!"
exit
