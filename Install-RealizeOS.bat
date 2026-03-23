@echo off
setlocal EnableDelayedExpansion
title RealizeOS V5 - Interactive Setup Wizard

:: --------------------------------------------------------------------------
:: 1. Self-Elevate to Administrator (Needed to bypass execution policies cleanly)
:: --------------------------------------------------------------------------
fsutil dirty query %systemdrive% >nul 2>&1
if !errorlevel! neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Anchor working directory to the script's location
cd /d "%~dp0"

:: --------------------------------------------------------------------------
:: 2. Welcome Screen & App Explanation
:: --------------------------------------------------------------------------
cls
color 0B
echo ==============================================================================
echo                              RealizeOS V5 Setup
echo ==============================================================================
echo.
echo Welcome to the RealizeOS Setup Wizard!
echo.
echo RealizeOS is an advanced, self-evolving AI Operations System built for absolute 
echo control, privacy, and performance. This installer will automatically:
echo   - Download and install Python (if you don't have it)
echo   - Download the latest RealizeOS secure package from GitHub
echo   - Install all necessary dependencies safely
echo   - Create a desktop shortcut to launch your local dashboard
echo.

:: --------------------------------------------------------------------------
:: 3. License Agreement (EULA)
:: --------------------------------------------------------------------------
echo ------------------------------------------------------------------------------
echo END-USER LICENSE AGREEMENT (EULA)
echo ------------------------------------------------------------------------------
echo By proceeding, you agree to use RealizeOS responsibly. RealizeOS is provided
echo "AS IS" without warranty of any kind. You are responsible for your own API
echo keys and token costs. 
echo ------------------------------------------------------------------------------
:EULA_PROMPT
set /p "AGREE=Do you accept these terms? (Y/N): "
if /I "!AGREE!"=="N" (
    echo Installation Cancelled by User.
    pause
    exit /b
)
if /I not "!AGREE!"=="Y" (
    echo Please type Y or N.
    goto EULA_PROMPT
)

:: --------------------------------------------------------------------------
:: 4. Installation Directory Selection
:: --------------------------------------------------------------------------
echo.
echo ------------------------------------------------------------------------------
echo INSTALLATION DIRECTORY
echo ------------------------------------------------------------------------------
set "DEFAULT_DIR=%USERPROFILE%\RealizeOS"
set "INSTALL_DIR="

set /p "INSTALL_DIR=Enter installation path (Press ENTER for Default: !DEFAULT_DIR!): "
if "!INSTALL_DIR!"=="" set "INSTALL_DIR=!DEFAULT_DIR!"

echo.
echo Setting up RealizeOS in: !INSTALL_DIR!
if not exist "!INSTALL_DIR!" (
    mkdir "!INSTALL_DIR!"
    if !errorlevel! neq 0 (
        echo [ERROR] Could not create directory: !INSTALL_DIR!
        echo Please ensure you have permission and try again.
        pause
        exit /b 1
    )
)

:: Common PowerShell Command Prefix for maximum compatibility
set "PS_CMD=powershell -NoProfile -ExecutionPolicy Bypass -Command"
set "TLS_PATCH=[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;"

:: --------------------------------------------------------------------------
:: 5. Python Installation Check
:: --------------------------------------------------------------------------
echo.
echo [1/4] Checking Python requirements...
python --version >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] Python is already installed!
) else (
    echo [!] Python not found. Downloading Python 3.11...
    set "PY_INSTALLER=%TEMP%\python_installer.exe"
    !PS_CMD! "!TLS_PATCH! Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe' -OutFile '!PY_INSTALLER!'"
    
    if not exist "!PY_INSTALLER!" (
        echo [ERROR] Failed to download Python. Please check your internet connection or install manually.
        pause
        exit /b 1
    )
    
    echo [!] Installing Python silently (this will take a minute or two)...
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    
    :: Refresh Environment Variables
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%PATH%"
    echo [OK] Python installed successfully!
)

:: --------------------------------------------------------------------------
:: 6. Download RealizeOS Core
:: --------------------------------------------------------------------------
echo.
echo [2/4] Downloading RealizeOS Core Package from GitHub...
set "ZIP_FILE=%TEMP%\RealizeOS-main.zip"

!PS_CMD! "!TLS_PATCH! Invoke-WebRequest -Uri 'https://github.com/SufZen/RealizeOS-5/archive/refs/heads/main.zip' -OutFile '!ZIP_FILE!'"

if not exist "!ZIP_FILE!" (
    echo [ERROR] Failed to download RealizeOS source code. 
    echo Check your internet connection or GitHub availability.
    pause
    exit /b 1
)

:: --------------------------------------------------------------------------
:: 7. Extraction
:: --------------------------------------------------------------------------
echo.
echo [3/4] Extracting system files...
set "TEMP_EXTRACT=%TEMP%\RealizeOS_Temp"
if exist "!TEMP_EXTRACT!" rmdir /s /q "!TEMP_EXTRACT!"

!PS_CMD! "Expand-Archive -Path '!ZIP_FILE!' -DestinationPath '!TEMP_EXTRACT!' -Force"
if !errorlevel! neq 0 (
    echo [ERROR] Failed to extract the ZIP archive.
    pause
    exit /b 1
)

:: Move core files to their permanent home
xcopy /s /e /y /q "!TEMP_EXTRACT!\RealizeOS-5-main\*" "!INSTALL_DIR!\" >nul
move /Y "!TEMP_EXTRACT!\RealizeOS-5-main\.gitattributes" "!INSTALL_DIR!\" >nul 2>&1
move /Y "!TEMP_EXTRACT!\RealizeOS-5-main\.env.example" "!INSTALL_DIR!\" >nul 2>&1

:: Cleanup temp files
rmdir /s /q "!TEMP_EXTRACT!"
del /f /q "!ZIP_FILE!"

:: --------------------------------------------------------------------------
:: 8. Dependency Installation & Desktop Shortcut
:: --------------------------------------------------------------------------
echo.
echo [4/4] Installing background AI dependencies...
cd /d "!INSTALL_DIR!"
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [WARNING] There was a minor issue installing some dependencies. The system will try to resolve this on launch.
) else (
    echo [OK] Dependencies installed successfully!
)

echo.
echo Creating Desktop Shortcut...
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\Start RealizeOS.lnk"
set "LAUNCHER_PATH=!INSTALL_DIR!\start-realizeos.bat"

!PS_CMD! "$wshell = New-Object -ComObject WScript.Shell; $shortcut = $wshell.CreateShortcut('!SHORTCUT_PATH!'); $shortcut.TargetPath = '!LAUNCHER_PATH!'; $shortcut.WorkingDirectory = '!INSTALL_DIR!'; $shortcut.Description = 'Launch RealizeOS V5 AI Dashboard'; $shortcut.Save()"

:: --------------------------------------------------------------------------
:: 9. Completion
:: --------------------------------------------------------------------------
cls
color 0A
echo ==============================================================================
echo                           INSTALLATION COMPLETE!
echo ==============================================================================
echo.
echo RealizeOS has been successfully installed to:
echo  !INSTALL_DIR!
echo.
echo A shortcut named "Start RealizeOS" is now on your Desktop.
echo.
echo Press any key to close this wizard and start the system for the first time!
echo.
pause >nul

cd /d "!INSTALL_DIR!"
start "" "!LAUNCHER_PATH!"
exit
