@echo off
setlocal
cd /d "%~dp0"

rem =========================================================================
rem Contract Manager Launcher
rem Strips PyInstaller environment variables before launching the executable
rem to prevent "Failed to load Python DLL" errors during updates/restarts.
rem =========================================================================

set _MEIPASS2=
set _MEIPASS=
set _PYI_APPLICATION_HOME_DIR=
set _PYI_ARCHIVE_FILE=
set _PYI_SPLASH_IPC=
set PYINSTALLER_RESET_ENVIRONMENT=1

start "" "%~dp0ContractManager.exe" %*
endlocal
