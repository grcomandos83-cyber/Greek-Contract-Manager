import urllib.request
import json
import os
import sys
import subprocess
import threading
import tempfile
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
                    is_installer = False

                    # Προτεραιότητα 1: Inno Setup Installer (ContractManager_Setup.exe)
                    for asset in assets:
                        name = asset.get('name', '').lower()
                        if 'setup' in name and name.endswith('.exe'):
                            download_url = asset.get('browser_download_url')
                            is_installer = True
                            break

                    # Προτεραιότητα 2: Standalone .exe (π.χ. ContractManager.exe)
                    if not download_url:
                        for asset in assets:
                            if asset.get('name', '').endswith('.exe'):
                                download_url = asset.get('browser_download_url')
                                is_installer = False
                                break

                    if download_url:
                        _prompt_update(parent_window, latest_version, download_url, is_installer)
        except Exception as e:
            print(f"Update check failed: {e}")

    threading.Thread(target=_run_check, daemon=True).start()


def _prompt_update(parent_window, new_version, download_url, is_installer=True):
    """Ρωτάει τον χρήστη αν θέλει να κάνει ενημέρωση"""
    if parent_window:
        def ask():
            msg = (f"Υπάρχει διαθέσιμη μια νέα έκδοση ({new_version}).\n"
                   f"Θέλετε να την κατεβάσετε και να εγκατασταθεί αυτόματα;")
            if messagebox.askyesno("Ενημέρωση Διαθέσιμη", msg, parent=parent_window):
                _download_and_apply(download_url, is_installer)
        parent_window.after(0, ask)


def _download_and_apply(download_url, is_installer=True):
    """Κατεβάζει το νέο .exe και εφαρμόζει την ενημέρωση"""
    if not getattr(sys, 'frozen', False):
        messagebox.showinfo("Ενημέρωση", "Τρέχετε τον πηγαίο κώδικα (όχι .exe). Κάντε 'git pull' για ενημέρωση.")
        return

    # --- Μέθοδος Inno Setup Installer: Ασφαλής, αθόρυβη & αξιόπιστη εκτέλεση ---
    if is_installer:
        temp_dir = tempfile.gettempdir()
        setup_exe = os.path.join(temp_dir, f"ContractManager_Setup_{os.getpid()}.exe")

        try:
            urllib.request.urlretrieve(download_url, setup_exe)
        except Exception as e:
            messagebox.showerror("Σφάλμα Λήψης", f"Αποτυχία λήψης νέας έκδοσης:\n{e}")
            return

        try:
            DETACHED_PROCESS = 0x00000008
            flags = DETACHED_PROCESS
            if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                flags |= subprocess.CREATE_NO_WINDOW

            subprocess.Popen(
                [setup_exe, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
                creationflags=flags,
                close_fds=True
            )
            sys.exit(0)
        except Exception as e:
            messagebox.showerror("Σφάλμα Εγκατάστασης", f"Αποτυχία εκτέλεσης εγκαταστάτη:\n{e}")
            return

    # --- Fallback για Standalone .exe (αν δεν βρεθεί Installer) ---
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

    # -------------------------------------------------------------------------
    # Build the .bat file
    # -------------------------------------------------------------------------
    bat_path = os.path.join(exe_dir, "updater.bat")

    # FIX-A: Pure ASCII content — no chcp, no Greek comments, no goto labels
    # with non-ASCII chars. Paths are passed as %~1/%~2 arguments so the file's
    # own encoding never touches the paths.
    # FIX-A (wait): "ping 127.0.0.1 -n N" is used instead of "timeout /t N"
    # because timeout requires an attached console; with CREATE_NO_WINDOW there
    # is no console and timeout exits immediately (returns error), so the retry
    # loop would spin without actually waiting.
    bat_content = (
        "@echo off\r\n"
        "setlocal\r\n"
        "\r\n"
        "rem --- Arguments: %1 = current exe, %2 = new exe ---\r\n"
        'set "CURRENT_EXE=%~1"\r\n'
        'set "NEW_EXE=%~2"\r\n'
        'set "LOG=%TEMP%\\cm_update.log"\r\n'
        "\r\n"
        "echo [%DATE% %TIME%] === Auto-update started === >> \"%LOG%\"\r\n"
        "echo [%DATE% %TIME%] CURRENT_EXE: %CURRENT_EXE% >> \"%LOG%\"\r\n"
        "echo [%DATE% %TIME%] NEW_EXE:     %NEW_EXE% >> \"%LOG%\"\r\n"
        "\r\n"
        "rem --- Initial wait: 3 pings = ~3 s, works without a console window ---\r\n"
        "ping 127.0.0.1 -n 4 >nul\r\n"
        "\r\n"
        "rem --- Delete old exe with up to 15 retries (~2 s each) ---\r\n"
        "set /a TRIES=0\r\n"
        ":DEL_LOOP\r\n"
        "del /f /q \"%CURRENT_EXE%\" >nul 2>&1\r\n"
        "if exist \"%CURRENT_EXE%\" (\r\n"
        "    set /a TRIES+=1\r\n"
        "    if %TRIES% LSS 15 (\r\n"
        "        echo [%DATE% %TIME%] Lock wait attempt %TRIES% >> \"%LOG%\"\r\n"
        "        ping 127.0.0.1 -n 3 >nul\r\n"
        "        goto DEL_LOOP\r\n"
        "    ) else (\r\n"
        "        echo [%DATE% %TIME%] ERROR: could not delete old exe >> \"%LOG%\"\r\n"
        "        goto DONE\r\n"
        "    )\r\n"
        ")\r\n"
        "echo [%DATE% %TIME%] Old exe deleted >> \"%LOG%\"\r\n"
        "\r\n"
        "rem --- Move new exe into place ---\r\n"
        "move /y \"%NEW_EXE%\" \"%CURRENT_EXE%\" >> \"%LOG%\" 2>&1\r\n"
        "if not exist \"%CURRENT_EXE%\" (\r\n"
        "    echo [%DATE% %TIME%] ERROR: move failed >> \"%LOG%\"\r\n"
        "    goto DONE\r\n"
        ")\r\n"
        "echo [%DATE% %TIME%] New exe in place >> \"%LOG%\"\r\n"
        "\r\n"
        "rem --- FIX-A (verify): check the new exe exists before launching ---\r\n"
        "if not exist \"%CURRENT_EXE%\" (\r\n"
        "    echo [%DATE% %TIME%] ERROR: exe missing before launch >> \"%LOG%\"\r\n"
        "    goto DONE\r\n"
        ")\r\n"
        "\r\n"
        "rem --- Launch: 'start \"\" ...' with empty title, NOT explorer.exe ---\r\n"
        "echo [%DATE% %TIME%] Launching... >> \"%LOG%\"\r\n"
        'start "" "%CURRENT_EXE%"\r\n'
        "echo [%DATE% %TIME%] Launch issued >> \"%LOG%\"\r\n"
        "\r\n"
        ":DONE\r\n"
        "echo [%DATE% %TIME%] === Auto-update finished === >> \"%LOG%\"\r\n"
        "endlocal\r\n"
        # Self-delete that works even when the bat is the running process
        "(goto) 2>nul & del \"%~f0\"\r\n"
    )

    # FIX-A: Write as pure ASCII with explicit CRLF line endings
    try:
        with open(bat_path, "w", encoding="ascii", newline="\r\n") as f:
            f.write(bat_content)
    except Exception as e:
        messagebox.showerror("Σφάλμα", f"Αποτυχία δημιουργίας script ενημέρωσης:\n{e}")
        return

    # -------------------------------------------------------------------------
    # Build a clean environment for the bat / new exe
    # -------------------------------------------------------------------------
    # FIX-B: Remove _MEIPASS / _MEIPASS2 / _PYI_* variables (case-insensitive).
    # These point to the temp folder of the *current* frozen process. If the new
    # exe inherits them it tries to load DLLs from a folder that no longer exists
    # once the old process exits → "Failed to load Python DLL" crash.
    env = {}
    for k, v in os.environ.items():
        ku = k.upper()
        if ku.startswith("_MEI") or ku.startswith("_PYI_"):
            continue
        env[k] = v

    # FIX-B: Tell PyInstaller 6.9+ to reset its internal state on next start
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

    # FIX-B: Remove any PATH entries that live inside the current _MEIPASS dir.
    # Use normcase+abspath so that case and trailing-slash differences don't matter.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        norm_meipass = os.path.normcase(os.path.abspath(meipass))
        path_parts = env.get("PATH", "").split(os.pathsep)
        filtered = [
            p for p in path_parts
            if not os.path.normcase(os.path.abspath(p)).startswith(norm_meipass)
        ]
        env["PATH"] = os.pathsep.join(filtered)

    # -------------------------------------------------------------------------
    # Launch the bat and exit
    # -------------------------------------------------------------------------
    # FIX-C: cmd /d /s /c "..."  — the outer double-quotes are stripped by cmd
    # itself (that is what /s does), so the inner "bat" "arg1" "arg2" are parsed
    # correctly even when paths contain spaces or non-ASCII characters.
    cmdline = f'cmd.exe /d /s /c ""{bat_path}" "{current_exe}" "{new_exe}""'

    # FIX-D: DETACHED_PROCESS (0x8) lets the bat keep running after this process
    # exits. CREATE_NO_WINDOW hides the console. cwd=exe_dir avoids inheriting a
    # random working directory from explorer or a parent process.
    DETACHED_PROCESS = 0x00000008
    subprocess.Popen(
        cmdline,
        shell=False,
        env=env,
        cwd=exe_dir,
        creationflags=subprocess.CREATE_NO_WINDOW | DETACHED_PROCESS,
        close_fds=True,
    )
    sys.exit(0)
