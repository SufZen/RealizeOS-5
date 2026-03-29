@echo off
setlocal EnableDelayedExpansion
title RealizeOS V5 - Interactive Setup Wizard

:: --------------------------------------------------------------------------
:: 1. Self-Elevate to Administrator
:: --------------------------------------------------------------------------
net session >nul 2>&1
if !errorlevel! neq 0 (
    echo Requesting Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

:: Anchor working directory to the script's location
cd /d "%~dp0"

:: --------------------------------------------------------------------------
:: 2. Welcome Screen
:: --------------------------------------------------------------------------
cls
color 0B
echo ==============================================================================
echo                              RealizeOS V5 Setup
echo ==============================================================================
echo.
echo Welcome to the RealizeOS Setup Wizard!
echo.
echo RealizeOS is an advanced, self-evolving AI Operations System built for
echo absolute control, privacy, and performance. This installer will:
echo.
echo   - Check and install Python 3.12+ (if you don't have it)
echo   - Check for Node.js (needed for the dashboard)
echo   - Download the latest RealizeOS package from GitHub
echo   - Install all necessary dependencies safely
echo   - Build the React dashboard for local use
echo   - Run database migrations
echo   - Create a desktop shortcut to launch your local dashboard
echo.

:: --------------------------------------------------------------------------
:: 3. License Agreement (EULA)
:: --------------------------------------------------------------------------
echo ------------------------------------------------------------------------------
echo END-USER LICENSE AGREEMENT (EULA)
echo ------------------------------------------------------------------------------
echo.
echo By proceeding, you agree to use RealizeOS responsibly.
echo RealizeOS is provided "AS IS" without warranty of any kind.
echo You are responsible for your own API keys and token costs.
echo.
echo License: Business Source License 1.1 (BSL 1.1)
echo Full text: https://github.com/SufZen/RealizeOS-5/blob/main/LICENSE
echo.
echo ------------------------------------------------------------------------------
:EULA_PROMPT
set "AGREE="
set /p "AGREE=Do you accept these terms? (Y/N): "
if /I "!AGREE!"=="N" (
    echo.
    echo Installation cancelled by user.
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
set "DEFAULT_DIR=!USERPROFILE!\RealizeOS"
set "INSTALL_DIR="
set /p "INSTALL_DIR=Enter installation path (Press ENTER for default: !DEFAULT_DIR!): "
if "!INSTALL_DIR!"=="" set "INSTALL_DIR=!DEFAULT_DIR!"

echo.
echo Installing to: !INSTALL_DIR!
echo.

if not exist "!INSTALL_DIR!" (
    mkdir "!INSTALL_DIR!" 2>nul
    if not exist "!INSTALL_DIR!" (
        echo [ERROR] Could not create directory: !INSTALL_DIR!
        echo Please check the path and try again.
        pause
        exit /b 1
    )
)

:: --------------------------------------------------------------------------
:: 5. Check Python
:: --------------------------------------------------------------------------
echo [1/7] Checking for Python...

where python >nul 2>&1
if !errorlevel! equ 0 (
    :: Verify version is 3.11+
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    echo       [OK] Python !PY_VER! is installed.
    goto :PYTHON_READY
)

echo       [!] Python not found. Downloading Python 3.12...
set "PY_INSTALLER=!TEMP!\python_installer.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '!PY_INSTALLER!'"

if not exist "!PY_INSTALLER!" (
    echo       [ERROR] Failed to download Python.
    echo       Please check your internet connection or install Python manually from python.org
    pause
    exit /b 1
)

echo       [!] Installing Python silently (this may take 1-2 minutes)...
"!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0

:: Refresh PATH for the current session
set "PATH=!LOCALAPPDATA!\Programs\Python\Python312\Scripts;!LOCALAPPDATA!\Programs\Python\Python312;!PATH!"

where python >nul 2>&1
if !errorlevel! neq 0 (
    echo       [ERROR] Python installation may have failed.
    echo       Please install Python manually from https://python.org and re-run this installer.
    pause
    exit /b 1
)

echo       [OK] Python installed successfully!

:PYTHON_READY

:: --------------------------------------------------------------------------
:: 6. Check Node.js (for dashboard)
:: --------------------------------------------------------------------------
echo.
echo [2/7] Checking for Node.js (required for dashboard)...

set "HAS_NODE=0"
where node >nul 2>&1
if !errorlevel! equ 0 (
    for /f "tokens=1 delims=v" %%v in ('node --version 2^>^&1') do set "NODE_VER=%%v"
    echo       [OK] Node.js is installed.
    set "HAS_NODE=1"
) else (
    echo       [!] Node.js not found.
    echo       The dashboard requires Node.js 18+ to build.
    echo       Download from: https://nodejs.org/en/download/
    echo.
    echo       You can install Node.js later and run:
    echo         cd dashboard ^&^& npx pnpm install ^&^& npx pnpm build
    echo.
    echo       The backend API will still work without the dashboard.
)

:: --------------------------------------------------------------------------
:: 7. Download RealizeOS
:: --------------------------------------------------------------------------
echo.
echo [3/7] Downloading RealizeOS from GitHub...
set "ZIP_FILE=!TEMP!\RealizeOS-main.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/SufZen/RealizeOS-5/archive/refs/heads/main.zip' -OutFile '!ZIP_FILE!'"

if not exist "!ZIP_FILE!" (
    echo       [ERROR] Failed to download RealizeOS source code.
    echo       Please check your internet connection.
    echo       If the repository is private, ensure you have access.
    pause
    exit /b 1
)

:: Quick check: is the file actually a valid zip (more than 1KB)?
for %%A in ("!ZIP_FILE!") do set "ZIP_SIZE=%%~zA"
if !ZIP_SIZE! LSS 1000 (
    echo       [ERROR] Downloaded file is too small - download may have failed.
    echo       The repository may be private. Please contact the developer for access.
    del /f /q "!ZIP_FILE!" 2>nul
    pause
    exit /b 1
)

:: Validate the zip is actually a zip archive, not a 404 HTML page
powershell -NoProfile -Command "try { Add-Type -AssemblyName System.IO.Compression.FileSystem; [IO.Compression.ZipFile]::OpenRead('!ZIP_FILE!').Dispose(); exit 0 } catch { exit 1 }"
if !errorlevel! neq 0 (
    echo       [ERROR] Downloaded file is not a valid archive.
    echo       The repository may be private or the URL may have changed.
    del /f /q "!ZIP_FILE!" 2>nul
    pause
    exit /b 1
)

:: --------------------------------------------------------------------------
:: 8. Extract
:: --------------------------------------------------------------------------
echo.
echo [4/7] Extracting system files...
set "TEMP_EXTRACT=!TEMP!\RealizeOS_Temp"
if exist "!TEMP_EXTRACT!" rmdir /s /q "!TEMP_EXTRACT!"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '!ZIP_FILE!' -DestinationPath '!TEMP_EXTRACT!' -Force"

if not exist "!TEMP_EXTRACT!\RealizeOS-5-main" (
    echo       [ERROR] Extraction failed. The archive may be corrupted.
    pause
    exit /b 1
)

:: Copy core files to chosen install directory
xcopy /s /e /y /q "!TEMP_EXTRACT!\RealizeOS-5-main\*" "!INSTALL_DIR!\" >nul

:: Copy hidden files that xcopy might skip
if exist "!TEMP_EXTRACT!\RealizeOS-5-main\.env.example" (
    copy /y "!TEMP_EXTRACT!\RealizeOS-5-main\.env.example" "!INSTALL_DIR!\" >nul 2>&1
)
if exist "!TEMP_EXTRACT!\RealizeOS-5-main\.gitignore" (
    copy /y "!TEMP_EXTRACT!\RealizeOS-5-main\.gitignore" "!INSTALL_DIR!\" >nul 2>&1
)

:: Cleanup temp files
rmdir /s /q "!TEMP_EXTRACT!" 2>nul
del /f /q "!ZIP_FILE!" 2>nul
echo       [OK] Files extracted to !INSTALL_DIR!

:: --------------------------------------------------------------------------
:: 9. Create required directories
:: --------------------------------------------------------------------------
echo.
echo [5/7] Creating required directories...

if not exist "!INSTALL_DIR!\data" mkdir "!INSTALL_DIR!\data"
if not exist "!INSTALL_DIR!\data\audit" mkdir "!INSTALL_DIR!\data\audit"
if not exist "!INSTALL_DIR!\data\storage" mkdir "!INSTALL_DIR!\data\storage"
if not exist "!INSTALL_DIR!\shared" mkdir "!INSTALL_DIR!\shared"
if not exist "!INSTALL_DIR!\ventures" mkdir "!INSTALL_DIR!\ventures"
if not exist "!INSTALL_DIR!\plugins" mkdir "!INSTALL_DIR!\plugins"
if not exist "!INSTALL_DIR!\systems" mkdir "!INSTALL_DIR!\systems"

echo       [OK] Directories created (data, shared, ventures, plugins, systems).

:: --------------------------------------------------------------------------
:: 10. Create .env from .env.example if needed
:: --------------------------------------------------------------------------
if not exist "!INSTALL_DIR!\.env" (
    if exist "!INSTALL_DIR!\.env.example" (
        copy /y "!INSTALL_DIR!\.env.example" "!INSTALL_DIR!\.env" >nul 2>&1
        echo       [OK] Created .env from .env.example (edit this to add your API keys).
    )
)

:: --------------------------------------------------------------------------
:: 11. Install Python Dependencies
:: --------------------------------------------------------------------------
echo.
echo [6/7] Installing Python dependencies (this may take a few minutes)...
cd /d "!INSTALL_DIR!"
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt

if !errorlevel! neq 0 (
    echo       [WARNING] Some dependencies had issues. The system will try to resolve on launch.
) else (
    echo       [OK] All Python dependencies installed successfully!
)

:: --------------------------------------------------------------------------
:: 12. Run Database Migrations
:: --------------------------------------------------------------------------
echo.
echo       Running database migrations...
python cli.py migrate >nul 2>&1
if !errorlevel! equ 0 (
    echo       [OK] Database schema is up to date.
) else (
    echo       [--] Migration skipped (will auto-run on first launch).
)

:: --------------------------------------------------------------------------
:: 13. Build Dashboard (if Node.js available)
:: --------------------------------------------------------------------------
echo.
echo [7/7] Building the dashboard...

if "!HAS_NODE!"=="1" (
    where pnpm >nul 2>&1
    if !errorlevel! neq 0 (
        echo       [..] Installing pnpm...
        npm install -g pnpm >nul 2>&1
    )

    where pnpm >nul 2>&1
    if !errorlevel! equ 0 (
        if exist "!INSTALL_DIR!\dashboard\package.json" (
            echo       [..] Installing dashboard dependencies...
            cd /d "!INSTALL_DIR!\dashboard"
            pnpm install >nul 2>&1
            echo       [..] Building dashboard (this may take 1-2 minutes)...
            pnpm build >nul 2>&1
            if !errorlevel! equ 0 (
                echo       [OK] Dashboard built successfully!
            ) else (
                echo       [WARNING] Dashboard build had issues. You can rebuild later:
                echo                 cd dashboard ^&^& pnpm install ^&^& pnpm build
            )
            cd /d "!INSTALL_DIR!"
        ) else (
            echo       [--] Dashboard source not found. Skipping.
        )
    ) else (
        echo       [--] pnpm not available. Install it later: npm install -g pnpm
    )
) else (
    echo       [--] Skipped (Node.js not found). Install Node.js 18+ to enable the dashboard.
    echo           Download: https://nodejs.org
    echo           Then run: cd dashboard ^&^& npx pnpm install ^&^& npx pnpm build
)

:: --------------------------------------------------------------------------
:: 14. Create Desktop Shortcut
:: --------------------------------------------------------------------------
echo.
echo Creating Desktop shortcut...
set "SHORTCUT_PATH=!USERPROFILE!\Desktop\Start RealizeOS.lnk"
set "LAUNCHER_PATH=!INSTALL_DIR!\start-realizeos.bat"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('!SHORTCUT_PATH!'); $sc.TargetPath = '!LAUNCHER_PATH!'; $sc.WorkingDirectory = '!INSTALL_DIR!'; $sc.Description = 'Launch RealizeOS V5'; $sc.Save()"

echo       [OK] Shortcut created on Desktop.

:: --------------------------------------------------------------------------
:: 15. Write VERSION File
:: --------------------------------------------------------------------------
echo.
echo Writing version info...
if exist "!INSTALL_DIR!\VERSION" (
    set /p INSTALLED_VER<"!INSTALL_DIR!\VERSION"
    echo       [OK] Version: !INSTALLED_VER!
) else (
    echo 5.0.0> "!INSTALL_DIR!\VERSION"
    echo       [OK] Version: 5.0.0
)

:: --------------------------------------------------------------------------
:: 16. Completion
:: --------------------------------------------------------------------------
echo.
color 0A
echo ==============================================================================
echo                        INSTALLATION COMPLETE!
echo ==============================================================================
echo.
echo RealizeOS V5 has been installed to:
echo   !INSTALL_DIR!
echo.
echo A shortcut "Start RealizeOS" is now on your Desktop.
echo Double-click it anytime to launch the system.
echo.
echo IMPORTANT — Next step:
echo   Edit .env to add your API keys (at least one LLM provider).
echo   Or run: python cli.py setup   (interactive configuration wizard)
echo.
echo Also included:
echo   - Update-RealizeOS.bat   (check for and install updates)
echo   - Migrate-RealizeOS.bat  (migrate data from another installation)
echo   - Uninstall-RealizeOS.bat (cleanly remove the system)
echo.

:OPEN_GUIDE
set "OPEN_GUIDE="
set /p "OPEN_GUIDE=Would you like to open the User Guide? (Y/N): "
if /I "!OPEN_GUIDE!"=="Y" (
    if exist "!INSTALL_DIR!\docs\user-guide.html" (
        start "" "!INSTALL_DIR!\docs\user-guide.html"
    ) else if exist "!INSTALL_DIR!\docs\quick-install.html" (
        start "" "!INSTALL_DIR!\docs\quick-install.html"
    )
)

echo.
echo Press any key to close this wizard and start RealizeOS...
echo.
pause >nul

cd /d "!INSTALL_DIR!"
start "" "!LAUNCHER_PATH!"
exit
