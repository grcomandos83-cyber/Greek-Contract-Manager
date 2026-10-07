# --- Ονόματα Αρχείων ---
DB_FILE = "contracts.db"
SETTINGS_FILE = "settings.json"
PDF_FOLDER = "contract_pdfs"
BACKUP_FOLDER = "backups"

# --- Στοιχεία Εφαρμογής & Ενημερώσεων ---
APP_VERSION = "v1.0.3"
GITHUB_REPO = "grcomandos83-cyber/contract-manager-sqlite"

# =========================================================================
# === ΧΡΩΜΑΤΙΚΑ ΘΕΜΑΤΑ ===
# =========================================================================

COLOR_THEMES = {
    "Μπλε (Προεπιλογή)": {
        "primary": "#3B8ED0",
        "secondary": "#1F6AA5",
        "accent": "#2FA572",
        "danger": "#BE3324",
        "warning": "#F39C12",
        "light_danger": "#FDE2E2",
        "light_warning": "#FEF3C7"
    },
    "Πράσινο": {
        "primary": "#27AE60",
        "secondary": "#219653",
        "accent": "#2ECC71",
        "danger": "#E74C3C",
        "warning": "#F1C40F",
        "light_danger": "#FDE2E2",
        "light_warning": "#FEF3C7"
    },
    "Μωβ": {
        "primary": "#8E44AD",
        "secondary": "#7D3C98",
        "accent": "#9B59B6",
        "danger": "#C0392B",
        "warning": "#F39C12",
        "light_danger": "#FDE2E2",
        "light_warning": "#FEF3C7"
    },
    "Πορτοκαλί": {
        "primary": "#E67E22",
        "secondary": "#D35400",
        "accent": "#F39C12",
        "danger": "#C0392B",
        "warning": "#F1C40F",
        "light_danger": "#FDE2E2",
        "light_warning": "#FEF3C7"
    },
    "Minimalist": {
        "primary": "#264653",      # Dark Cypress/Blue
        "secondary": "#2A9D8F",    # Soft Teal
        "accent": "#E9C46A",       # Muted Gold
        "danger": "#E76F51",       # Soft Terracotta
        "warning": "#F4A261",      # Sandy Orange
        "light_danger": "#FDE2E2", # Very light red (for light mode bg)
        "light_warning": "#FEF3C7" # Very light orange (for light mode bg)
    }
}

SPECIAL_FIELD_TRANSLATIONS = {
    'legal_entity': 'Νομικό Πρόσωπο',
    'program': 'Πρόγραμμα',
    'supply_number': 'Αριθμός Παροχής',
    'concerns_institute': 'Ίδρυμα',
    'line_number': 'Αριθμός Γραμμής',
}

CATEGORY_DYNAMIC_FIELDS = {
    "Ενέργεια": {
        "legal_entity": "Νομικό Πρόσωπο",
        "program": "Πρόγραμμα",
        "supply_number": "Αριθμός Παροχής",
        "concerns_institute": "Όνομα Ιδρύματος"
    },
    "Τηλεφωνία": {
        "legal_entity": "Νομικό Πρόσωπο",
        "line_number": "Αριθμός Τηλεφωνικής Γραμμής",
        "program": "Πρόγραμμα",
        "concerns_institute": "Όνομα Ιδρύματος"
    },
    "Internet": {
        "legal_entity": "Νομικό Πρόσωπο",
        "line_number": "Αριθμός Τηλεφωνικής Γραμμής",
        "program": "Πρόγραμμα",
        "concerns_institute": "Όνομα Ιδρύματος"
    }
}
