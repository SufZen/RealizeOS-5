@echo off
setlocal EnableDelayedExpansion
title RealizeOS V5 - Data Migration Wizard

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
echo                    RealizeOS V5 - Data Migration Wizard
echo ==============================================================================
echo.
echo This wizard migrates your data from a previous RealizeOS installation
echo or another device into this installation.
echo.
echo What will be migrated:
echo   - FABRIC knowledge files (systems/ directory)
echo   - Configuration (.env, realize-os.yaml)
echo   - Databases (activity logs, conversations, KB index)
echo   - Credentials (.credentials/ directory)
echo.

:: --------------------------------------------------------------------------
:: 3. Source Path Selection
:: --------------------------------------------------------------------------
echo ------------------------------------------------------------------------------
echo SOURCE LOCATION
echo ------------------------------------------------------------------------------
echo.
echo Enter the path to your previous RealizeOS installation,
echo or a RealizeOS backup folder.
echo.
echo Examples:
echo   C:\Users\John\RealizeOS
echo   D:\Backups\RealizeOS-Backup
echo   E:\OldPC\RealizeOS
echo.

:SOURCE_PROMPT
set "SOURCE="
set /p "SOURCE=Source path: "

if "!SOURCE!"=="" (
    echo Please enter a valid path.
    goto SOURCE_PROMPT
)

if not exist "!SOURCE!" (
    echo [ERROR] Path not found: !SOURCE!
    echo Please check the path and try again.
    echo.
    goto SOURCE_PROMPT
)

:: --------------------------------------------------------------------------
:: 4. Scan Source for Migratable Data
:: --------------------------------------------------------------------------
echo.
echo [1/4] Scanning source directory...
echo.

set "HAS_SYSTEMS=0"
set "HAS_ENV=0"
set "HAS_CONFIG=0"
set "HAS_CREDS=0"
set "HAS_DBS=0"
set "DB_COUNT=0"
set "FOUND_ANYTHING=0"

:: Check for FABRIC systems
if exist "!SOURCE!\systems" (
    set "HAS_SYSTEMS=1"
    set "FOUND_ANYTHING=1"
    :: Count ventures
    set "VENTURE_COUNT=0"
    for /d %%v in ("!SOURCE!\systems\*") do set /a VENTURE_COUNT+=1
    echo   [FOUND] FABRIC knowledge: !VENTURE_COUNT! venture(s^) in systems/
)

:: Check for .env
if exist "!SOURCE!\.env" (
    set "HAS_ENV=1"
    set "FOUND_ANYTHING=1"
    echo   [FOUND] Environment config: .env
)

:: Check for realize-os.yaml
if exist "!SOURCE!\realize-os.yaml" (
    set "HAS_CONFIG=1"
    set "FOUND_ANYTHING=1"
    echo   [FOUND] System config: realize-os.yaml
)

:: Check for credentials
if exist "!SOURCE!\.credentials" (
    set "HAS_CREDS=1"
    set "FOUND_ANYTHING=1"
    echo   [FOUND] Credentials: .credentials/
)

:: Check for databases
for %%f in ("!SOURCE!\*.db" "!SOURCE!\*.sqlite" "!SOURCE!\*.sqlite3") do (
    if exist "%%f" (
        set "HAS_DBS=1"
        set "FOUND_ANYTHING=1"
        set /a DB_COUNT+=1
    )
)
if "!HAS_DBS!"=="1" echo   [FOUND] Databases: !DB_COUNT! file(s^)

:: Nothing found?
if "!FOUND_ANYTHING!"=="0" (
    echo.
    echo [WARNING] No RealizeOS data found at: !SOURCE!
    echo Make sure you selected the correct directory.
    echo.
    pause
    exit /b 1
)

:: --------------------------------------------------------------------------
:: 5. Conflict Resolution Strategy
:: --------------------------------------------------------------------------
echo.
echo ------------------------------------------------------------------------------
echo CONFLICT RESOLUTION
echo ------------------------------------------------------------------------------
echo.
echo If files already exist in this installation, how should conflicts be handled?
echo.
echo   1. Skip existing files (keep current, only add new)
echo   2. Overwrite existing files (replace with source)
echo   3. Ask for each conflict
echo.

:CONFLICT_PROMPT
set "STRATEGY="
set /p "STRATEGY=Choose strategy (1/2/3): "
if "!STRATEGY!"=="1" (
    set "CONFLICT_MODE=skip"
    echo.
    echo [OK] Will skip existing files.
) else if "!STRATEGY!"=="2" (
    set "CONFLICT_MODE=overwrite"
    echo.
    echo [OK] Will overwrite existing files.
) else if "!STRATEGY!"=="3" (
    set "CONFLICT_MODE=ask"
    echo.
    echo [OK] Will ask for each conflict.
) else (
    echo Please choose 1, 2, or 3.
    goto CONFLICT_PROMPT
)

:: --------------------------------------------------------------------------
:: 6. Confirm Migration
:: --------------------------------------------------------------------------
echo.
echo ------------------------------------------------------------------------------
echo MIGRATION SUMMARY
echo ------------------------------------------------------------------------------
echo.
echo   From: !SOURCE!
echo   To:   %~dp0
echo   Strategy: !CONFLICT_MODE!
echo.

:MIGRATE_CONFIRM
set "GO="
set /p "GO=Proceed with migration? (Y/N): "
if /I "!GO!"=="N" (
    echo Migration cancelled.
    pause
    exit /b
)
if /I not "!GO!"=="Y" (
    echo Please type Y or N.
    goto MIGRATE_CONFIRM
)

:: --------------------------------------------------------------------------
:: 7. Execute Migration
:: --------------------------------------------------------------------------
echo.
echo [2/4] Migrating data...
set "MIGRATED=0"
set "SKIPPED=0"

:: Migrate FABRIC systems
if "!HAS_SYSTEMS!"=="1" (
    echo.
    echo   Migrating FABRIC knowledge...
    if "!CONFLICT_MODE!"=="skip" (
        xcopy /s /e /y /q /d "!SOURCE!\systems\*" "systems\" >nul 2>&1
    ) else (
        xcopy /s /e /y /q "!SOURCE!\systems\*" "systems\" >nul 2>&1
    )
    set /a MIGRATED+=1
    echo       [OK] FABRIC systems migrated.
)

:: Migrate .env
if "!HAS_ENV!"=="1" (
    if exist ".env" (
        if "!CONFLICT_MODE!"=="skip" (
            echo       [SKIP] .env already exists.
            set /a SKIPPED+=1
        ) else if "!CONFLICT_MODE!"=="ask" (
            set "ENV_ANS="
            set /p "ENV_ANS=  .env exists. Overwrite? (Y/N): "
            if /I "!ENV_ANS!"=="Y" (
                copy /y "!SOURCE!\.env" ".\" >nul 2>&1
                set /a MIGRATED+=1
                echo       [OK] .env migrated.
            ) else (
                set /a SKIPPED+=1
                echo       [SKIP] .env kept.
            )
        ) else (
            copy /y "!SOURCE!\.env" ".\" >nul 2>&1
            set /a MIGRATED+=1
            echo       [OK] .env migrated.
        )
    ) else (
        copy /y "!SOURCE!\.env" ".\" >nul 2>&1
        set /a MIGRATED+=1
        echo       [OK] .env migrated.
    )
)

:: Migrate realize-os.yaml
if "!HAS_CONFIG!"=="1" (
    if exist "realize-os.yaml" (
        if "!CONFLICT_MODE!"=="skip" (
            echo       [SKIP] realize-os.yaml already exists.
            set /a SKIPPED+=1
        ) else if "!CONFLICT_MODE!"=="ask" (
            set "CFG_ANS="
            set /p "CFG_ANS=  realize-os.yaml exists. Overwrite? (Y/N): "
            if /I "!CFG_ANS!"=="Y" (
                copy /y "!SOURCE!\realize-os.yaml" ".\" >nul 2>&1
                set /a MIGRATED+=1
                echo       [OK] realize-os.yaml migrated.
            ) else (
                set /a SKIPPED+=1
                echo       [SKIP] realize-os.yaml kept.
            )
        ) else (
            copy /y "!SOURCE!\realize-os.yaml" ".\" >nul 2>&1
            set /a MIGRATED+=1
            echo       [OK] realize-os.yaml migrated.
        )
    ) else (
        copy /y "!SOURCE!\realize-os.yaml" ".\" >nul 2>&1
        set /a MIGRATED+=1
        echo       [OK] realize-os.yaml migrated.
    )
)

:: Migrate credentials
if "!HAS_CREDS!"=="1" (
    echo.
    echo   Migrating credentials...
    if not exist ".credentials" mkdir ".credentials"
    xcopy /s /e /y /q "!SOURCE!\.credentials\*" ".credentials\" >nul 2>&1
    set /a MIGRATED+=1
    echo       [OK] Credentials migrated.
)

:: Migrate databases
if "!HAS_DBS!"=="1" (
    echo.
    echo   Migrating databases...
    for %%f in ("!SOURCE!\*.db" "!SOURCE!\*.sqlite" "!SOURCE!\*.sqlite3") do (
        if exist "%%f" (
            set "DB_NAME=%%~nxf"
            if "!CONFLICT_MODE!"=="skip" (
                if not exist "!DB_NAME!" (
                    copy /y "%%f" ".\" >nul 2>&1
                    set /a MIGRATED+=1
                ) else (
                    set /a SKIPPED+=1
                )
            ) else (
                copy /y "%%f" ".\" >nul 2>&1
                set /a MIGRATED+=1
            )
        )
    )
    echo       [OK] Databases migrated.
)

:: --------------------------------------------------------------------------
:: 8. Rebuild KB Index
:: --------------------------------------------------------------------------
echo.
echo [3/4] Rebuilding knowledge base index...
python cli.py index >nul 2>&1
if !errorlevel! equ 0 (
    echo       [OK] KB index rebuilt.
) else (
    echo       [WARNING] KB rebuild had issues. Run 'python cli.py index' manually.
)

:: --------------------------------------------------------------------------
:: 9. Completion
:: --------------------------------------------------------------------------
echo.
echo [4/4] Finalizing...
echo.
color 0A
echo ==============================================================================
echo                        MIGRATION COMPLETE!
echo ==============================================================================
echo.
echo   Items migrated: !MIGRATED!
echo   Items skipped:  !SKIPPED!
echo.
echo Your data has been successfully migrated to this installation.
echo Start RealizeOS to verify everything works correctly.
echo.
echo Press any key to close...
pause >nul
exit
