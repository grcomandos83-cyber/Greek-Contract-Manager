@echo off
setlocal
cd /d "%~dp0"

:: ============================================================================
:: Bootstrap Trampoline Launcher
:: Καθαρισμός όλων των μεταβλητών runtime του PyInstaller πριν την εκκίνηση
:: του νέου εκτελέσιμου για την πλήρη αποτροπή σφαλμάτων "Failed to load Python DLL".
:: ============================================================================

set _MEIPASS2=
set _MEIPASS=
set _PYI_APPLICATION_HOME_DIR=
set _PYI_ARCHIVE_FILE=
set _PYI_PARENT_PROCESS_LEVEL=
set PYTHONPATH=
set PYTHONHOME=
set PYINSTALLER_STRICT_UNPACK_PROCESS=
set PYINSTALLER_RESET_ENVIRONMENT=1

start "" "%~dp0ContractManager.exe" %*
endlocal
exit /b 0
