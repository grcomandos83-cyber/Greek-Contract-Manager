"""
updater.py - Υβριδικός & Απόλυτα Ασφαλής Μηχανισμός Auto-Update για Windows.

Χαρακτηριστικά Ασφαλείας & Εγγυημένης Επανεκκίνησης:
1. Background Checking χωρίς πάγωμα του GUI.
2. Σημασιολογική σύγκριση εκδόσεων με packaging.version.Version (αγνοώντας 'v').
3. Αυτόματος εντοπισμός installer (.exe με setup/install) από τα assets.
4. Ασύγχρονη λήψη σε chunks (64 KB) σε ασφαλή tempfile.mkdtemp.
5. UI Throttling (~40ms / 25fps) για αποφυγή συμφόρησης του Event Loop.
6. Υπολογισμός πραγματικής στιγμιαίας ταχύτητας (MB/s) και ποσοστού λήψης.
7. Safe Cancellation με άμεσο κλείσιμο socket και διαγραφή ημιτελών αρχείων.
8. Safe Delay Trampoline Runner (update_runner.bat):
   - Αναμονή 2 δευτερολέπτων για πλήρη απελευθέρωση file handles/DLLs από τα Windows.
   - Εκτέλεση Inno Setup με /VERYSILENT /SUPPRESSMSGBOXES /FORCECLOSEAPPLICATIONS /DIR="<app_dir>".
   - Καθαρισμός os.environ (_MEIPASS, _PYI*, PYINSTALLER*, PYTHONPATH, PYTHONHOME).
   - Εγγυημένη επανεκκίνηση της νέας έκδοσης με launcher.bat.
   - Υποστήριξη chcp 65001 για ελληνικά μονοπάτια φακέλων (Unicode paths).
"""

import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
import threading
import urllib.request
import urllib.error
import re
from typing import Optional, Dict, Any

# Σημασιολογική σύγκριση εκδόσεων
try:
    from packaging.version import Version, InvalidVersion
    HAS_PACKAGING = True
except ImportError:
    HAS_PACKAGING = False
    Version = None
    InvalidVersion = Exception

# Ανάκτηση στοιχείων έκδοσης και αποθετηρίου
try:
    from version import __version__, GITHUB_REPO
except ImportError:
    try:
        from constants import APP_VERSION as __version__, GITHUB_REPO
    except ImportError:
        __version__ = "1.0.30"
        GITHUB_REPO = "grcomandos83-cyber/Greek-Contract-Manager"


# =========================================================================
# 1. Βοηθητικές Συναρτήσεις Σύγκρισης Εκδόσεων & Εντοπισμού Assets
# =========================================================================

def normalize_version_string(v_str: str) -> str:
    """Καθαρίζει το string της έκδοσης από προθέματα τύπου 'v' ή 'V' και κενά."""
    if not v_str:
        return "0.0.0"
    cleaned = str(v_str).strip()
    if cleaned.lower().startswith('v'):
        cleaned = cleaned[1:].strip()
    return cleaned


def is_newer_version(latest_tag: str, current_ver: str) -> bool:
    """
    Ελέγχει αν το latest_tag είναι αυστηρά νεότερο από το current_ver.
    Χρησιμοποιεί τη βιβλιοθήκη packaging.version.Version με fallback σε parsing ακεραίων.
    """
    latest_clean = normalize_version_string(latest_tag)
    current_clean = normalize_version_string(current_ver)

    if HAS_PACKAGING:
        try:
            return Version(latest_clean) > Version(current_clean)
        except InvalidVersion:
            pass

    def parse_tuple(v):
        nums = re.findall(r'\d+', v)
        return tuple(int(n) for n in nums) if nums else (0,)

    return parse_tuple(latest_clean) > parse_tuple(current_clean)


def find_installer_asset(assets: list) -> Optional[Dict[str, Any]]:
    """
    Εντοπίζει αυτόματα το αρχείο εγκατάστασης (.exe) από τη λίστα assets.
    Αναζητά αρχεία .exe που περιέχουν τις λέξεις 'setup' ή 'install'.
    """
    if not assets:
        return None

    candidates = []
    for asset in assets:
        name = asset.get("name", "").lower()
        if name.endswith(".exe") and ("setup" in name or "install" in name):
            candidates.append(asset)

    if candidates:
        for c in candidates:
            if "latest" in c.get("name", "").lower():
                return c
        return candidates[0]

    for asset in assets:
        if asset.get("name", "").lower().endswith(".exe"):
            return asset

    return None


def sanitize_and_launch_installer(installer_path: str, parent=None):
    """
    Εκκινεί τον Inno Setup Installer μέσω ενός εξωτερικού Trampoline Runner Script
    με πλήρη καθαρισμό περιβάλλοντος, εγγυημένο delay για απελευθέρωση file locks
    και αυτόματη επανεκκίνηση της νέας έκδοσης.
    """
    if not os.path.exists(installer_path):
        raise FileNotFoundError(f"Δεν βρέθηκε το αρχείο εγκατάστασης: {installer_path}")

    # Έλεγχος μεγέθους αρχείου: πρέπει να είναι έγκυρος installer (> 1 MB)
    if os.path.getsize(installer_path) < 1024 * 1024:
        raise ValueError("Το αρχείο εγκατάστασης που λήφθηκε φαίνεται κατεστραμμένο ή ημιτελές.")

    # 1. Έλεγχος αν τρέχουμε σε περιβάλλον ανάπτυξης (πηγαίος κώδικας .py)
    if not getattr(sys, 'frozen', False):
        from tkinter import messagebox
        file_size_mb = os.path.getsize(installer_path) / (1024 * 1024)
        messagebox.showinfo(
            "Λειτουργία Ανάπτυξης",
            f"Η δοκιμαστική λήψη ολοκληρώθηκε επιτυχώς ({file_size_mb:.1f} MB)!\n\n"
            "Επειδή εκτελείτε την εφαρμογή από πηγαίο κώδικα Python (όχι από .exe), "
            "η αυτόματη εγκατάσταση παρακάμπτεται για λόγους ασφαλείας.",
            parent=parent
        )
        try:
            if os.path.exists(installer_path):
                os.remove(installer_path)
        except Exception:
            pass
        return

    # 2. Προσδιορισμός διαδρομών της τρέχουσας εκτελέσιμης εφαρμογής
    app_exe = os.path.abspath(sys.executable)
    app_dir = os.path.dirname(app_exe)
    norm_installer = os.path.abspath(installer_path)

    # 3. Δημιουργία Trampoline Runner Script στο %TEMP% με υποστήριξη UTF-8 (chcp 65001)
    runner_bat_path = os.path.join(tempfile.gettempdir(), f"cm_updater_{os.getpid()}.bat")

    bat_content = (
        "@echo off\r\n"
        "chcp 65001 >nul 2>&1\r\n"
        "setlocal\r\n"
        "\r\n"
        "rem =========================================================================\r\n"
        "rem Greek Contract Manager Auto-Update Runner\r\n"
        "rem =========================================================================\r\n"
        "\r\n"
        "rem 1. Αναμονή 2 δευτερολέπτων για να τερματίσει πλήρως η παλιά εφαρμογή\r\n"
        "ping 127.0.0.1 -n 3 >nul 2>&1\r\n"
        "\r\n"
        "rem 2. Εκτέλεση του Inno Setup Installer με ακριβή προορισμό τον φάκελο της εφαρμογής\r\n"
        f'"{norm_installer}" /VERYSILENT /SUPPRESSMSGBOXES /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /NORESTART /DIR="{app_dir}"\r\n'
        "\r\n"
        "rem 3. Αναμονή 1.5 δευτερολέπτου για ολοκλήρωση της αντικατάστασης των αρχείων\r\n"
        "ping 127.0.0.1 -n 3 >nul 2>&1\r\n"
        "\r\n"
        "rem 4. Καθαρισμός μεταβλητών PyInstaller πριν την επανεκκίνηση\r\n"
        "set _MEIPASS2=\r\n"
        "set _MEIPASS=\r\n"
        "set _PYI_APPLICATION_HOME_DIR=\r\n"
        "set _PYI_ARCHIVE_FILE=\r\n"
        "set _PYI_PARENT_PROCESS_LEVEL=\r\n"
        "set PYTHONPATH=\r\n"
        "set PYTHONHOME=\r\n"
        "set PYINSTALLER_STRICT_UNPACK_PROCESS=\r\n"
        "set PYINSTALLER_RESET_ENVIRONMENT=1\r\n"
        "\r\n"
        "rem 5. Εγγυημένη επανεκκίνηση της εφαρμογής στον σωστό φάκελο\r\n"
        f'cd /d "{app_dir}"\r\n'
        f'if exist "{app_dir}\\launcher.bat" (\r\n'
        f'    start "" "{app_dir}\\launcher.bat"\r\n'
        f') else if exist "{app_exe}" (\r\n'
        f'    start "" "{app_exe}"\r\n'
        f')\r\n'
        "\r\n"
        "rem 6. Αυτοκαταστροφή του προσωρινού runner script\r\n"
        '(goto) 2>nul & del "%~f0"\r\n'
    )

    with open(runner_bat_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(bat_content)

    # 4. Καθαρισμός os.environ για τη νέα διεργασία
    clean_env = os.environ.copy()
    for key in list(clean_env.keys()):
        if key.startswith(("_MEI", "_PYI", "PYINSTALLER")) or key in ("PYTHONPATH", "PYTHONHOME"):
            clean_env.pop(key, None)
    clean_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000

    # 5. Εκτέλεση του Trampoline Runner αποσυνδεδεμένου (Detached)
    subprocess.Popen(
        f'cmd.exe /d /c ""{runner_bat_path}""',
        env=clean_env,
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        cwd=tempfile.gettempdir(),
        close_fds=True
    )

    # 6. Κλείσιμο παραθύρου και ακαριαίος τερματισμός (απελευθέρωση handles & DLLs)
    if parent is not None and hasattr(parent, "destroy"):
        try:
            parent.destroy()
        except Exception:
            pass

    os._exit(0)


# =========================================================================
# 2. CustomTkinter / Tkinter Implementation
# =========================================================================

def _is_tk_or_ctk_widget(obj) -> bool:
    """Ελέγχει αν το αντικείμενο ανήκει στο οικοσύστημα Tkinter / CustomTkinter."""
    if obj is None:
        return False
    return (
        hasattr(obj, "winfo_id") or
        hasattr(obj, "winfo_exists") or
        hasattr(obj, "tk") or
        "tkinter" in obj.__class__.__module__.lower() or
        "customtkinter" in obj.__class__.__module__.lower()
    )


class TkDownloadProgressDialog:
    """
    CustomTkinter Modal Διάλογος Προόδου Λήψης με UI Throttling (~25fps)
    και ασφαλή ακύρωση (Safe Cancellation).
    """
    def __init__(self, master, download_url: str, asset_name: str, new_version: str):
        import customtkinter as ctk
        from tkinter import messagebox

        self.master = master
        self.download_url = download_url
        self.asset_name = asset_name
        self.new_version = new_version
        self.messagebox = messagebox

        self._is_cancelled = False
        self._response = None
        self.temp_dir = None
        self.target_file_path = None

        self.top = ctk.CTkToplevel(master)
        self.top.title(f"Λήψη Ενημέρωσης v{self.new_version}")
        self.top.geometry("480x210")
        self.top.resizable(False, False)

        if master:
            self.top.transient(master)
            self.top.grab_set()

        self.top.attributes("-topmost", True)
        self.top.protocol("WM_DELETE_WINDOW", self.cancel)

        # UI Elements
        self.lbl_status = ctk.CTkLabel(
            self.top,
            text=f"Γίνεται λήψη της έκδοσης v{self.new_version}...",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.lbl_status.pack(pady=(20, 10), padx=20, anchor="w")

        self.progress_bar = ctk.CTkProgressBar(self.top, width=440, height=20)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(pady=10, padx=20)

        self.lbl_details = ctk.CTkLabel(
            self.top,
            text="Προετοιμασία λήψης...",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.lbl_details.pack(pady=5, padx=20, anchor="w")

        self.btn_cancel = ctk.CTkButton(
            self.top,
            text="Ακύρωση",
            width=100,
            command=self.cancel
        )
        self.btn_cancel.pack(pady=(10, 15), padx=20, anchor="e")

        # Εκκίνηση Download Thread
        self.download_thread = threading.Thread(target=self._run_download, daemon=True)
        self.download_thread.start()

    def cancel(self):
        self._is_cancelled = True
        self.btn_cancel.configure(state="disabled")
        self.lbl_status.configure(text="Ακύρωση λήψης...")
        if self._response:
            try:
                self._response.close()
            except Exception:
                pass

    def _cleanup_temp_files(self):
        try:
            if self.target_file_path and os.path.exists(self.target_file_path):
                os.remove(self.target_file_path)
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def _update_ui(self, percent: int, downloaded_mb: float, total_mb: float, speed_mb_s: float):
        if not self.top.winfo_exists():
            return
        self.progress_bar.set(percent / 100.0)
        if total_mb > 0:
            self.lbl_details.configure(
                text=f"{downloaded_mb:.1f} MB / {total_mb:.1f} MB ({percent}%)  —  Ταχύτητα: {speed_mb_s:.2f} MB/s"
            )
        else:
            self.lbl_details.configure(text=f"{downloaded_mb:.1f} MB  —  Ταχύτητα: {speed_mb_s:.2f} MB/s")

    def _run_download(self):
        CHUNK_SIZE = 64 * 1024
        THROTTLE_INTERVAL_SEC = 0.040  # 40ms = 25 FPS

        try:
            self.temp_dir = tempfile.mkdtemp(prefix="app_update_")
            self.target_file_path = os.path.join(self.temp_dir, self.asset_name)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoUpdater"
            }
            req = urllib.request.Request(self.download_url, headers=headers)
            self._response = urllib.request.urlopen(req, timeout=30)

            total_size = int(self._response.info().get("Content-Length", 0))
            total_mb = total_size / (1024 * 1024) if total_size > 0 else 0.0

            bytes_downloaded = 0
            start_time = time.time()
            last_emit_time = 0.0
            last_bytes = 0

            with open(self.target_file_path, "wb") as out_file:
                while True:
                    if self._is_cancelled:
                        out_file.close()
                        self._cleanup_temp_files()
                        if self.top.winfo_exists():
                            self.top.destroy()
                        return

                    chunk = self._response.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    out_file.write(chunk)
                    bytes_downloaded += len(chunk)

                    now = time.time()
                    time_since_last_emit = now - last_emit_time

                    if time_since_last_emit >= THROTTLE_INTERVAL_SEC:
                        downloaded_mb = bytes_downloaded / (1024 * 1024)
                        percent = int((bytes_downloaded / total_size) * 100) if total_size > 0 else 0
                        delta_bytes = bytes_downloaded - last_bytes
                        speed_mb_s = (delta_bytes / (1024 * 1024)) / time_since_last_emit if time_since_last_emit > 0 else 0.0

                        if self.top.winfo_exists():
                            self.top.after(0, self._update_ui, percent, downloaded_mb, total_mb, speed_mb_s)

                        last_emit_time = now
                        last_bytes = bytes_downloaded

            if not self._is_cancelled:
                final_mb = bytes_downloaded / (1024 * 1024)
                if self.top.winfo_exists():
                    self.top.after(0, self._on_finished, self.target_file_path)

        except Exception as e:
            self._cleanup_temp_files()
            if not self._is_cancelled and self.top.winfo_exists():
                self.top.after(0, lambda: self.messagebox.showerror(
                    "Σφάλμα Λήψης",
                    f"Αποτυχία λήψης ενημέρωσης:\n{e}",
                    parent=self.top
                ))
            if self.top.winfo_exists():
                self.top.destroy()

    def _on_finished(self, installer_path: str):
        if self.top.winfo_exists():
            self.top.destroy()

        # Επιβεβαίωση πριν την εκτέλεση
        self.messagebox.showinfo(
            "Ετοιμότητα Εγκατάστασης",
            "Η λήψη της νέας έκδοσης ολοκληρώθηκε με επιτυχία!\n\n"
            "Η εφαρμογή θα τερματιστεί τώρα για να ολοκληρωθεί η εγκατάσταση "
            "και θα επανεκκινήσει αυτόματα σε λίγα δευτερόλεπτα.",
            parent=self.master
        )

        sanitize_and_launch_installer(installer_path, self.master)


def _check_updates_tk(parent=None, silent: bool = True, repo: str = GITHUB_REPO):
    """Έλεγχος ενημερώσεων για περιβάλλον Tkinter / CustomTkinter."""
    from tkinter import messagebox

    def worker():
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoUpdater",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status != 200:
                    if not silent and parent:
                        parent.after(0, lambda: messagebox.showwarning("Έλεγχος Ενημερώσεων", f"HTTP Status: {response.status}", parent=parent))
                    return
                data = json.loads(response.read().decode('utf-8'))

            latest_tag = data.get("tag_name", "")
            if not latest_tag:
                return

            if is_newer_version(latest_tag, __version__):
                assets = data.get("assets", [])
                installer = find_installer_asset(assets)
                if not installer:
                    if not silent and parent:
                        parent.after(0, lambda: messagebox.showwarning("Έλεγχος Ενημερώσεων", "Βρέθηκε νέα έκδοση αλλά λείπει το αρχείο εγκατάστασης (.exe).", parent=parent))
                    return

                new_version = normalize_version_string(latest_tag)
                download_url = installer.get("browser_download_url")
                asset_name = installer.get("name")
                size_mb = installer.get("size", 0) / (1024 * 1024)
                notes = data.get("body", "").strip()

                def prompt_user():
                    msg = (
                        f"Βρέθηκε νέα έκδοση: v{new_version}\n"
                        f"Μέγεθος αρχείου: {size_mb:.1f} MB\n\n"
                        f"Θέλετε να πραγματοποιηθεί αυτόματη λήψη και εγκατάσταση;"
                    )
                    if notes:
                        msg += f"\n\nΣημειώσεις έκδοσης:\n{notes[:350]}" + ("..." if len(notes) > 350 else "")

                    reply = messagebox.askyesno("Διαθέσιμη Νέα Έκδοση", msg, parent=parent)
                    if reply:
                        TkDownloadProgressDialog(
                            master=parent,
                            download_url=download_url,
                            asset_name=asset_name,
                            new_version=new_version
                        )

                if parent:
                    parent.after(0, prompt_user)

            elif not silent and parent:
                parent.after(0, lambda: messagebox.showinfo("Έλεγχος Ενημερώσεων", f"Έχετε ήδη την πιο πρόσφατη έκδοση (v{__version__})!", parent=parent))

        except Exception as e:
            if not silent and parent:
                parent.after(0, lambda: messagebox.showwarning("Έλεγχος Ενημερώσεων", f"Αποτυχία ελέγχου ενημερώσεων:\n{e}", parent=parent))

    t = threading.Thread(target=worker, daemon=True)
    t.start()


# =========================================================================
# 3. PyQt6 Implementation
# =========================================================================

def _check_updates_pyqt(parent=None, silent: bool = True, repo: str = GITHUB_REPO):
    """Έλεγχος ενημερώσεων για περιβάλλον PyQt6."""
    try:
        from updater_pyqt import check_for_updates as pyqt_check
        pyqt_check(parent=parent, silent=silent, repo=repo)
    except Exception as e:
        if not silent:
            print(f"[AutoUpdate Error]: {e}")


# =========================================================================
# 4. Κεντρική Συνάρτηση Εισόδου (Universal Entrypoint)
# =========================================================================

def check_for_updates(parent=None, silent: bool = True, repo: str = GITHUB_REPO):
    """
    Κεντρικό σημείο εισόδου για τον έλεγχο ενημερώσεων.
    
    Ανιχνεύει αυτόματα αν το parent ανήκει σε CustomTkinter/Tkinter ή PyQt6
    και εκτελεί τον αντίστοιχο ασφαλή μηχανισμό.
    
    :param parent: Το παράθυρο της εφαρμογής (ctk.CTk, tk.Tk ή PyQt6 QWidget).
    :param silent: Αν True (προεπιλογή κατά την εκκίνηση), δεν εμφανίζει μηνύματα
                   όταν δεν υπάρχει ενημέρωση ή σε σφάλμα δικτύου.
    :param repo: Το αποθετήριο GitHub (π.χ. 'owner/repo').
    """
    if _is_tk_or_ctk_widget(parent):
        _check_updates_tk(parent=parent, silent=silent, repo=repo)
    else:
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is not None:
                _check_updates_pyqt(parent=parent, silent=silent, repo=repo)
                return
        except ImportError:
            pass

        _check_updates_tk(parent=parent, silent=silent, repo=repo)
