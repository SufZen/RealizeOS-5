@echo off
setlocal EnableDelayedExpansion
title RealizeOS V5 - Uninstaller

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
color 0C
echo ==============================================================================
echo                         RealizeOS V5 - Uninstaller
echo ==============================================================================
echo.
echo This will remove RealizeOS from your system.
echo.

:: --------------------------------------------------------------------------
:: 3. Confirm Uninstall
:: --------------------------------------------------------------------------
:CONFIRM
set "CONFIRM="
set /p "CONFIRM=Are you sure you want to uninstall RealizeOS? (Y/N): "
if /I "!CONFIRM!"=="N" (
    echo.
    echo Uninstallation cancelled.
    pause
    exit /b
)
if /I not "!CONFIRM!"=="Y" (
    echo Please type Y or N.
    goto CONFIRM
)

:: --------------------------------------------------------------------------
:: 4. Ask About User Data
:: --------------------------------------------------------------------------
echo.
echo ------------------------------------------------------------------------------
echo USER DATA
echo ------------------------------------------------------------------------------
echo.
echo Your user data includes:
echo   - FABRIC knowledge files (systems/ directory)
echo   - Configuration (.env, realize-os.yaml)
echo   - Databases (activity logs, conversations)
echo   - Credentials (.credentials/ directory)
echo.
:DATA_PROMPT
set "KEEP_DATA="
set /p "KEEP_DATA=Do you want to KEEP your user data? (Y/N): "
if /I "!KEEP_DATA!"=="Y" (
    echo.
    echo [OK] User data will be preserved.
    set "PRESERVE=1"
) else if /I "!KEEP_DATA!"=="N" (
    echo.
    echo [!] All data will be permanently deleted.
    set "PRESERVE=0"
) else (
    echo Please type Y or N.
    goto DATA_PROMPT
)

:: --------------------------------------------------------------------------
:: 5. Detect Installation Directory
:: --------------------------------------------------------------------------
set "INSTALL_DIR=%~dp0"
:: Remove trailing backslash
if "!INSTALL_DIR:~-1!"=="\" set "INSTALL_DIR=!INSTALL_DIR:~0,-1!"

echo.
echo Uninstalling from: !INSTALL_DIR!
echo.

:: --------------------------------------------------------------------------
:: 6. Remove Desktop Shortcut
:: --------------------------------------------------------------------------
echo [1/4] Removing desktop shortcut...
set "SHORTCUT=!USERPROFILE!\Desktop\Start RealizeOS.lnk"
if exist "!SHORTCUT!" (
    del /f /q "!SHORTCUT!" 2>nul
    echo       [OK] Desktop shortcut removed.
) else (
    echo       [--] No desktop shortcut found.
)

:: --------------------------------------------------------------------------
:: 7. Stop Running Processes
:: --------------------------------------------------------------------------
echo.
echo [2/4] Stopping RealizeOS processes...
taskkill /f /fi "WINDOWTITLE eq RealizeOS*" >nul 2>&1
taskkill /f /fi "IMAGENAME eq pythonw.exe" /fi "WINDOWTITLE eq RealizeOS*" >nul 2>&1
echo       [OK] Processes stopped.

:: --------------------------------------------------------------------------
:: 8. Back Up User Data (if preserving)
:: --------------------------------------------------------------------------
echo.
echo [3/4] Processing user data...

if "!PRESERVE!"=="1" (
    set "BACKUP_DIR=!USERPROFILE!\RealizeOS-Backup"
    if not exist "!BACKUP_DIR!" mkdir "!BACKUP_DIR!"
    
    :: Back up user files
    if exist "!INSTALL_DIR!\systems" (
        xcopy /s /e /y /q "!INSTALL_DIR!\systems\*" "!BACKUP_DIR!\systems\" >nul 2>&1
        echo       [OK] FABRIC data backed up to !BACKUP_DIR!\systems\
    )
    if exist "!INSTALL_DIR!\.env" (
        copy /y "!INSTALL_DIR!\.env" "!BACKUP_DIR!\" >nul 2>&1
        echo       [OK] .env backed up.
    )
    if exist "!INSTALL_DIR!\realize-os.yaml" (
        copy /y "!INSTALL_DIR!\realize-os.yaml" "!BACKUP_DIR!\" >nul 2>&1
        echo       [OK] realize-os.yaml backed up.
    )
    if exist "!INSTALL_DIR!\.credentials" (
        xcopy /s /e /y /q "!INSTALL_DIR!\.credentials\*" "!BACKUP_DIR!\.credentials\" >nul 2>&1
        echo       [OK] Credentials backed up.
    )
    
    :: Back up databases
    for %%f in ("!INSTALL_DIR!\*.db" "!INSTALL_DIR!\*.sqlite" "!INSTALL_DIR!\*.sqlite3") do (
        if exist "%%f" (
            copy /y "%%f" "!BACKUP_DIR!\" >nul 2>&1
        )
    )
    echo       [OK] Databases backed up.
    echo.
    echo       Data saved to: !BACKUP_DIR!
) else (
    echo       [!] User data will be deleted.
)

:: --------------------------------------------------------------------------
:: 9. Remove Installation Directory
:: --------------------------------------------------------------------------
echo.
echo [4/4] Removing installation files...

:: We need to copy this script to temp and run removal from there
:: because we can't delete the directory while running from it
set "CLEANUP_SCRIPT=!TEMP!\realizeos-cleanup.bat"

(
echo @echo off
echo timeout /t 2 /nobreak ^>nul
echo rmdir /s /q "!INSTALL_DIR!" 2^>nul
echo if exist "!INSTALL_DIR!" (
echo     echo [WARNING] Could not fully remove !INSTALL_DIR!
echo     echo           Some files may be in use. Please delete manually.
echo ^) else (
echo     echo [OK] Installation directory removed.
echo ^)
echo echo.
echo echo ==============================================================================
echo echo                      UNINSTALLATION COMPLETE
echo echo ==============================================================================
echo echo.
if "!PRESERVE!"=="1" (
echo echo Your data has been saved to: !BACKUP_DIR!
echo echo You can use this data if you reinstall RealizeOS later.
) else (
echo echo All RealizeOS files have been removed from your system.
)
echo echo.
echo echo Press any key to close...
echo pause ^>nul
echo del /f /q "%%~f0" 2^>nul
) > "!CLEANUP_SCRIPT!"

echo       [OK] Cleanup scheduled.
echo.
color 0A
echo ==============================================================================
echo                        UNINSTALLATION IN PROGRESS
echo ==============================================================================
echo.
echo RealizeOS will be removed momentarily.
echo.

start "" cmd /c "!CLEANUP_SCRIPT!"
exit
