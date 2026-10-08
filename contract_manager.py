import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import json
import os
import uuid
import sqlite3
import logging
from collections import OrderedDict

from datetime import datetime
from typing import List, Dict, Any, Optional
import updater
import sys
import os

# Αλλαγή του CWD στον φάκελο του εκτελέσιμου για να αποθηκεύονται σωστά το log και η βάση.
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('contract_manager.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from constants import DB_FILE, SETTINGS_FILE, PDF_FOLDER, BACKUP_FOLDER, COLOR_THEMES, SPECIAL_FIELD_TRANSLATIONS, APP_VERSION
from utils import create_backup, get_contract_status, get_resource_path
from database import DatabaseManager
from ui_forms import ContractFormToplevel, AdvancedSearchToplevel, CategoryManagerWindow
from dashboard_view import DashboardView
from contract_list_view import ContractListView
from signals import SignalManager, Signals
from contract_versions_view import ContractVersionsWindow
from notification_system import notification_manager

# --- Ρυθμίσεις Εμφάνισης ---
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

# Καλείται κατά το κλείσιμο



# =========================================================================
# === ΚΥΡΙΟ ΠΡΟΓΡΑΜΜΑ ===
# =========================================================================

class ContractApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"Διαχείριση Συμβάσεων Pro - {APP_VERSION}")
        
        WINDOW_WIDTH = 1280
        WINDOW_HEIGHT = 850
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (WINDOW_WIDTH // 2)
        y = (screen_height // 2) - (WINDOW_HEIGHT // 2)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
        
        try:
            self.iconbitmap(get_resource_path(os.path.join("assets", "app.ico")))
        except Exception as e:
            pass
                
        self.db_manager = DatabaseManager(DB_FILE)
        self.contracts_data: List[Dict[str, Any]] = [] 
        self.form_window: Optional[ContractFormToplevel] = None 
        self.advanced_search_window: Optional[AdvancedSearchToplevel] = None
        
        self.sort_column: str = 'expiry_date'
        self.sort_direction: str = 'asc'
        
        self.current_theme: str = "Minimalist"
        self.theme_colors: Dict[str, str] = COLOR_THEMES[self.current_theme]
        
        self.current_filtered_contracts: List[Dict[str, Any]] = []
        self._search_job: Optional[str] = None
        self.current_search_params: Dict[str, Any] = {}
        
        # Debounce & Performance Optimization
        self._last_search_time: float = 0
        self._search_cache: OrderedDict[str, List[Dict[str, Any]]] = OrderedDict()  # LRU cache
        self._min_query_interval: float = 0.25  # minimum 250ms between queries
        self._debounce_delay: int = 600  # 600ms delay for user input
        self._max_cache_size: int = 100  # Maximum cache entries before cleanup
        
        self.__app_setup_storage() 
        self.load_settings()

        self.grid_columnconfigure(0, weight=0) 
        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(0, weight=1)

        # Left Side: Dashboard
        self.left_frame = ctk.CTkFrame(self, width=300, corner_radius=15)
        self.left_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        dashboard_callbacks = {
            'new_contract': lambda: self._open_contract_form(None),
            'manage_categories': self.open_category_manager,
            'show_stats': self.show_statistics,
            'show_notifications': self.check_upcoming_expiries,
            'advanced_search': self.open_advanced_search,
            'export_data': self.export_data,
            'change_theme': self.open_theme_selector
        }
        
        self.dashboard_view = DashboardView(
            self.left_frame, 
            callbacks=dashboard_callbacks,
            theme_colors=self.theme_colors,
            fg_color="transparent"
        )
        self.dashboard_view.pack(fill="both", expand=True)

        # Right Side: Content Area
        self.right_container = ctk.CTkFrame(self, fg_color="transparent")
        self.right_container.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        self.setup_right_area() 
        
        # Αρχικό γέμισμα λίστας & στατιστικών
        self.load_data_from_db()
        self.apply_filters()
        self.refresh_dashboard_stats()
        
        self.create_menubar()
        
        # --- SIGNALS SUBSCRIPTION ---
        SignalManager.subscribe(Signals.CONTRACT_UPSERTED, self._on_contract_changed)
        SignalManager.subscribe(Signals.CONTRACT_DELETED, self._on_contract_changed)
        SignalManager.subscribe(Signals.CATEGORIES_UPDATED, self._on_categories_changed)
        
        self.optimize_performance()
        
        # Αρχικοποίηση συστήματος ειδοποιήσεων
        notification_manager.set_root(self)
        
        # Έλεγχος για νέες εκδόσεις (αυτόματη ενημέρωση)
        updater.check_for_updates(self)
        
        # Cleanup κατά το κλείσιμο
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        


    def _on_closing(self):
        """Cleanup handler κατά το κλείσιμο της εφαρμογής."""
        try:
            # Καταστροφή notification window αν υπάρχει
            if notification_manager.notification_window and notification_manager.notification_window.winfo_exists():
                notification_manager.notification_window.destroy()
            
            # Ακύρωση pending search jobs
            if self._search_job is not None:
                try:
                    self.after_cancel(self._search_job)
                except Exception:
                    pass
            
            # Unsubscribe signals
            SignalManager.unsubscribe(Signals.CONTRACT_UPSERTED, self._on_contract_changed)
            SignalManager.unsubscribe(Signals.CONTRACT_DELETED, self._on_contract_changed)
            SignalManager.unsubscribe(Signals.CATEGORIES_UPDATED, self._on_categories_changed)
            
            logger.info("Η εφαρμογή τερματίστηκε ομαλά.")
        except Exception as e:
            logger.error(f"Σφάλμα κατά το κλείσιμο: {e}")
        finally:
            self.destroy()

    def __app_setup_storage(self):
        if not os.path.exists(PDF_FOLDER): 
            os.makedirs(PDF_FOLDER)
        if not os.path.exists(BACKUP_FOLDER): 
            os.makedirs(BACKUP_FOLDER)
        if not os.path.exists(SETTINGS_FILE):
            default_settings = {
                "categories": ["Ενέργεια", "Τηλεφωνία", "Ύδρευση", "Ασφάλεια", "Internet"],
                "current_theme": "Minimalist"
            }
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f: 
                json.dump(default_settings, f, ensure_ascii=False)

    def load_settings(self):
        """Load application settings from JSON file."""
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                self.settings = json.load(f)
            self.categories = self.settings.get("categories", [])
            self.current_theme = self.settings.get("current_theme", "Minimalist")
            self.theme_colors = COLOR_THEMES.get(self.current_theme, COLOR_THEMES["Minimalist"])
            
            logger.info(f"Φορτώθηκαν ρυθμίσεις: {len(self.categories)} κατηγορίες, θέμα: {self.current_theme}")
            
            # Propagate theme to views if initialized
            if hasattr(self, 'dashboard_view'):
                self.dashboard_view.update_theme(self.theme_colors)
                self.refresh_dashboard_stats()
            if hasattr(self, 'contract_list_view'):
                self.contract_list_view.update_theme(self.theme_colors)
        except FileNotFoundError:
            logger.warning(f"Το αρχείο ρυθμίσεων δεν βρέθηκε, χρήση προεπιλογών")
            self.settings = {"categories": [], "current_theme": "Minimalist"}
            self.categories = []
            self.current_theme = "Minimalist"
            self.theme_colors = COLOR_THEMES["Minimalist"]
        except json.JSONDecodeError as json_err:
            logger.error(f"Σφάλμα ανάγνωσης ρυθμίσεων: {json_err}", exc_info=True)
            messagebox.showwarning("Σφάλμα Ρυθμίσεων",
                                 "Το αρχείο ρυθμίσεων είναι κατεστραμμένο.\n\nΘα χρησιμοποιηθούν προεπιλογές.", parent=self)
            self.settings = {"categories": [], "current_theme": "Minimalist"}
            self.categories = []
            self.current_theme = "Minimalist"
            self.theme_colors = COLOR_THEMES["Minimalist"]
        except Exception as e:
            logger.error(f"Απροσδόκητο σφάλμα κατά τη φόρτωση ρυθμίσεων: {e}", exc_info=True)
            self.settings = {"categories": [], "current_theme": "Minimalist"}
            self.categories = []
            self.current_theme = "Minimalist"
            self.theme_colors = COLOR_THEMES["Minimalist"]

    def save_settings(self):
        """Save application settings to JSON file."""
        try:
            self.settings["categories"] = self.categories
            self.settings["current_theme"] = self.current_theme
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
            logger.info(f"Αποθηκεύτηκαν ρυθμίσεις: {len(self.categories)} κατηγορίες, θέμα: {self.current_theme}")
            if hasattr(self, 'combo_filter'):
                self.combo_filter.configure(values=["Όλα"] + self.categories)
        except IOError as io_err:
            logger.error(f"Σφάλμα I/O κατά την αποθήκευση ρυθμίσεων: {io_err}", exc_info=True)
            messagebox.showerror("Σφάλμα Αποθήκευσης",
                               f"Αποτυχία αποθήκευσης ρυθμίσεων:\n\n{str(io_err)}", parent=self)
        except TypeError as json_err:
            logger.error(f"Σφάλμα κωδικοποίησης JSON ρυθμίσεων: {json_err}", exc_info=True)
            messagebox.showerror("Σφάλμα JSON",
                               f"Αποτυχία κωδικοποίησης ρυθμίσεων:\n\n{str(json_err)}", parent=self)
        except Exception as e:
            logger.error(f"Απροσδόκητο σφάλμα κατά την αποθήκευση ρυθμίσεων: {e}", exc_info=True)
            messagebox.showerror("Σφάλμα", f"Απροσδόκητο σφάλμα:\n\n{str(e)}", parent=self)

    def open_theme_selector(self):
        theme_window = ctk.CTkToplevel(self)
        theme_window.title("Επιλογή Χρωματικού Θέματος")
        theme_window.geometry("400x300")
        theme_window.transient(self)
        theme_window.grab_set()
        
        ctk.CTkLabel(theme_window, text="Επιλέξτε Χρωματικό Θέμα", 
                    font=("Roboto", 18, "bold")).pack(pady=20)
        
        for theme_name, colors in COLOR_THEMES.items():
            theme_frame = ctk.CTkFrame(theme_window, fg_color="transparent")
            theme_frame.pack(fill="x", padx=20, pady=5)
            
            color_preview = ctk.CTkFrame(theme_frame, width=30, height=30, 
                                       fg_color=colors["primary"],
                                       corner_radius=5)
            color_preview.pack(side="left", padx=(0, 10))
            
            ctk.CTkButton(theme_frame, 
                         text=theme_name,
                         command=lambda tn=theme_name: self._apply_theme_and_close(tn, theme_window),
                         fg_color=colors["primary"],
                         hover_color=colors["secondary"],
                         width=200).pack(side="left")
            
            if theme_name == self.current_theme:
                ctk.CTkLabel(theme_frame, text="✓", 
                           font=("Roboto", 16, "bold")).pack(side="right", padx=10)

    def _apply_theme_and_close(self, theme_name: str, window: ctk.CTkToplevel):
        self.change_theme(theme_name)
        window.destroy()

    def change_theme(self, theme_name: str):
        if theme_name in COLOR_THEMES:
            self.current_theme = theme_name
            self.theme_colors = COLOR_THEMES[theme_name]
            
            self.settings["current_theme"] = theme_name
            self.save_settings()
            
            self.apply_theme_colors()
            self.lift()
            self.focus_force()
            messagebox.showinfo("Θέμα", f"Το θέμα άλλαξε σε: {theme_name}", parent=self)

    def apply_theme_colors(self):
        self.dashboard_view.update_theme(self.theme_colors)
        self.contract_list_view.update_theme(self.theme_colors)
        self.apply_filters() # Re-render cards

    def _open_contract_form(self, contract_to_edit: Optional[Dict[str, Any]] = None):
        self.load_settings()
        win = self.form_window
        if win is None or not win.winfo_exists():
            win = ContractFormToplevel(self, self.db_manager, self.categories, contract_to_edit, self.current_theme)
            self.form_window = win
            self.wait_window(win) 
            
            if win.result_contract:
                self.process_contract_result(win.result_contract)
            
            self.load_settings()
            self.combo_filter.configure(values=["Όλα"] + self.categories)
            self.form_window = None
        elif win is not None:
            win.focus()

    def process_contract_result(self, result_contract: Dict[str, Any]):
        try:
            existing_contract = self.db_manager.get_contract_by_id(result_contract['id'])
            
            if existing_contract:
                self.db_manager.update_contract(result_contract)
                msg = "ενημερώθηκε"
                logger.info(f"Ενημερώθηκε σύμβαση με ID: {result_contract['id']}")
            else:
                self.db_manager.insert_contract(result_contract)
                msg = "αποθηκεύτηκε"
                logger.info(f"Αποθηκεύτηκε νέα σύμβαση με ID: {result_contract['id']}")
            
            self.lift()
            self.focus_force()
            messagebox.showinfo(title="Επιτυχία", message=f"Η σύμβαση {msg}!", parent=self)
            
            # Clear search cache when database is modified
            self._clear_search_cache()
            
            # Emit Signal instead of manual reload (though we reload to be sure we have fresh DB state)
            # The signal listener will handle the UI update
            SignalManager.emit(Signals.CONTRACT_UPSERTED, result_contract)
            
        except sqlite3.Error as db_err:
            logger.error(f"Σφάλμα βάσης δεδομένων κατά την αποθήκευση σύμβασης: {db_err}", exc_info=True)
            self.lift()
            self.focus_force()
            messagebox.showerror(title="Σφάλμα Βάσης Δεδομένων",
                               message=f"Αποτυχία αποθήκευσης στη βάση δεδομένων:\n\n{str(db_err)}", parent=self)
        except KeyError as key_err:
            logger.error(f"Λείπει απαιτούμενο πεδίο στη σύμβαση: {key_err}", exc_info=True)
            self.lift()
            self.focus_force()
            messagebox.showerror(title="Σφάλμα Δεδομένων",
                               message=f"Λείπει απαιτούμενο πεδίο: {str(key_err)}", parent=self)
        except Exception as e:
            logger.error(f"Απροσδόκητο σφάλμα κατά την αποθήκευση σύμβασης: {e}", exc_info=True)
            self.lift()
            self.focus_force()
            messagebox.showerror(title="Σφάλμα",
                               message=f"Απροσδόκητο σφάλμα:\n\n{str(e)}", parent=self)

    def edit_contract(self, contract: Dict[str, Any]):
        self._open_contract_form(contract)

    def setup_right_area(self):
        search_filter_frame = ctk.CTkFrame(self.right_container, fg_color="transparent")
        search_filter_frame.pack(fill="x", pady=(0, 10))
        
        self.entry_search = ctk.CTkEntry(search_filter_frame, 
                                       placeholder_text="🔍 Αναζήτηση σε ΟΛΑ τα πεδία...")
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_search.bind("<KeyRelease>", self._delayed_search)
        self.combo_filter = ctk.CTkComboBox(search_filter_frame, values=["Όλα"] + self.categories, 
                                          command=self.on_filter_change, width=150)
        self.combo_filter.set("Όλα")
        self.combo_filter.pack(side="left", padx=(0, 10))
        
        self.btn_advanced_search = ctk.CTkButton(search_filter_frame, text="🎯 Προχωρημένη", 
                                               command=self.open_advanced_search,
                                               width=120, fg_color="#8e44ad")
        self.btn_advanced_search.pack(side="left", padx=(0, 10))
        
        self.btn_clear_filters = ctk.CTkButton(search_filter_frame, text="🧹 Καθαρισμός", 
                                             command=self.clear_all_filters,
                                             width=100, fg_color="#7f8c8d")
        self.btn_clear_filters.pack(side="left", padx=(0, 10))
        
        # Headers
        self.list_header_frame = ctk.CTkFrame(self.right_container, fg_color="#3a3a3a", height=30)
        self.list_header_frame.pack(fill="x", pady=(0, 0))
        self.setup_list_headers()

        # Contract List View
        callbacks = {
            'edit_contract': self.edit_contract,
            'delete_contract': self.delete_contract,
            'open_pdf': self.open_pdf
        }
        self.contract_list_view = ContractListView(self.right_container, 
                                                 callbacks=callbacks,
                                                 theme_colors=self.theme_colors)
        self.contract_list_view.pack(fill="both", expand=True)

    def open_advanced_search(self):
        win = self.advanced_search_window
        if win is None or not win.winfo_exists():
            win = AdvancedSearchToplevel(self, self.db_manager, self.categories, self.current_theme)
            self.advanced_search_window = win
        elif win is not None:
            win.focus()
    
    def clear_all_filters(self):
        self.entry_search.delete(0, 'end')
        self.combo_filter.set("Όλα")
        self.current_search_params = {}
        self.apply_filters()
        self.lift()
        self.focus_force()
        messagebox.showinfo("Καθαρισμός", "Όλα τα φίλτρα καθαρίστηκαν", parent=self)

    def refresh_dashboard_stats(self):
        stats = self.db_manager.get_statistics()
        self.dashboard_view.refresh_stats(stats)

    def setup_list_headers(self):
        header_frame = self.list_header_frame
        header_frame.columnconfigure(0, weight=1) 
        header_frame.columnconfigure(1, weight=0) 
        self.header_provider_btn = ctk.CTkButton(header_frame, text="Πάροχος / Αριθμός", fg_color="transparent", hover_color="#444", command=lambda: self.set_sort('provider'))
        self.header_provider_btn.grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.header_expiry_btn = ctk.CTkButton(header_frame, text="Λήξη", fg_color="transparent", hover_color="#444", command=lambda: self.set_sort('expiry_date'))
        self.header_expiry_btn.grid(row=0, column=1, padx=(10, 10), pady=5, sticky="e")
        self.update_header_arrows() 

    def set_sort(self, column: str):
        if self.sort_column == column: 
            self.sort_direction = 'asc' if self.sort_direction == 'desc' else 'desc'
        else:
            self.sort_column = column
            self.sort_direction = 'asc' 
        self.apply_filters()

    def update_header_arrows(self):
        self.header_provider_btn.configure(text="Πάροχος / Αριθμός")
        self.header_expiry_btn.configure(text="Λήξη")
        arrow = " ↓" if self.sort_direction == 'desc' else " ↑"
        if self.sort_column == 'provider': 
            self.header_provider_btn.configure(text="Πάροχος / Αριθμός" + arrow)
        elif self.sort_column == 'expiry_date': 
            self.header_expiry_btn.configure(text="Λήξη" + arrow)
            
    def on_filter_change(self, choice: str): 
        self.apply_filters()
        
    def load_data_from_db(self):
        self.contracts_data = self.db_manager.get_all_contracts()

    def apply_filters(self):
        """Apply filters with debounce and LRU caching to optimize database queries."""
        import time
        
        try:
            search_text = self.entry_search.get().lower()
            category_filter = self.combo_filter.get()
            
            # Create cache key
            cache_key = f"{search_text}|{category_filter}|{str(self.current_search_params)}"
            
            # Check if result is in cache (LRU: move to end if found)
            if cache_key in self._search_cache:
                # Move to end (most recently used)
                self._search_cache.move_to_end(cache_key)
                filtered_contracts = self._search_cache[cache_key]
                logger.debug(f"Cache hit για αναζήτηση: {search_text[:50]}")
            else:
                # Check if minimum interval has passed since last query
                current_time = time.time()
                time_since_last_query = current_time - self._last_search_time
                
                if time_since_last_query < self._min_query_interval:
                    # Skip this query if too soon, will be retried on next debounce
                    logger.debug("Παράλειψη query λόγω minimum interval")
                    return
                
                # Execute database query
                self._last_search_time = current_time
                logger.debug(f"Εκτέλεση query για: {search_text[:50]}")
                
                try:
                    if self.current_search_params:
                        filtered_contracts = self.db_manager.advanced_search_contracts(self.current_search_params)
                    elif search_text:
                        try:
                            filtered_contracts = self.db_manager.fts_search(search_text)
                            if category_filter != "Όλα":
                                # Ανοχή σε τυχόν κενά/πεζά-κεφαλαία στα αποθηκευμένα types
                                normalized_filter = category_filter.strip().lower()
                                filtered_contracts = [
                                    c for c in filtered_contracts
                                    if str(c.get('type', '')).strip().lower() == normalized_filter
                                ]
                        except sqlite3.OperationalError as fts_err:
                            logger.warning(f"FTS search απέτυχε, χρήση fuzzy search: {fts_err}")
                            filtered_contracts = self.db_manager.fuzzy_search(search_text, category_filter)
                    else:
                        filtered_contracts = self.db_manager.search_contracts_comprehensive(search_text, category_filter)
                except sqlite3.Error as db_err:
                    logger.error(f"Σφάλμα βάσης δεδομένων κατά την αναζήτηση: {db_err}", exc_info=True)
                    self.lift()
                    self.focus_force()
                    messagebox.showerror("Σφάλμα Αναζήτησης",
                                       f"Σφάλμα κατά την αναζήτηση στη βάση:\n\n{str(db_err)}", parent=self)
                    filtered_contracts = []
                
                # LRU Cache management: remove oldest if cache is full
                if len(self._search_cache) >= self._max_cache_size:
                    # Remove oldest entry (first item in OrderedDict)
                    self._search_cache.popitem(last=False)
                    logger.debug("Αφαίρεση παλαιότερου cache entry")
                
                # Add new entry (will be at the end)
                self._search_cache[cache_key] = filtered_contracts
            
            self._sort_contracts(filtered_contracts)
            self.current_filtered_contracts = filtered_contracts
            
            # Update View
            self.contract_list_view.update_contracts(filtered_contracts)
            
        except tk.TclError as tcl_err:
            logger.error(f"Σφάλμα Tkinter κατά την εφαρμογή φίλτρων: {tcl_err}", exc_info=True)
            # Don't show messagebox for Tkinter errors during widget destruction
        except Exception as e:
            logger.error(f"Απροσδόκητο σφάλμα κατά την εφαρμογή φίλτρων: {e}", exc_info=True)
            self.lift()
            self.focus_force()
            messagebox.showerror("Σφάλμα", f"Απροσδόκητο σφάλμα:\n\n{str(e)}", parent=self)

    def _sort_contracts(self, contracts: List[Dict[str, Any]]):
        """Sort contracts with optimized date parsing using caching."""
        reverse_order = self.sort_direction == 'desc'
        sort_key = self.sort_column
        
        # Cache for parsed dates to avoid repeated parsing
        date_cache = {}
        default_date = datetime.strptime('01/01/0001', '%d/%m/%Y')
        
        def get_sort_key_value(contract):
            if sort_key == 'expiry_date':
                date_str = contract.get('expiry_date')
                if date_str:
                    # Check cache first
                    if date_str not in date_cache:
                        try:
                            date_cache[date_str] = datetime.strptime(date_str, '%d/%m/%Y')
                        except ValueError:
                            date_cache[date_str] = default_date
                    return date_cache[date_str]
                return default_date
            elif sort_key == 'provider':
                return contract.get('provider', '').lower()
            return contract.get(sort_key, '')
        
        contracts.sort(key=get_sort_key_value, reverse=reverse_order)

    # Bulk Operations methods removed as per user request


    def open_pdf(self, path: str):
        """Open PDF file with appropriate system viewer."""
        if not os.path.exists(path):
            logger.warning(f"Το αρχείο PDF δεν βρέθηκε: {path}")
            self.lift()
            self.focus_force()
            messagebox.showerror(title="Αρχείο Δεν Βρέθηκε",
                               message=f"Το αρχείο PDF δεν βρέθηκε:\n\n{path}", parent=self)
            return
        
        try:
            logger.info(f"Άνοιγμα PDF: {path}")
            os.startfile(path)  # type: ignore
        except AttributeError:
            # os.startfile is Windows-only
            try:
                import subprocess, sys
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                logger.info(f"Χρήση {opener} για άνοιγμα PDF")
                subprocess.call([opener, path])
            except FileNotFoundError as fnf_err:
                logger.error(f"Δεν βρέθηκε το πρόγραμμα ανοίγματος PDF: {fnf_err}", exc_info=True)
                self.lift()
                self.focus_force()
                messagebox.showerror(title="Σφάλμα Συστήματος",
                                   message=f"Δεν βρέθηκε πρόγραμμα για άνοιγμα PDF.\n\nΠαρακαλώ εγκαταστήστε ένα PDF viewer.", parent=self)
            except Exception as e2:
                logger.error(f"Αποτυχία ανοίγματος PDF με {opener}: {e2}", exc_info=True)
                self.lift()
                self.focus_force()
                messagebox.showerror(title="Σφάλμα Ανοίγματος",
                                   message=f"Αποτυχία ανοίγματος PDF:\n\n{str(e2)}", parent=self)
        except OSError as os_err:
            logger.error(f"Σφάλμα λειτουργικού συστήματος κατά το άνοιγμα PDF: {os_err}", exc_info=True)
            messagebox.showerror(title="Σφάλμα Συστήματος",
                               message=f"Σφάλμα κατά το άνοιγμα του αρχείου:\n\n{str(os_err)}")
        except Exception as e:
            logger.error(f"Απροσδόκητο σφάλμα κατά το άνοιγμα PDF: {e}", exc_info=True)
            messagebox.showerror(title="Σφάλμα",
                               message=f"Απροσδόκητο σφάλμα:\n\n{str(e)}")

    def _clear_search_cache(self):
        """Clear search cache when database is modified."""
        self._search_cache.clear()
        self._last_search_time = 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring performance."""
        return {
            'cache_size': len(self._search_cache),
            'max_cache_size': self._max_cache_size,
            'cache_usage_percent': (len(self._search_cache) / self._max_cache_size) * 100 if self._max_cache_size > 0 else 0
        }

    def optimize_performance(self):
        if hasattr(self, 'entry_search'):
            self.entry_search.unbind("<KeyRelease>")
            self.entry_search.bind("<KeyRelease>", self._delayed_search)

    def _delayed_search(self, event):
        """Debounce search input with 300ms delay to reduce database load."""
        if hasattr(self, '_search_job') and self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except (ValueError, tk.TclError):
                pass
        # Use 300ms delay instead of 50ms to significantly reduce database queries
        self._search_job = self.after(self._debounce_delay, self.apply_filters)



    def create_menubar(self):
        menubar = tk.Menu(self)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Εξαγωγή δεδομένων", command=self.export_data)
        file_menu.add_command(label="Εισαγωγή δεδομένων", command=self.import_from_json)
        file_menu.add_separator()
        file_menu.add_command(label="Μεταφορά από JSON", command=self.migrate_from_json)
        file_menu.add_separator()
        file_menu.add_command(label="Δημιουργία Backup", command=self.manual_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Έξοδος", command=self.quit)
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Στατιστικά", command=self.show_statistics)
        tools_menu.add_command(label="Ειδοποιήσεις", command=self.check_upcoming_expiries)
        tools_menu.add_command(label="Διαχείριση Εκδόσεων", command=self.show_versions_manager)
        tools_menu.add_separator()
        tools_menu.add_command(label="Αρχικοποίηση Βάσης", command=self.initialize_database)
        
        theme_menu = tk.Menu(menubar, tearoff=0)
        theme_menu.add_command(label="Μπλε (Προεπιλογή)", command=lambda: self.change_theme("Μπλε (Προεπιλογή)"))
        theme_menu.add_command(label="Πράσινο", command=lambda: self.change_theme("Πράσινο"))
        theme_menu.add_command(label="Μωβ", command=lambda: self.change_theme("Μωβ"))
        theme_menu.add_command(label="Πορτοκαλί", command=lambda: self.change_theme("Πορτοκαλί"))
        theme_menu.add_separator()
        theme_menu.add_command(label="Minimalist", command=lambda: self.change_theme("Minimalist"))
        
        menubar.add_cascade(label="Αρχείο", menu=file_menu)
        menubar.add_cascade(label="Εργαλεία", menu=tools_menu)
        menubar.add_cascade(label="Χρώμα", menu=theme_menu)
        
        self.configure(menu=menubar)

    def initialize_database(self):
        if not messagebox.askyesno(
            "Αρχικοποίηση Βάσης",
            "Θέλετε να αρχικοποιηθεί η βάση δεδομένων;\nΔεν θα διαγραφούν δεδομένα.",
            parent=self
        ):
            return
        try:
            self.db_manager.initialize_database()
            self.load_data_from_db()
            self.apply_filters()
            self.lift()
            self.focus_force()
            messagebox.showinfo("Αρχικοποίηση Βάσης", "Η βάση δεδομένων αρχικοποιήθηκε επιτυχώς.", parent=self)
        except sqlite3.Error as db_err:
            logger.error(f"Database initialization error: {db_err}", exc_info=True)
            messagebox.showerror("Σφάλμα Βάσης Δεδομένων", f"Αποτυχία αρχικοποίησης:\n\n{db_err}", parent=self)
        except Exception as e:
            logger.error(f"Unexpected initialization error: {e}", exc_info=True)
            messagebox.showerror("Σφάλμα", f"Απροσδόκητο σφάλμα:\n\n{e}", parent=self)
    def open_category_manager(self):
        # The CategoryManagerWindow emits Signals.CATEGORIES_UPDATED
        # which is handled by self._on_categories_changed.
        # No manual callback needed for refreshing.
        CategoryManagerWindow(self, self.categories, self.db_manager)

    def manual_backup(self):
        if create_backup():
            self.lift()
            self.focus_force()
            messagebox.showinfo("Backup", "Το αντίγραφο ασφαλείας δημιουργήθηκε επιτυχώς!", parent=self)
        else:
            self.lift()
            self.focus_force()
            messagebox.showerror("Backup", "Σφάλμα κατά τη δημιουργία αντιγράφου.", parent=self)

    def migrate_from_json(self):
        json_file = "contracts.json"
        if not os.path.exists(json_file):
            self.lift()
            self.focus_force()
            messagebox.showinfo("Μεταφορά", "Δεν βρέθηκε αρχείο contracts.json για μεταφορά.", parent=self)
            return
        if messagebox.askyesno("Μεταφορά", "Θέλετε να μεταφερθούν τα δεδομένα από το JSON αρχείο στη νέα βάση SQLite;", parent=self):
            if self.db_manager.migrate_from_json(json_file):
                self.lift()
                self.focus_force()
                messagebox.showinfo("Μεταφορά", "Τα δεδομένα μεταφέρθηκαν επιτυχώς!", parent=self)
                SignalManager.emit(Signals.CONTRACT_UPSERTED, None)
            else:
                self.lift()
                self.focus_force()
                messagebox.showerror("Μεταφορά", "Αποτυχία μεταφοράς δεδομένων.", parent=self)

    def export_data(self):
        """Export contracts data to JSON file."""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialfile=f"contracts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            if filename:
                logger.info(f"Εξαγωγή δεδομένων σε: {filename}")
                # Fresh query αντί για cached contracts_data
                export_data = self.db_manager.get_all_contracts()
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=4)
                logger.info(f"Εξήχθησαν {len(export_data)} συμβάσεις επιτυχώς")
                self.lift()
                self.focus_force()
                messagebox.showinfo("Εξαγωγή", f"Τα δεδομένα εξήχθησαν επιτυχώς!\n\nΑρχείο: {filename}\nΣυμβάσεις: {len(self.contracts_data)}", parent=self)
        except IOError as io_err:
            logger.error(f"Σφάλμα I/O κατά την εξαγωγή: {io_err}", exc_info=True)
            self.lift()
            self.focus_force()
            messagebox.showerror("Σφάλμα Αρχείου",
                               f"Αποτυχία εγγραφής στο αρχείο:\n\n{str(io_err)}", parent=self)
        except TypeError as json_err:
            logger.error(f"Σφάλμα κωδικοποίησης JSON: {json_err}", exc_info=True)
            self.lift()
            self.focus_force()
            messagebox.showerror("Σφάλμα JSON",
                               f"Αποτυχία κωδικοποίησης δεδομένων:\n\n{str(json_err)}", parent=self)
        except Exception as e:
            logger.error(f"Απροσδόκητο σφάλμα κατά την εξαγωγή: {e}", exc_info=True)
            self.lift()
            self.focus_force()
            messagebox.showerror("Σφάλμα", f"Απροσδόκητο σφάλμα:\n\n{str(e)}", parent=self)

    def import_from_json(self):
        """Import contracts data from JSON file."""
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filename:
            try:
                logger.info(f"Εισαγωγή δεδομένων από: {filename}")
                with open(filename, 'r', encoding='utf-8') as f:
                    imported_data = json.load(f)
                
                if not isinstance(imported_data, list):
                    logger.warning(f"Μη έγκυρη μορφή αρχείου: {type(imported_data)}")
                    self.lift()
                    self.focus_force()
                    messagebox.showerror("Μη Έγκυρη Μορφή",
                                       "Μη έγκυρη μορφή αρχείου.\n\nΑπαιτείται λίστα συμβάσεων.", parent=self)
                    return
                
                success_count = 0
                error_count = 0
                
                for i, contract in enumerate(imported_data):
                    try:
                        if 'id' not in contract:
                            contract['id'] = str(uuid.uuid4())
                        
                        existing = self.db_manager.get_contract_by_id(contract['id'])
                        if existing:
                            self.db_manager.update_contract(contract)
                        else:
                            self.db_manager.insert_contract(contract)
                        success_count += 1  # type: ignore
                    except sqlite3.Error as db_err:
                        error_count += 1  # type: ignore
                        logger.error(f"Σφάλμα εισαγωγής σύμβασης {i+1}: {db_err}")
                    except Exception as e:
                        error_count += 1  # type: ignore
                        logger.error(f"Σφάλμα επεξεργασίας σύμβασης {i+1}: {e}")
                
                SignalManager.emit(Signals.CONTRACT_UPSERTED, None)
                
                if error_count > 0:
                    logger.warning(f"Εισαγωγή ολοκληρώθηκε με σφάλματα: {success_count} επιτυχείς, {error_count} αποτυχίες")
                    self.lift()
                    self.focus_force()
                    messagebox.showwarning("Εισαγωγή με Σφάλματα",
                                         f"Εισήχθησαν {success_count} συμβάσεις επιτυχώς.\n\n{error_count} συμβάσεις απέτυχαν.", parent=self)
                else:
                    logger.info(f"Εισήχθησαν {success_count} συμβάσεις επιτυχώς")
                    self.lift()
                    self.focus_force()
                    messagebox.showinfo("Εισαγωγή", f"Εισήχθησαν {success_count} συμβάσεις επιτυχώς!", parent=self)
                    
            except FileNotFoundError:
                logger.error(f"Το αρχείο δεν βρέθηκε: {filename}")
                self.lift()
                self.focus_force()
                messagebox.showerror("Αρχείο Δεν Βρέθηκε",
                                   f"Το αρχείο δεν βρέθηκε:\n\n{filename}", parent=self)
            except json.JSONDecodeError as json_err:
                logger.error(f"Σφάλμα ανάγνωσης JSON: {json_err}", exc_info=True)
                self.lift()
                self.focus_force()
                messagebox.showerror("Μη Έγκυρο JSON",
                                   f"Το αρχείο δεν είναι έγκυρο JSON:\n\n{str(json_err)}", parent=self)
            except IOError as io_err:
                logger.error(f"Σφάλμα I/O κατά την εισαγωγή: {io_err}", exc_info=True)
                self.lift()
                self.focus_force()
                messagebox.showerror("Σφάλμα Αρχείου",
                                   f"Αποτυχία ανάγνωσης αρχείου:\n\n{str(io_err)}", parent=self)
            except Exception as e:
                logger.error(f"Απροσδόκητο σφάλμα κατά την εισαγωγή: {e}", exc_info=True)
                self.lift()
                self.focus_force()
                messagebox.showerror("Σφάλμα", f"Απροσδόκητο σφάλμα:\n\n{str(e)}", parent=self)

    def check_upcoming_expiries(self):
        expired, expiring_soon = self.db_manager.get_expiring_contracts()
        if expiring_soon or expired:
            self.show_notifications_window(expired, expiring_soon)
        else:
            self.lift()
            self.focus_force()
            messagebox.showinfo("Ειδοποιήσεις", "Δεν υπάρχουν συμβάσεις που λήγουν σύντομα ή έχουν λήξει.", parent=self)

    def show_notifications_window(self, expired: List[Dict], expiring_soon: List[Dict]):
        # Reuse existing logic logic, but for brevity/cleanliness we could extract this too.
        # Implemented for completeness similar to original.
        notif_window = ctk.CTkToplevel(self)
        notif_window.title("Ειδοποιήσεις Συμβάσεων")
        notif_window.geometry("600x400")
        notif_window.transient(self)
        notif_window.grab_set()
        notif_window.attributes("-topmost", True)
        
        tabview = ctk.CTkTabview(notif_window)
        tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        if expired:
            tab1 = tabview.add("Ληγμένες")
            self._populate_notification_tab(tab1, expired, self.theme_colors["light_danger"])
        if expiring_soon:
            tab2 = tabview.add("Προς Λήξη")
            self._populate_notification_tab(tab2, expiring_soon, self.theme_colors["light_warning"])

    def _populate_notification_tab(self, tab: ctk.CTkFrame, contracts: List[Dict], bg_color: str):
        scroll_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True)

        for contract in contracts:
            # Card Container
            frame = ctk.CTkFrame(scroll_frame, fg_color=bg_color, corner_radius=12, border_width=1, border_color="#e0e0e0")
            frame.pack(fill="x", pady=5, padx=5)

            # Content Frame
            content = ctk.CTkFrame(frame, fg_color="transparent")
            content.pack(padx=10, pady=10, fill="x")

            # Info Text
            provider = contract['provider']
            number = contract['number']
            expiry = contract.get('expiry_date', 'N/A')
            contract_type = contract.get('type', 'N/A')
            start_date = contract.get('date', 'N/A')
            months = contract.get('months', '')
            comments = contract.get('comments', '')

            ctk.CTkLabel(content, text=provider, font=("Roboto", 14, "bold"), text_color="#34495e").pack(anchor="w")
            ctk.CTkLabel(content, text=f"Αρ. Σύμβασης: {number}", font=("Roboto", 12), text_color="#5d6d7e").pack(anchor="w")
            ctk.CTkLabel(content, text=f"Είδος: {contract_type}", font=("Roboto", 12), text_color="#5d6d7e").pack(anchor="w")

            # Date row
            date_info = f"Έναρξη: {start_date}"
            if months:
                date_info += f"   |   Διάρκεια: {months} μήνες"
            ctk.CTkLabel(content, text=date_info, font=("Roboto", 12), text_color="#5d6d7e").pack(anchor="w")

            ctk.CTkLabel(content, text=f"Λήξη: {expiry}", font=("Roboto", 12, "bold"), text_color="#e74c3c").pack(anchor="w", pady=(2, 0))

            if comments:
                ctk.CTkLabel(content, text=f"Σχόλια: {comments}", font=("Roboto", 11, "italic"),
                             text_color="#7f8c8d", wraplength=500, justify="left").pack(anchor="w", pady=(2, 5))
            else:
                ctk.CTkFrame(content, height=5, fg_color="transparent").pack()
            
            # Buttons
            btn_frame = ctk.CTkFrame(content, fg_color="transparent")
            btn_frame.pack(fill="x", pady=(5, 0))
            
            ctk.CTkButton(btn_frame, text="✎ Επεξεργασία", height=28, width=100, 
                         fg_color=self.theme_colors["secondary"],
                         command=lambda c=contract: self.edit_contract(c)).pack(side="left", padx=(0, 5))
                         
            if contract.get('pdf_path'):
                ctk.CTkButton(btn_frame, text="📄 PDF", height=28, width=70, 
                             fg_color=self.theme_colors["primary"],
                             command=lambda p=contract['pdf_path']: self.open_pdf(p)).pack(side="left", padx=5)

    def show_statistics(self):
        stats_window = ctk.CTkToplevel(self)
        stats_window.title("Στατιστικά Συμβάσεων")
        stats_window.geometry("500x500")
        stats_window.transient(self)
        stats_window.grab_set() 
        stats_window.attributes("-topmost", True)
        stats = self.db_manager.get_statistics()
        main_frame = ctk.CTkScrollableFrame(stats_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(main_frame, text="Στατιστικά Συμβάσεων", font=("Roboto", 18, "bold")).pack(pady=10)
        total = stats['total']
        ctk.CTkLabel(main_frame, text=f"Σύνολο Συμβάσεων: {total}", 
                    font=("Roboto", 16, "bold"), text_color=self.theme_colors["primary"]).pack(pady=5)
        ctk.CTkLabel(main_frame, text="Κατανομή ανά Είδος:", font=("Roboto", 14, "bold")).pack(pady=(15, 5))
        for contract_type, count in sorted(stats['by_type'].items()):
             percentage = (count / total) * 100 if total > 0 else 0
             ctk.CTkLabel(main_frame, text=f"  {contract_type}: {count} ({percentage:.1f}%)", font=("Roboto", 12)).pack(anchor="w", padx=20)

    def _on_contract_changed(self, data):
        """Signal handler for contract additions/updates/deletions."""
        self._clear_search_cache()
        self.load_data_from_db()
        self.apply_filters()
        self.refresh_dashboard_stats()

    def _on_categories_changed(self, data):
        """Signal handler for category updates."""
        self._clear_search_cache()
        self.load_settings()
        self.combo_filter.configure(values=["Όλα"] + self.categories)

        if isinstance(data, dict) and data.get("action") == "rename":
            old_name = data.get("old_name")
            new_name = data.get("new_name")
            if old_name and new_name and old_name != new_name:
                current_filter = self.combo_filter.get()
                if current_filter and current_filter.strip().lower() == old_name.strip().lower():
                    self.combo_filter.set(new_name)
                if self.current_search_params:
                    cat_filter = self.current_search_params.get("category_filter")
                    if cat_filter and cat_filter.strip().lower() == old_name.strip().lower():
                        self.current_search_params["category_filter"] = new_name

        self.load_data_from_db()
        self.apply_filters()
        self.refresh_dashboard_stats()
        
    def delete_contract(self, contract_id: str):
        if messagebox.askyesno("Επιβεβαίωση", "Είστε σίγουρος/η για τη διαγραφή;", parent=self):
            try:
                self.db_manager.delete_contract(contract_id)
                # Clear search cache when database is modified
                self._clear_search_cache()
                SignalManager.emit(Signals.CONTRACT_DELETED, contract_id)
                self.lift()
                self.focus_force()
                messagebox.showinfo("Επιτυχία", "Η σύμβαση διαγράφηκε.", parent=self)
            except Exception as e:
                self.lift()
                self.focus_force()
                messagebox.showerror("Σφάλμα", f"Αποτυχία διαγραφής: {e}", parent=self)
    
    def show_versions_manager(self):
        """Εμφάνιση διαχείρισης εκδόσεων για την επιλεγμένη σύμβαση"""
        if not self.current_filtered_contracts:
            messagebox.showinfo("Πληροφορία", "Δεν υπάρχουν συμβάσεις για προβολή εκδόσεων")
            return
        
        # Λήψη της πρώτης ορατής σύμβασης (ή επιλογή από τον χρήστη)
        contract = self.current_filtered_contracts[0]
        
        try:
            ContractVersionsWindow(
                self,
                self.db_manager,
                contract['id'],
                contract.get('provider', 'Σύμβαση'),
                self.theme_colors
            )
        except Exception as e:
            logger.error(f"Error showing versions manager: {e}", exc_info=True)
            messagebox.showerror("Σφάλμα", f"Αποτυχία ανοίγματος διαχείρισης εκδόσεων: {str(e)}")

if __name__ == "__main__":
    try:
        app = ContractApp()
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Η εφαρμογή τερματίστηκε από τον χρήστη (Ctrl+C).")
        print("\nΗ εφαρμογή τερματίστηκε.")
