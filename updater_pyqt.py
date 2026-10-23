"""
updater_pyqt.py - Καθαρή υλοποίηση Auto-Update για εφαρμογές PyQt6 σε Windows.

Απαιτήσεις Master Prompt:
1. Background Checking μέσω QThread (UpdateCheckThread).
2. Σημασιολογική σύγκριση εκδόσεων με packaging.version.Version (αγνοώντας 'v').
3. Αυτόματος εντοπισμός .exe installer (setup/install) από τα assets του GitHub Release.
4. Ασύγχρονη λήψη (DownloadWorker) σε chunks (64 KB) σε tempfile.mkdtemp.
5. UI Throttling: Εκπομπή σημάτων προόδου ανά ~40ms (25fps) για αποφυγή συμφόρησης του PyQt6 event loop.
6. Υπολογισμός πραγματικής στιγμιαίας ταχύτητας (MB/s) και ποσοστού λήψης.
7. Safe Cancellation με άμεσο κλείσιμο socket και διαγραφή ημιτελών αρχείων.
8. Αποτροπή File Locking & PyInstaller DLL Crashes:
   - Πλήρης καθαρισμός os.environ (_MEIPASS, _PYI*, PYINSTALLER*, PYTHONPATH, PYTHONHOME)
   - PYINSTALLER_RESET_ENVIRONMENT=1
   - Εκτέλεση Inno Setup με ["/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART"]
   - Detached Process (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
   - Άμεσος τερματισμός με QApplication.quit() και os._exit(0)
"""

import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error
import re
from typing import Optional, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QMessageBox, QWidget
)

try:
    from packaging.version import Version, InvalidVersion
    HAS_PACKAGING = True
except ImportError:
    HAS_PACKAGING = False
    Version = None
    InvalidVersion = Exception

try:
    from version import __version__, GITHUB_REPO
except ImportError:
    try:
        from constants import APP_VERSION as __version__, GITHUB_REPO
    except ImportError:
        __version__ = "1.0.0"
        GITHUB_REPO = "grcomandos83-cyber/Greek-Contract-Manager"


def normalize_version_string(v_str: str) -> str:
    if not v_str:
        return "0.0.0"
    cleaned = str(v_str).strip()
    if cleaned.lower().startswith('v'):
        cleaned = cleaned[1:].strip()
    return cleaned


def is_newer_version(latest_tag: str, current_ver: str) -> bool:
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


class UpdateCheckThread(QThread):
    update_available = pyqtSignal(dict)
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, repo: str = GITHUB_REPO, current_version: str = __version__, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.current_version = current_version

    def run(self):
        api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PyQt6-AutoUpdater",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status != 200:
                    self.error.emit(f"HTTP Status {response.status}")
                    return

                raw_data = response.read().decode('utf-8')
                data = json.loads(raw_data)

            latest_tag = data.get("tag_name", "")
            if not latest_tag:
                self.error.emit("Δεν βρέθηκε tag έκδοσης στο GitHub Release.")
                return

            if is_newer_version(latest_tag, self.current_version):
                assets = data.get("assets", [])
                installer = find_installer_asset(assets)

                if installer:
                    payload = {
                        "version": normalize_version_string(latest_tag),
                        "raw_tag": latest_tag,
                        "download_url": installer.get("browser_download_url"),
                        "asset_name": installer.get("name"),
                        "size": installer.get("size", 0),
                        "release_notes": data.get("body", "").strip(),
                        "published_at": data.get("published_at", "")
                    }
                    self.update_available.emit(payload)
                else:
                    self.error.emit("Βρέθηκε νέα έκδοση, αλλά δεν υπάρχει αρχείο εγκατάστασης (.exe Setup) στα assets.")
            else:
                self.no_update.emit()

        except urllib.error.URLError as e:
            self.error.emit(f"Σφάλμα σύνδεσης στο διαδίκτυο: {e.reason}")
        except json.JSONDecodeError:
            self.error.emit("Αποτυχία ανάλυσης απάντησης από το GitHub API.")
        except Exception as e:
            self.error.emit(f"Απροσδόκητο σφάλμα: {str(e)}")


class DownloadWorker(QThread):
    progress = pyqtSignal(int, float, float, float)  # percent, downloaded_mb, total_mb, speed_mb_s
    finished = pyqtSignal(str)
    cancelled = pyqtSignal()
    error = pyqtSignal(str)

    CHUNK_SIZE = 64 * 1024
    THROTTLE_INTERVAL_SEC = 0.040  # 40ms = 25 FPS

    def __init__(self, download_url: str, asset_name: str, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.asset_name = asset_name
        self._is_cancelled = False
        self._response = None
        self.temp_dir = None
        self.target_file_path = None

    def cancel(self):
        self._is_cancelled = True
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

    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="app_update_")
            self.target_file_path = os.path.join(self.temp_dir, self.asset_name)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PyQt6-AutoUpdater"
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
                        self.cancelled.emit()
                        return

                    chunk = self._response.read(self.CHUNK_SIZE)
                    if not chunk:
                        break

                    out_file.write(chunk)
                    bytes_downloaded += len(chunk)

                    now = time.time()
                    time_since_last_emit = now - last_emit_time

                    if time_since_last_emit >= self.THROTTLE_INTERVAL_SEC:
                        downloaded_mb = bytes_downloaded / (1024 * 1024)
                        percent = int((bytes_downloaded / total_size) * 100) if total_size > 0 else 0

                        delta_bytes = bytes_downloaded - last_bytes
                        speed_mb_s = (delta_bytes / (1024 * 1024)) / time_since_last_emit if time_since_last_emit > 0 else 0.0

                        self.progress.emit(percent, downloaded_mb, total_mb, speed_mb_s)
                        last_emit_time = now
                        last_bytes = bytes_downloaded

            if not self._is_cancelled:
                final_mb = bytes_downloaded / (1024 * 1024)
                total_duration = max(time.time() - start_time, 0.001)
                avg_speed = final_mb / total_duration
                self.progress.emit(100, final_mb, final_mb, avg_speed)
                self.finished.emit(self.target_file_path)

        except Exception as e:
            if self._is_cancelled:
                self._cleanup_temp_files()
                self.cancelled.emit()
            else:
                self._cleanup_temp_files()
                self.error.emit(f"Σφάλμα κατά τη λήψη: {str(e)}")


class UpdateProgressDialog(QDialog):
    def __init__(self, download_url: str, asset_name: str, new_version: str, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.asset_name = asset_name
        self.new_version = new_version
        self.installer_path: Optional[str] = None

        self.setWindowTitle(f"Λήψη Ενημέρωσης v{self.new_version}")
        self.setFixedSize(480, 210)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._build_ui()
        self._start_download()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.status_label = QLabel(f"Γίνεται λήψη της νέας έκδοσης v{self.new_version}...")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #C0C0C0;
                border-radius: 4px;
                text-align: center;
                height: 22px;
                background-color: #F5F5F5;
            }
            QProgressBar::chunk {
                background-color: #2E86C1;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.details_label = QLabel("Προετοιμασία λήψης...")
        self.details_label.setStyleSheet("font-size: 11px; color: #555;")
        layout.addWidget(self.details_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Ακύρωση")
        self.btn_cancel.setFixedWidth(100)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def _start_download(self):
        self.worker = DownloadWorker(self.download_url, self.asset_name, parent=self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    @pyqtSlot(int, float, float, float)
    def _on_progress(self, percent: int, downloaded_mb: float, total_mb: float, speed_mb_s: float):
        self.progress_bar.setValue(percent)
        if total_mb > 0:
            self.details_label.setText(
                f"{downloaded_mb:.1f} MB / {total_mb:.1f} MB ({percent}%)  —  Ταχύτητα: {speed_mb_s:.2f} MB/s"
            )
        else:
            self.details_label.setText(f"{downloaded_mb:.1f} MB  —  Ταχύτητα: {speed_mb_s:.2f} MB/s")

    @pyqtSlot(str)
    def _on_finished(self, installer_path: str):
        self.installer_path = installer_path
        self.accept()
        confirm_and_launch_update(installer_path, self.parent())

    @pyqtSlot()
    def _on_cancelled(self):
        self.details_label.setText("Η λήψη ακυρώθηκε.")
        self.reject()

    @pyqtSlot(str)
    def _on_error(self, err_msg: str):
        self.details_label.setText(f"Σφάλμα: {err_msg}")
        QMessageBox.critical(self, "Σφάλμα Λήψης", f"Αποτυχία λήψης ενημέρωσης:\n{err_msg}")
        self.reject()

    def _on_cancel_clicked(self):
        self.btn_cancel.setEnabled(False)
        self.status_label.setText("Ακύρωση λήψης...")
        self.worker.cancel()

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)
        event.accept()


def launch_silent_installer(installer_path: str):
    if not os.path.exists(installer_path):
        raise FileNotFoundError(f"Δεν βρέθηκε το αρχείο εγκατάστασης: {installer_path}")

    clean_env = os.environ.copy()
    pyinstaller_keys = [
        k for k in clean_env.keys()
        if k.startswith(("_MEI", "_PYI", "PYINSTALLER"))
        or k in ("PYTHONPATH", "PYTHONHOME")
    ]
    for key in pyinstaller_keys:
        clean_env.pop(key, None)

    clean_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    creation_flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    installer_args = [
        installer_path,
        "/SILENT",
        "/CLOSEAPPLICATIONS",
        "/NORESTART"
    ]

    subprocess.Popen(
        installer_args,
        env=clean_env,
        creationflags=creation_flags,
        cwd=tempfile.gettempdir(),
        close_fds=True
    )

    app_instance = QApplication.instance()
    if app_instance:
        app_instance.quit()

    os._exit(0)


def confirm_and_launch_update(installer_path: str, parent: Optional[QWidget] = None):
    msg = QMessageBox(parent)
    msg.setWindowTitle("Ετοιμότητα Εγκατάστασης")
    msg.setIcon(QMessageBox.Icon.Information)
    msg.setText(
        "Η λήψη της νέας έκδοσης ολοκληρώθηκε με επιτυχία!\n\n"
        "Η εφαρμογή θα τερματιστεί τώρα αυτόματα για να εφαρμοστεί η ενημέρωση "
        "και θα επανεκκινήσει αυτόματα."
    )
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg.exec()

    launch_silent_installer(installer_path)


_active_check_threads = []

def check_for_updates(parent: Optional[QWidget] = None, silent: bool = False, repo: str = GITHUB_REPO):
    thread = UpdateCheckThread(repo=repo, current_version=__version__, parent=parent)
    _active_check_threads.append(thread)

    def on_update_available(payload: dict):
        _cleanup_thread()
        version = payload.get("version", "")
        asset_name = payload.get("asset_name", "")
        download_url = payload.get("download_url", "")
        size_bytes = payload.get("size", 0)
        size_mb = size_bytes / (1024 * 1024) if size_bytes > 0 else 0.0
        notes = payload.get("release_notes", "")

        msg_text = (
            f"Βρέθηκε νέα έκδοση: v{version}\n"
            f"Μέγεθος αρχείου: {size_mb:.1f} MB\n\n"
            f"Θέλετε να πραγματοποιηθεί αυτόματη λήψη και εγκατάσταση;"
        )
        if notes:
            msg_text += f"\n\nΣημειώσεις έκδοσης:\n{notes[:400]}" + ("..." if len(notes) > 400 else "")

        reply = QMessageBox.question(
            parent,
            "Διαθέσιμη Νέα Έκδοση",
            msg_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            dialog = UpdateProgressDialog(
                download_url=download_url,
                asset_name=asset_name,
                new_version=version,
                parent=parent
            )
            dialog.exec()

    def on_no_update():
        _cleanup_thread()
        if not silent:
            QMessageBox.information(
                parent,
                "Έλεγχος Ενημερώσεων",
                f"Έχετε ήδη την πιο πρόσφατη έκδοση (v{__version__})!"
            )

    def on_error(err: str):
        _cleanup_thread()
        if not silent:
            QMessageBox.warning(
                parent,
                "Έλεγχος Ενημερώσεων",
                f"Δεν ήταν δυνατός ο έλεγχος ενημερώσεων:\n{err}"
            )

    def _cleanup_thread():
        if thread in _active_check_threads:
            _active_check_threads.remove(thread)

    thread.update_available.connect(on_update_available)
    thread.no_update.connect(on_no_update)
    thread.error.connect(on_error)
    thread.start()
