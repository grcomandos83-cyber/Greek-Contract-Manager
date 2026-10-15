import urllib.request
import json
import os
import sys
import subprocess
import threading
import tempfile
import time
from tkinter import messagebox
import customtkinter as ctk
from constants import APP_VERSION, GITHUB_REPO
from utils import get_resource_path


class DownloadCancelled(Exception):
    """Εξαίρεση που εγείρεται όταν ο χρήστης ακυρώνει τη λήψη."""
    pass


class UpdateProgressDialog(ctk.CTkToplevel):
    """
    Παράθυρο Προόδου Λήψης Ενημέρωσης (Progress Bar)
    
    Εκτελεί τη λήψη του νέου αρχείου σε ξεχωριστό threading.Thread ώστε να μην
    παγώνει το κύριο παράθυρο (UI Not Responding) και ενημερώνει δυναμικά
    μια CTkProgressBar μέσω reporthook με ποσοστό, MB και ταχύτητα λήψης.
    """
    def __init__(self, master, download_url: str, target_path: str, new_version: str = "",
                 on_success=None, on_error=None, on_cancel=None):
        super().__init__(master)
        
        self.download_url = download_url
        self.target_path = target_path
        self.new_version = new_version
        self.on_success = on_success
        self.on_error = on_error
        self.on_cancel = on_cancel
        
        self.cancelled = False
        self.start_time = time.time()
        self.last_ui_time = 0.0
        
        # Εικονίδιο εφαρμογής
        try:
            self.iconbitmap(get_resource_path(os.path.join("assets", "app.ico")))
        except Exception:
            pass

        self.title("Λήψη Ενημέρωσης")
        self.width = 440
        self.height = 230
        self.resizable(False, False)
        
        # Ανάκτηση χρωματικού θέματος από το κύριο παράθυρο
        theme_colors = getattr(master, "theme_colors", {}) if master else {}
        self.primary_color = theme_colors.get("primary", "#3B8ED0")
        self.accent_color = theme_colors.get("accent", "#2FA572")

        # Κεντράρισμα παραθύρου πάνω από το master
        self._center_window(master)

        if master:
            self.transient(master)
            self.grab_set()

        self._build_ui()
        
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())

        # Εκκίνηση λήψης σε ξεχωριστό thread
        self.worker_thread = threading.Thread(target=self._download_worker, daemon=True)
        self.worker_thread.start()

    def _center_window(self, master):
        self.update_idletasks()
        if master:
            try:
                m_x = master.winfo_rootx()
                m_y = master.winfo_rooty()
                m_w = master.winfo_width()
                m_h = master.winfo_height()
                x = m_x + (m_w // 2) - (self.width // 2)
                y = m_y + (m_h // 2) - (self.height // 2)
            except Exception:
                x = (self.winfo_screenwidth() // 2) - (self.width // 2)
                y = (self.winfo_screenheight() // 2) - (self.height // 2)
        else:
            x = (self.winfo_screenwidth() // 2) - (self.width // 2)
            y = (self.winfo_screenheight() // 2) - (self.height // 2)
        self.geometry(f"{self.width}x{self.height}+{max(0, x)}+{max(0, y)}")

    def _build_ui(self):
        # Επικεφαλίδα
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 5))
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="📥 Λήψη Ενημέρωσης",
            font=("Roboto", 16, "bold")
        )
        title_label.pack(side="left")
        
        if self.new_version:
            badge_frame = ctk.CTkFrame(header_frame, fg_color=self.primary_color, corner_radius=6)
            badge_frame.pack(side="right")
            badge_label = ctk.CTkLabel(
                badge_frame,
                text=f" {self.new_version} ",
                font=("Roboto", 11, "bold"),
                text_color="white"
            )
            badge_label.pack(padx=6, pady=2)
            
        # Ετικέτα κατάστασης
        self.status_label = ctk.CTkLabel(
            self,
            text="Σύνδεση με το διακομιστή...",
            font=("Roboto", 12),
            anchor="w"
        )
        self.status_label.pack(fill="x", padx=20, pady=(8, 4))
        
        # Μπάρα Προόδου (CTkProgressBar)
        self.progress_bar = ctk.CTkProgressBar(
            self,
            width=400,
            height=14,
            corner_radius=7,
            progress_color=self.primary_color
        )
        self.progress_bar.pack(padx=20, pady=6)
        self.progress_bar.set(0.0)
        
        # Σειρά στατιστικών (ποσοστό/MB αριστερά, ταχύτητα δεξιά)
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=(2, 10))
        
        self.percent_label = ctk.CTkLabel(
            stats_frame,
            text="0% (0.0 MB / 0.0 MB)",
            font=("Roboto", 11),
            text_color=("gray60", "gray40"),
            anchor="w"
        )
        self.percent_label.pack(side="left")
        
        self.speed_label = ctk.CTkLabel(
            stats_frame,
            text="",
            font=("Roboto", 11),
            text_color=("gray60", "gray40"),
            anchor="e"
        )
        self.speed_label.pack(side="right")
        
        # Κουμπί Ακύρωσης
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(5, 12))
        
        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Ακύρωση",
            width=95,
            height=28,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray80"),
            border_color=("gray60", "gray40"),
            hover_color=("gray85", "gray30"),
            command=self.cancel
        )
        self.cancel_btn.pack(side="right")

    def _reporthook(self, block_num, block_size, total_size):
        if self.cancelled:
            raise DownloadCancelled("Η λήψη ακυρώθηκε από τον χρήστη.")
            
        downloaded = block_num * block_size
        now = time.time()
        
        # Ενημέρωση UI κάθε ~40ms (25fps) ή στην ολοκλήρωση για μέγιστη απόδοση
        if now - self.last_ui_time >= 0.04 or (total_size > 0 and downloaded >= total_size):
            self.last_ui_time = now
            elapsed = now - self.start_time
            speed_bps = downloaded / elapsed if elapsed > 0.3 else 0
            
            if speed_bps >= 1024 * 1024:
                speed_text = f"{speed_bps / (1024 * 1024):.1f} MB/s"
            elif speed_bps >= 1024:
                speed_text = f"{speed_bps / 1024:.0f} KB/s"
            else:
                speed_text = ""
                
            downloaded_mb = downloaded / (1024 * 1024)
            if total_size > 0:
                fraction = min(1.0, downloaded / total_size)
                total_mb = total_size / (1024 * 1024)
                pct = int(fraction * 100)
                stats_text = f"{pct}% ({downloaded_mb:.1f} / {total_mb:.1f} MB)"
            else:
                fraction = 0.0
                stats_text = f"{downloaded_mb:.1f} MB"
                
            try:
                if self.winfo_exists():
                    self.after(0, self._update_progress_ui, fraction, stats_text, speed_text, total_size <= 0)
            except Exception:
                pass

    def _update_progress_ui(self, fraction, stats_text, speed_text, is_indeterminate):
        if not self.winfo_exists():
            return
        if is_indeterminate:
            if self.progress_bar.cget("mode") != "indeterminate":
                self.progress_bar.configure(mode="indeterminate")
                self.progress_bar.start()
        else:
            if self.progress_bar.cget("mode") == "indeterminate":
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(fraction)
        self.status_label.configure(text="Γίνεται λήψη ενημέρωσης...")
        self.percent_label.configure(text=stats_text)
        self.speed_label.configure(text=speed_text)

    def _download_worker(self):
        try:
            # Ορισμός User-Agent header για ασφαλές download
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]
            urllib.request.install_opener(opener)

            urllib.request.urlretrieve(self.download_url, self.target_path, reporthook=self._reporthook)

            if self.cancelled:
                raise DownloadCancelled("Η λήψη ακυρώθηκε από τον χρήστη.")

            if self.winfo_exists():
                self.after(0, self._handle_success)
        except DownloadCancelled:
            self._cleanup_target()
            if self.winfo_exists():
                self.after(0, self._handle_cancel)
        except Exception as e:
            self._cleanup_target()
            if self.winfo_exists():
                self.after(0, lambda err=e: self._handle_error(err))

    def _cleanup_target(self):
        try:
            if os.path.exists(self.target_path):
                os.remove(self.target_path)
        except Exception:
            pass

    def cancel(self):
        if not self.cancelled:
            self.cancelled = True
            self.status_label.configure(text="Ακύρωση λήψης...")
            self.cancel_btn.configure(state="disabled")

    def _handle_cancel(self):
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_cancel:
            self.on_cancel()

    def _handle_error(self, err):
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_error:
            self.on_error(err)
        else:
            messagebox.showerror("Σφάλμα Λήψης", f"Αποτυχία λήψης νέας έκδοσης:\n{err}", parent=self.master)

    def _handle_success(self):
        if not self.winfo_exists():
            if self.on_success:
                self.on_success(self.target_path)
            return
        self.status_label.configure(text="Η λήψη ολοκληρώθηκε! Εκκίνηση εγκατάστασης...")
        self.progress_bar.set(1.0)
        self.percent_label.configure(text="100%")
        self.cancel_btn.configure(state="disabled")

        # Μικρή παύση (350ms) ώστε ο χρήστης να δει τη συμπλήρωση στο 100%
        def proceed():
            try:
                self.destroy()
            except Exception:
                pass
            if self.on_success:
                self.on_success(self.target_path)

        self.after(350, proceed)


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


def _get_clean_env():
    """Καθαρίζει το περιβάλλον από μεταβλητές του PyInstaller (_MEIPASS, _PYI_, PATH)
    ώστε οι νέες διεργασίες (installer ή ανανεωμένο .exe) να μην προσπαθούν να φορτώσουν
    DLLs από προσωρινούς φακέλους της τρέχουσας έκδοσης που θα διαγραφούν."""
    clean_env = {}
    for k, v in os.environ.items():
        ku = k.upper()
        if ku.startswith("_MEI") or ku.startswith("_PYI_"):
            continue
        clean_env[k] = v

    clean_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        norm_meipass = os.path.normcase(os.path.abspath(meipass))
        path_parts = clean_env.get("PATH", "").split(os.pathsep)
        filtered = [
            p for p in path_parts
            if not os.path.normcase(os.path.abspath(p)).startswith(norm_meipass)
        ]
        clean_env["PATH"] = os.pathsep.join(filtered)
    return clean_env


def _prompt_update(parent_window, new_version, download_url, is_installer=True):
    """Ρωτάει τον χρήστη αν θέλει να κάνει ενημέρωση"""
    def ask():
        msg = (f"Υπάρχει διαθέσιμη μια νέα έκδοση ({new_version}).\n"
               f"Θέλετε να την κατεβάσετε και να εγκατασταθεί αυτόματα;")
        if messagebox.askyesno("Ενημέρωση Διαθέσιμη", msg, parent=parent_window):
            _download_and_apply(download_url, is_installer=is_installer, parent_window=parent_window, new_version=new_version)
            
    if parent_window:
        parent_window.after(0, ask)
    else:
        ask()


def _download_and_apply(download_url, is_installer=True, parent_window=None, new_version=""):
    """
    Κατεβάζει το νέο .exe / Setup σε ξεχωριστό thread με Progress Bar
    και εφαρμόζει την ενημέρωση χωρίς να παγώνει το UI.
    """
    # Έλεγχος περιβάλλοντος πηγαίου κώδικα (development)
    if not getattr(sys, 'frozen', False):
        test_confirm = messagebox.askyesno(
            "Λειτουργία Ανάπτυξης",
            "Τρέχετε τον πηγαίο κώδικα (όχι .exe).\n\n"
            "Θέλετε να εκτελεστεί δοκιμαστική λήψη για να δείτε τη Μπάρα Προόδου (Progress Bar) "
            "χωρίς να εφαρμοστεί εγκατάσταση;",
            parent=parent_window
        )
        if not test_confirm:
            return

    # Προετοιμασία διαδρομής αρχείου προορισμού
    if is_installer:
        temp_dir = tempfile.gettempdir()
        target_path = os.path.join(temp_dir, f"ContractManager_Setup_{os.getpid()}.exe")
    else:
        current_exe = os.path.abspath(sys.executable)
        exe_dir = os.path.dirname(current_exe)
        new_exe = current_exe + ".new"
        target_path = new_exe

        # Έλεγχος δικαιωμάτων εγγραφής στον φάκελο
        if getattr(sys, 'frozen', False) and not os.access(exe_dir, os.W_OK):
            messagebox.showerror(
                "Σφάλμα Δικαιωμάτων",
                f"Δεν υπάρχουν δικαιώματα εγγραφής στον φάκελο:\n{exe_dir}\n\n"
                "Μετακινήστε την εφαρμογή σε έναν προσωπικό φάκελο (π.χ. Έγγραφα ή Desktop) "
                "και δοκιμάστε ξανά.",
                parent=parent_window
            )
            return

    def on_download_success(downloaded_file):
        # Σε λειτουργία ανάπτυξης (πηγαίος κώδικας), απλώς ενημερώνουμε και καθαρίζουμε
        if not getattr(sys, 'frozen', False):
            file_size_mb = os.path.getsize(downloaded_file) / (1024 * 1024) if os.path.exists(downloaded_file) else 0
            messagebox.showinfo(
                "Επιτυχής Δοκιμή",
                f"Η δοκιμαστική λήψη ολοκληρώθηκε με επιτυχία ({file_size_mb:.1f} MB)!\n\n"
                "Το προσωρινό αρχείο θα διαγραφεί.",
                parent=parent_window
            )
            try:
                if os.path.exists(downloaded_file):
                    os.remove(downloaded_file)
            except Exception:
                pass
            return

        # --- Μέθοδος Inno Setup Installer: Ασφαλής, αθόρυβη & αξιόπιστη εκτέλεση ---
        if is_installer:
            try:
                DETACHED_PROCESS = 0x00000008
                flags = DETACHED_PROCESS
                if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    flags |= subprocess.CREATE_NO_WINDOW

                clean_env = _get_clean_env()

                # Clean os.environ in-place as well before spawning
                for k in list(os.environ.keys()):
                    if k.upper().startswith('_MEI') or k.upper().startswith('_PYI'):
                        os.environ.pop(k, None)

                subprocess.Popen(
                    [downloaded_file, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS"],
                    env=clean_env,
                    creationflags=flags,
                    close_fds=True
                )
                sys.exit(0)
            except Exception as e:
                messagebox.showerror("Σφάλμα Εγκατάστασης", f"Αποτυχία εκτέλεσης εγκαταστάτη:\n{e}", parent=parent_window)
                return

        # --- Fallback για Standalone .exe (αν δεν βρεθεί Installer) ---
        current_exe = os.path.abspath(sys.executable)
        exe_dir = os.path.dirname(current_exe)
        bat_path = os.path.join(exe_dir, "updater.bat")

        # FIX-A: Pure ASCII content — no chcp, no Greek comments, no goto labels
        # with non-ASCII chars. Paths are passed as %~1/%~2 arguments so the file's
        # own encoding never touches the paths.
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
            "rem --- Clear PyInstaller temp variables before launch ---\r\n"
            "set _MEIPASS2=\r\n"
            "set _MEIPASS=\r\n"
            "set _PYI_APPLICATION_HOME_DIR=\r\n"
            "set _PYI_ARCHIVE_FILE=\r\n"
            "set _PYI_SPLASH_IPC=\r\n"
            "set PYINSTALLER_RESET_ENVIRONMENT=1\r\n"
            "\r\n"
            "rem --- Launch: 'start \"\" ...' with empty title, NOT explorer.exe ---\r\n"
            "echo [%DATE% %TIME%] Launching... >> \"%LOG%\"\r\n"
            'start "" "%CURRENT_EXE%"\r\n'
            "echo [%DATE% %TIME%] Launch issued >> \"%LOG%\"\r\n"
            "\r\n"
            ":DONE\r\n"
            "echo [%DATE% %TIME%] === Auto-update finished === >> \"%LOG%\"\r\n"
            "endlocal\r\n"
            "(goto) 2>nul & del \"%~f0\"\r\n"
        )

        try:
            with open(bat_path, "w", encoding="ascii", newline="\r\n") as f:
                f.write(bat_content)
        except Exception as e:
            messagebox.showerror("Σφάλμα", f"Αποτυχία δημιουργίας script ενημέρωσης:\n{e}", parent=parent_window)
            return

        env = _get_clean_env()
        cmdline = f'cmd.exe /d /s /c ""{bat_path}" "{current_exe}" "{downloaded_file}""'

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

    # Εκκίνηση παραθύρου προόδου λήψης (CTkProgressBar & Threaded urlretrieve)
    UpdateProgressDialog(
        master=parent_window,
        download_url=download_url,
        target_path=target_path,
        new_version=new_version,
        on_success=on_download_success
    )
