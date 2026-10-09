import urllib.request
import json
import os
import sys
import subprocess
import threading
from tkinter import messagebox
from constants import APP_VERSION, GITHUB_REPO

def check_for_updates(parent_window=None):
    """Ελέγχει το GitHub API για νέες εκδόσεις (tags)"""

    def _run_check():
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

                latest_version = data.get('tag_name')
                if latest_version and latest_version != APP_VERSION:
                    assets = data.get('assets', [])
                    download_url = None
                    for asset in assets:
                        if asset.get('name', '').endswith('.exe'):
                            download_url = asset.get('browser_download_url')
                            break

                    if download_url:
                        _prompt_update(parent_window, latest_version, download_url)
        except Exception as e:
            print(f"Update check failed: {e}")

    threading.Thread(target=_run_check, daemon=True).start()


def _prompt_update(parent_window, new_version, download_url):
    """Ρωτάει τον χρήστη αν θέλει να κάνει ενημέρωση"""
    if parent_window:
        def ask():
            msg = (f"Υπάρχει διαθέσιμη μια νέα έκδοση ({new_version}).\n"
                   f"Θέλετε να την κατεβάσετε και να εγκατασταθεί αυτόματα;")
            if messagebox.askyesno("Ενημέρωση Διαθέσιμη", msg, parent=parent_window):
                _download_and_apply(download_url)
        parent_window.after(0, ask)


def _download_and_apply(download_url):
    """Κατεβάζει το νέο .exe και δημιουργεί το script ενημέρωσης"""
    if not getattr(sys, 'frozen', False):
        messagebox.showinfo("Ενημέρωση", "Τρέχετε τον πηγαίο κώδικα (όχι .exe). Κάντε 'git pull' για ενημέρωση.")
        return

    # --- ΑΙΤΙΑ #2: Πάντα χρησιμοποιούμε sys.executable & os.path.abspath ---
    current_exe = os.path.abspath(sys.executable)
    exe_dir     = os.path.dirname(current_exe)
    exe_name    = os.path.basename(current_exe)
    new_exe     = current_exe + ".new"

    # --- ΑΙΤΙΑ #3: Έλεγχος δικαιωμάτων εγγραφής στον φάκελο ---
    if not os.access(exe_dir, os.W_OK):
        messagebox.showerror(
            "Σφάλμα Δικαιωμάτων",
            f"Δεν υπάρχουν δικαιώματα εγγραφής στον φάκελο:\n{exe_dir}\n\n"
            "Μετακινήστε την εφαρμογή σε έναν προσωπικό φάκελο (π.χ. Έγγραφα ή Desktop) "
            "και δοκιμάστε ξανά."
        )
        return

    # --- Λήψη νέου .exe ---
    try:
        urllib.request.urlretrieve(download_url, new_exe)
    except Exception as e:
        messagebox.showerror("Σφάλμα Λήψης", f"Αποτυχία λήψης νέας έκδοσης:\n{e}")
        return

    # --- ΑΙΤΙΑ #1 & #3: Δημιουργία .bat με ANSI (cp1253 για Windows/Ελληνικά) ---
    # Χρησιμοποιούμε %~1, %~2 (ορίσματα) αντί για hardcoded paths μέσα στο .bat,
    # ώστε να αποφύγουμε παντελώς το πρόβλημα κωδικοποίησης των ελληνικών χαρακτήρων.
    bat_path = os.path.join(exe_dir, "updater.bat")

    # ΑΙΤΙΑ #4: Χρησιμοποιούμε 'start "" "..."' αντί για explorer.exe
    # ΑΙΤΙΑ #5: Loop 10 φορών για να περιμένει να ξεκλειδώσει το παλιό .exe
    # ΑΙΤΙΑ #7: Logging σε %TEMP%\cm_update.log
    bat_content = """\
@echo off
chcp 65001 >nul 2>&1
setlocal

:: Ορίσματα: %1 = current_exe, %2 = new_exe
set "CURRENT_EXE=%~1"
set "NEW_EXE=%~2"
set "LOG=%TEMP%\\cm_update.log"

echo [%DATE% %TIME%] === Auto-update started === >> "%LOG%"
echo [%DATE% %TIME%] CURRENT_EXE: %CURRENT_EXE% >> "%LOG%"
echo [%DATE% %TIME%] NEW_EXE:     %NEW_EXE% >> "%LOG%"

:: Αναμονή για να κλείσει η παλιά εφαρμογή
timeout /t 3 /nobreak >nul

:: --- ΑΙΤΙΑ #5: Επαναληπτική διαγραφή μέχρι να ξεκλειδώσει το αρχείο ---
set /a TRIES=0
:DELETE_LOOP
del /f /q "%CURRENT_EXE%" >nul 2>&1
if exist "%CURRENT_EXE%" (
    set /a TRIES+=1
    if %TRIES% LSS 10 (
        echo [%DATE% %TIME%] Waiting for lock, attempt %TRIES%... >> "%LOG%"
        timeout /t 2 /nobreak >nul
        goto DELETE_LOOP
    ) else (
        echo [%DATE% %TIME%] ERROR: Could not delete old exe after 10 attempts. >> "%LOG%"
        goto CLEANUP
    )
)
echo [%DATE% %TIME%] Old exe deleted OK. >> "%LOG%"

:: --- Μετακίνηση νέου .exe στη θέση του παλιού ---
move /y "%NEW_EXE%" "%CURRENT_EXE%" >nul 2>&1
if not exist "%CURRENT_EXE%" (
    echo [%DATE% %TIME%] ERROR: move failed, new exe not found at destination. >> "%LOG%"
    goto CLEANUP
)
echo [%DATE% %TIME%] New exe moved OK. >> "%LOG%"

:: --- ΑΙΤΙΑ #8: Επαλήθευση ύπαρξης πριν την εκκίνηση ---
if not exist "%CURRENT_EXE%" (
    echo [%DATE% %TIME%] ERROR: new exe missing before launch. >> "%LOG%"
    goto CLEANUP
)

:: --- ΑΙΤΙΑ #4: Εκκίνηση με start και κενό τίτλο, ΟΧΙ explorer ---
echo [%DATE% %TIME%] Launching new exe... >> "%LOG%"
start "" "%CURRENT_EXE%"
echo [%DATE% %TIME%] Launch command issued OK. >> "%LOG%"

:CLEANUP
echo [%DATE% %TIME%] === Auto-update finished === >> "%LOG%"
endlocal
del "%~f0"
"""

    # --- ΑΙΤΙΑ #1: Γράφουμε το .bat με utf-8-sig ---
    # Το CMD των Windows διαβάζει σωστά UTF-8 αφού τρέξουμε chcp 65001.
    # Οι διαδρομές περνιούνται ως ορίσματα (εκτός bat), άρα δεν εξαρτόμαστε
    # από την κωδικοποίηση του αρχείου για τα paths.
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
    except Exception as e:
        messagebox.showerror("Σφάλμα", f"Αποτυχία δημιουργίας script ενημέρωσης:\n{e}")
        return

    # --- ΣΗΜΑΝΤΙΚΟ: Καθαρισμός _MEIPASS από το περιβάλλον (DLL fix) ---
    env = os.environ.copy()
    env.pop('_MEIPASS2', None)
    env.pop('_MEIPASS', None)
    for key in list(env.keys()):
        if key.startswith('_PYI_'):
            env.pop(key, None)

    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        path_env = env.get('PATH', '')
        paths = [p for p in path_env.split(os.pathsep) if p != meipass]
        env['PATH'] = os.pathsep.join(paths)

    # Περνάμε τις διαδρομές ΩΣ ΟΡΙΣΜΑΤΑ στο bat για να αποφύγουμε encoding issues
    subprocess.Popen(
        f'cmd /c "{bat_path}" "{current_exe}" "{new_exe}"',
        shell=False,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    sys.exit(0)
