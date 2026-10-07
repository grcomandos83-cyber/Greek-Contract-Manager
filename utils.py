import os
import sys
import shutil
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional, Union
from constants import BACKUP_FOLDER, DB_FILE

def get_resource_path(relative_path: str) -> str:
    """Λήψη απόλυτης διαδρομής για πόρους, λειτουργεί και για development και για PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def calculate_expiry_date(start_date_str: str, months_str: Union[str, int]) -> Optional[str]:
    try:
        start_date = datetime.strptime(start_date_str, '%d/%m/%Y').date()
        months = int(months_str)
        expiry_date = start_date + relativedelta(months=+months)
        return expiry_date.strftime('%d/%m/%Y')
    except Exception:
        return None

def get_contract_status(expiry_date_str: Optional[str]) -> str:
    if not expiry_date_str or expiry_date_str == 'N/A': return "NO_DATE"
    try:
        expiry_date = datetime.strptime(expiry_date_str, '%d/%m/%Y').date()
    except ValueError: return "ERROR"
    
    today = datetime.now().date()
    ninety_days_from_now = today + timedelta(days=90)

    if expiry_date < today: return "EXPIRED"
    elif expiry_date <= ninety_days_from_now: return "EXPIRING_SOON"
    else: return "ACTIVE"

def validate_date(date_text: str) -> bool:
    """Επαλήθευση ημερομηνίας"""
    try:
        datetime.strptime(date_text, '%d/%m/%Y')
        return True
    except ValueError:
        return False

def create_backup() -> bool:
    """Δημιουργία αυτόματου backup"""
    try:
        if not os.path.exists(BACKUP_FOLDER):
            os.makedirs(BACKUP_FOLDER)
            
        if os.path.exists(DB_FILE):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(BACKUP_FOLDER, f"backup_contracts_{timestamp}.db")
            shutil.copy2(DB_FILE, backup_file)
            
            # Διατήρηση μόνο των 10 πιο πρόσφατων backups
            backups = sorted([f for f in os.listdir(BACKUP_FOLDER) if f.startswith('backup_contracts_')])
            for old_backup in backups[:-10]:
                os.remove(os.path.join(BACKUP_FOLDER, old_backup))
                
            return True
    except Exception as e:
        print(f"Backup error: {e}")
    return False
