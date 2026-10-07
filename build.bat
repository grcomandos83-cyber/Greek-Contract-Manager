@echo off
REM =========================================================================
REM Build script for Contract Manager Application
REM Uses PyInstaller to create a standalone executable
REM =========================================================================

echo ========================================
echo Contract Manager - Build Script
echo ========================================
echo.

REM Check if PyInstaller is installed
python -m pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
    if %errorlevel% neq 0 (
        echo Failed to install PyInstaller. Please install it manually.
        pause
        exit /b 1
    )
)

echo Building executable...
echo.

REM Clean previous builds
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "*.spec" del /q "*.spec"

REM Build the executable
pyinstaller --name="ContractManager" ^
    --onefile ^
    --windowed ^
    --icon="assets\app.ico" ^
    --add-data "assets;assets" ^
    --add-data "contract_pdfs;contract_pdfs" ^
    --add-data "backups;backups" ^
    --hidden-import=customtkinter ^
    --hidden-import=tkcalendar ^
    --hidden-import=dateutil ^
    --hidden-import=PIL ^
    --hidden-import=babel.numbers ^
    --collect-all customtkinter ^
    --collect-all tkcalendar ^
    contract_manager.py

if %errorlevel% neq 0 (
    echo.
    echo Build failed! Please check the error messages above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.

REM Copy README to the output folder
copy "README.md" "dist\" >nul

echo Executable location: dist\ContractManager.exe
echo.
echo Note: The README.md file has been automatically copied to the dist folder.
echo.
echo Note: You may also want to copy the following data files/folders to the dist directory:
echo   - contracts.db (if it exists)
echo   - settings.json (if it exists)
echo   - contract_pdfs folder
echo   - backups folder
echo.
pause
