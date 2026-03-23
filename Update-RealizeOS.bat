@echo off
setlocal EnableDelayedExpansion
title RealizeOS V5 - Updater

:: --------------------------------------------------------------------------
:: 1. Self-Elevate to Administrator
:: --------------------------------------------------------------------------
net session >nul 2>&1
if !errorlevel! neq 0 (
    echo Requesting Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

:: --------------------------------------------------------------------------
:: 2. Welcome Screen
:: --------------------------------------------------------------------------
cls
color 0B
echo ==============================================================================
echo                         RealizeOS V5 - Update Wizard
echo ==============================================================================
echo.

:: --------------------------------------------------------------------------
:: 3. Read Current Version
:: --------------------------------------------------------------------------
set "CURRENT_VERSION=unknown"
if exist "VERSION" (
    set /p CURRENT_VERSION=<VERSION
)
echo Current version: !CURRENT_VERSION!
echo.

:: --------------------------------------------------------------------------
:: 4. Check for Latest Release via GitHub API
:: --------------------------------------------------------------------------
echo [1/6] Checking for updates...
set "API_URL=https://api.github.com/repos/SufZen/RealizeOS-5/releases/latest"
set "RELEASE_JSON=!TEMP!\realizeos-release.json"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { $r = Invoke-RestMethod -Uri '!API_URL!' -Headers @{'User-Agent'='RealizeOS-Updater'}; $r | ConvertTo-Json -Depth 3 | Out-File -Encoding UTF8 '!RELEASE_JSON!'; Write-Host 'OK' } catch { Write-Host 'FALLBACK' }"

set "USE_FALLBACK=0"

:: If no releases exist yet, fall back to main branch
if not exist "!RELEASE_JSON!" set "USE_FALLBACK=1"
for %%A in ("!RELEASE_JSON!") do if %%~zA LSS 50 set "USE_FALLBACK=1"

if "!USE_FALLBACK!"=="1" (
    echo       [!] No GitHub Release found. Checking main branch...
    set "DOWNLOAD_URL=https://github.com/SufZen/RealizeOS-5/archive/refs/heads/main.zip"
    set "LATEST_VERSION=main-latest"
    set "RELEASE_NOTES=Updated to latest main branch."
    goto :HAVE_URL
)

:: Parse release info
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-Content '!RELEASE_JSON!' | ConvertFrom-Json).tag_name"`) do set "LATEST_VERSION=%%i"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-Content '!RELEASE_JSON!' | ConvertFrom-Json).zipball_url"`) do set "DOWNLOAD_URL=%%i"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$b=(Get-Content '!RELEASE_JSON!' | ConvertFrom-Json).body; if($b){$b.Substring(0,[Math]::Min(500,$b.Length))}else{'No release notes.'}"`) do set "RELEASE_NOTES=%%i"

:: Clean up version tag (remove leading 'v' if present)
set "CLEAN_LATEST=!LATEST_VERSION!"
if "!CLEAN_LATEST:~0,1!"=="v" set "CLEAN_LATEST=!CLEAN_LATEST:~1!"

:: Compare versions
if "!CURRENT_VERSION!"=="!CLEAN_LATEST!" (
    echo.
    color 0A
    echo ==============================================================================
    echo                         ALREADY UP TO DATE
    echo ==============================================================================
    echo.
    echo You are running the latest version: !CURRENT_VERSION!
    echo.
    pause
    exit /b
)

echo       Latest version: !LATEST_VERSION!
echo.

:HAVE_URL

:: --------------------------------------------------------------------------
:: 5. Show Release Notes
:: --------------------------------------------------------------------------
echo ------------------------------------------------------------------------------
echo WHAT'S NEW
echo ------------------------------------------------------------------------------
echo.
echo !RELEASE_NOTES!
echo.
echo ------------------------------------------------------------------------------
echo.

:UPDATE_PROMPT
set "PROCEED="
set /p "PROCEED=Update from !CURRENT_VERSION! to !LATEST_VERSION!? (Y/N): "
if /I "!PROCEED!"=="N" (
    echo Update cancelled.
    pause
    exit /b
)
if /I not "!PROCEED!"=="Y" (
    echo Please type Y or N.
    goto UPDATE_PROMPT
)

:: --------------------------------------------------------------------------
:: 6. Backup User Files
:: --------------------------------------------------------------------------
echo.
echo [2/6] Backing up your data...
set "BACKUP_DIR=!TEMP!\RealizeOS-Update-Backup"
if exist "!BACKUP_DIR!" rmdir /s /q "!BACKUP_DIR!"
mkdir "!BACKUP_DIR!"

:: Back up critical user files
if exist ".env"              copy /y ".env" "!BACKUP_DIR!\" >nul 2>&1
if exist "realize-os.yaml"   copy /y "realize-os.yaml" "!BACKUP_DIR!\" >nul 2>&1
if exist "VERSION"           copy /y "VERSION" "!BACKUP_DIR!\VERSION.old" >nul 2>&1

:: Back up directories
if exist "systems"           xcopy /s /e /y /q "systems\*" "!BACKUP_DIR!\systems\" >nul 2>&1
if exist ".credentials"      xcopy /s /e /y /q ".credentials\*" "!BACKUP_DIR!\.credentials\" >nul 2>&1

:: Back up databases
for %%f in (*.db *.sqlite *.sqlite3) do (
    if exist "%%f" copy /y "%%f" "!BACKUP_DIR!\" >nul 2>&1
)

echo       [OK] User data backed up.

:: --------------------------------------------------------------------------
:: 7. Download Update
:: --------------------------------------------------------------------------
echo.
echo [3/6] Downloading update...
set "ZIP_FILE=!TEMP!\RealizeOS-update.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '!DOWNLOAD_URL!' -OutFile '!ZIP_FILE!' -Headers @{'User-Agent'='RealizeOS-Updater'}"

if not exist "!ZIP_FILE!" (
    echo       [ERROR] Download failed. Restoring backup...
    goto :ROLLBACK
)

for %%A in ("!ZIP_FILE!") do set "ZIP_SIZE=%%~zA"
if !ZIP_SIZE! LSS 1000 (
    echo       [ERROR] Downloaded file is too small. Restoring backup...
    goto :ROLLBACK
)

echo       [OK] Download complete.

:: --------------------------------------------------------------------------
:: 8. Extract Update
:: --------------------------------------------------------------------------
echo.
echo [4/6] Extracting update files...
set "TEMP_EXTRACT=!TEMP!\RealizeOS-Update-Extract"
if exist "!TEMP_EXTRACT!" rmdir /s /q "!TEMP_EXTRACT!"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Expand-Archive -Path '!ZIP_FILE!' -DestinationPath '!TEMP_EXTRACT!' -Force"

:: Find the extracted folder (could be RealizeOS-5-main or RealizeOS-5-vX.X.X)
set "SOURCE_DIR="
for /d %%d in ("!TEMP_EXTRACT!\*") do set "SOURCE_DIR=%%d"

if not defined SOURCE_DIR (
    echo       [ERROR] Extraction failed. Restoring backup...
    goto :ROLLBACK
)

:: Copy updated files (overwrite system files, not user files)
xcopy /s /e /y /q "!SOURCE_DIR!\*" "%~dp0" >nul 2>&1
echo       [OK] Files updated.

:: --------------------------------------------------------------------------
:: 9. Restore User Files
:: --------------------------------------------------------------------------
echo.
echo [5/6] Restoring your data...

if exist "!BACKUP_DIR!\.env"            copy /y "!BACKUP_DIR!\.env" "%~dp0" >nul 2>&1
if exist "!BACKUP_DIR!\realize-os.yaml" copy /y "!BACKUP_DIR!\realize-os.yaml" "%~dp0" >nul 2>&1
if exist "!BACKUP_DIR!\systems"         xcopy /s /e /y /q "!BACKUP_DIR!\systems\*" "%~dp0systems\" >nul 2>&1
if exist "!BACKUP_DIR!\.credentials"    xcopy /s /e /y /q "!BACKUP_DIR!\.credentials\*" "%~dp0.credentials\" >nul 2>&1

:: Restore databases
for %%f in ("!BACKUP_DIR!\*.db" "!BACKUP_DIR!\*.sqlite" "!BACKUP_DIR!\*.sqlite3") do (
    if exist "%%f" copy /y "%%f" "%~dp0" >nul 2>&1
)

echo       [OK] User data restored.

:: --------------------------------------------------------------------------
:: 10. Update Dependencies
:: --------------------------------------------------------------------------
echo.
echo [6/6] Updating dependencies...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt >nul 2>&1

if !errorlevel! neq 0 (
    echo       [WARNING] Some dependencies had issues. System will try to resolve on launch.
) else (
    echo       [OK] Dependencies updated.
)

:: --------------------------------------------------------------------------
:: 11. Cleanup & Completion
:: --------------------------------------------------------------------------
rmdir /s /q "!TEMP_EXTRACT!" 2>nul
del /f /q "!ZIP_FILE!" 2>nul
del /f /q "!RELEASE_JSON!" 2>nul
rmdir /s /q "!BACKUP_DIR!" 2>nul

echo.
color 0A
echo ==============================================================================
echo                          UPDATE COMPLETE!
echo ==============================================================================
echo.
echo RealizeOS has been updated to version !LATEST_VERSION!
echo.
echo Your user data (FABRIC files, .env, databases) has been preserved.
echo.
echo Press any key to close...
pause >nul
exit /b

:: --------------------------------------------------------------------------
:: ROLLBACK — Restore from backup on failure
:: --------------------------------------------------------------------------
:ROLLBACK
echo.
color 0E
echo [!] Rolling back to previous version...
if exist "!BACKUP_DIR!\.env"            copy /y "!BACKUP_DIR!\.env" "%~dp0" >nul 2>&1
if exist "!BACKUP_DIR!\realize-os.yaml" copy /y "!BACKUP_DIR!\realize-os.yaml" "%~dp0" >nul 2>&1
if exist "!BACKUP_DIR!\VERSION.old"     copy /y "!BACKUP_DIR!\VERSION.old" "%~dp0\VERSION" >nul 2>&1
if exist "!BACKUP_DIR!\systems"         xcopy /s /e /y /q "!BACKUP_DIR!\systems\*" "%~dp0systems\" >nul 2>&1
if exist "!BACKUP_DIR!\.credentials"    xcopy /s /e /y /q "!BACKUP_DIR!\.credentials\*" "%~dp0.credentials\" >nul 2>&1

echo [OK] Rollback complete. Your system is unchanged.
echo.
pause
exit /b 1
