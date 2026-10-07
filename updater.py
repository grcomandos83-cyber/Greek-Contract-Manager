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
    # Μην ελέγχεις αν τρέχουμε ως script (όχι πακεταρισμένο) 
    # αν δεν θέλουμε. Αλλά καλό είναι να δουλεύει και εκεί για δοκιμές.
    
    def _run_check():
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                
                latest_version = data.get('tag_name')
                if latest_version and latest_version != APP_VERSION:
                    # Εντοπίστηκε νέα έκδοση!
                    assets = data.get('assets', [])
                    download_url = None
                    for asset in assets:
                        if asset.get('name', '').endswith('.exe'):
                            download_url = asset.get('browser_download_url')
                            break
                            
                    if download_url:
                        _prompt_update(parent_window, latest_version, download_url)
        except Exception as e:
            # Αγνοούμε σιωπηλά τα λάθη ελέγχου (πχ χωρίς ίντερνετ)
            print(f"Update check failed: {e}")

    # Τρέχουμε τον έλεγχο σε άλλο thread για να μην κολλήσει το UI
    threading.Thread(target=_run_check, daemon=True).start()

def _prompt_update(parent_window, new_version, download_url):
    """Ρωτάει τον χρήστη αν θέλει να κάνει ενημέρωση"""
    # Πρέπει να κληθεί μέσω after() για να τρέξει στο main thread
    if parent_window:
        def ask():
            msg = f"Υπάρχει διαθέσιμη μια νέα έκδοση ({new_version}).\nΘέλετε να την κατεβάσετε και να εγκατασταθεί αυτόματα;"
            if messagebox.askyesno("Ενημέρωση Διαθέσιμη", msg, parent=parent_window):
                _download_and_apply(download_url)
        parent_window.after(0, ask)

def _download_and_apply(download_url):
    """Κατεβάζει το νέο .exe και δημιουργεί το script ενημέρωσης"""
    # Αν το τρέχουμε ως script (όχι pyinstaller exe), απλώς ενημερώνουμε το χρήστη
    if not getattr(sys, 'frozen', False):
        messagebox.showinfo("Ενημέρωση", "Τρέχετε τον πηγαίο κώδικα (όχι .exe). Κάντε 'git pull' για ενημέρωση.")
        return

    current_exe = sys.executable
    new_exe = current_exe + ".new"
    
    # 1. Λήψη
    try:
        urllib.request.urlretrieve(download_url, new_exe)
    except Exception as e:
        messagebox.showerror("Σφάλμα", f"Αποτυχία λήψης: {e}")
        return

    # 2. Δημιουργία batch script για αντικατάσταση
    bat_path = os.path.join(os.path.dirname(current_exe), "updater.bat")
    
    # Το script: περιμένει 2 δεύτερα, διαγράφει το παλιό exe, μετονομάζει το νέο, το τρέχει και διαγράφει τον εαυτό του.
    bat_content = f"""@echo off
timeout /t 2 /nobreak > nul
del "{current_exe}"
ren "{new_exe}" "{os.path.basename(current_exe)}"
start "" "{current_exe}"
del "%~f0"
"""
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
        
    # 3. Εκτέλεση του bat script και έξοδος
    # ΣΗΜΑΝΤΙΚΟ: Καθαρίζουμε τα env variables του PyInstaller
    # αλλιώς το νέο exe ψάχνει DLLs στον παλιό (διαγραμμένο) φάκελο _MEI
    env = os.environ.copy()
    env.pop('_MEIPASS2', None)
    env.pop('_MEIPASS', None)
    env.pop('PYI_DEFAULT_COMPAT', None)
    
    subprocess.Popen([bat_path], shell=True, env=env)
    sys.exit(0)
