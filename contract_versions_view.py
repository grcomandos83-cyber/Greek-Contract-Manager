import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional
from utils import get_resource_path
import logging
import threading
from notification_system import show_notification

logger = logging.getLogger(__name__)


from mixins import MessageBoxMixin

class ContractVersionsWindow(MessageBoxMixin, ctk.CTkToplevel):
    """Window για προβολή και διαχείριση εκδόσεων συμβάσεων"""
    
    def __init__(self, parent, db_manager, contract_id: str, contract_name: str, theme_colors: Dict[str, str]):
        super().__init__(parent)
        
        self.title(f"Ιστορικό Εκδόσεων - {contract_name}")
        self.geometry("800x600")
        self.transient(parent)
        self.grab_set()
        self.attributes("-topmost", True)
        
        import os
        try:
            self.iconbitmap(get_resource_path(os.path.join("assets", "app.ico")))
        except Exception:
            pass
            
        self.db_manager = db_manager
        self.contract_id = contract_id
        self.contract_name = contract_name
        self.theme_colors = theme_colors
        
        self.selected_version_id: Optional[str] = None
        self.versions: List[Dict[str, Any]] = []
        self.is_maximized = False
        
        self.setup_ui()
        self.load_versions()
    
    def setup_ui(self):
        """Δημιουργία UI elements"""
        
        # Header με κουμπιά
        header_frame = ctk.CTkFrame(self, fg_color=self.theme_colors["primary"])
        header_frame.pack(fill="x", padx=0, pady=0)
        
        # Αριστερά: Τίτλος
        ctk.CTkLabel(
            header_frame,
            text=f"📋 Εκδόσεις Σύμβασης: {self.contract_name}",
            font=("Roboto", 16, "bold"),
            text_color="white"
        ).pack(side="left", padx=15, pady=10)
        
        # Δεξιά: Κουμπιά ελέγχου
        control_frame = ctk.CTkFrame(header_frame, fg_color=self.theme_colors["primary"])
        control_frame.pack(side="right", padx=10, pady=8)
        
        ctk.CTkButton(
            control_frame,
            text="□" if not self.is_maximized else "▢",
            command=self.toggle_maximize,
            width=40,
            height=30,
            fg_color="white",
            text_color=self.theme_colors["primary"],
            font=("Roboto", 14, "bold")
        ).pack(side="left", padx=5)
         
        # Main content frame
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Left side: Versions list
        left_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="both", expand=False, padx=(0, 10))
        
        ctk.CTkLabel(left_frame, text="Εκδόσεις:", font=("Roboto", 12, "bold")).pack(anchor="w", pady=(0, 10))
        
        # Versions scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(
            left_frame,
            width=250,
            fg_color="transparent"
        )
        scroll_frame.pack(fill="both", expand=True)
        
        self.versions_frame = scroll_frame
        
        # Right side: Version details
        right_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        right_frame.pack(side="right", fill="both", expand=True)
        
        ctk.CTkLabel(right_frame, text="Λεπτομέρειες Έκδοσης:", font=("Roboto", 12, "bold")).pack(anchor="w", pady=(0, 10))
        
        # Details scrollable frame
        details_scroll = ctk.CTkScrollableFrame(
            right_frame,
            fg_color="#f0f0f0",
            corner_radius=8
        )
        details_scroll.pack(fill="both", expand=True, pady=(0, 10))
        
        self.details_frame = details_scroll
        
        # Action buttons
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(10, 0))
        
        ctk.CTkButton(
            buttons_frame,
            text="🔄 Επαναφορά",
            command=self.restore_version,
            fg_color=self.theme_colors["secondary"],
            hover_color=self.theme_colors["primary"],
            width=120
        ).pack(side="left", padx=(0, 5))
        
        ctk.CTkButton(
            buttons_frame,
            text="📊 Σύγκριση",
            command=self.compare_versions,
            fg_color=self.theme_colors["accent"],
            width=120
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            buttons_frame,
            text="🗑️ Διαγραφή",
            command=self.delete_version,
            fg_color=self.theme_colors["danger"],
            width=120
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            buttons_frame,
            text="✕ Κλείσιμο",
            command=self.destroy,
            fg_color="#7f8c8d",
            width=100
        ).pack(side="right")

    
    def load_versions(self):
        """Φόρτωση εκδόσεων από τη βάση δεδομένων"""
        try:
            self.versions = self.db_manager.get_contract_versions(self.contract_id)
            self.display_versions()
        except Exception as e:
            logger.error(f"Error loading versions: {e}", exc_info=True)
            self._show_messagebox("error", "Σφάλμα", f"Αποτυχία φόρτωσης εκδόσεων: {str(e)}")
    
    def display_versions(self):
        """Εμφάνιση λίστας εκδόσεων"""
        # Καθαρισμός προηγούμενης λίστας
        for widget in self.versions_frame.winfo_children():
            widget.destroy()
        
        if not self.versions:
            ctk.CTkLabel(
                self.versions_frame,
                text="Δεν υπάρχουν εκδόσεις ακόμα",
                text_color="#999"
            ).pack(pady=20)
            return
        
        for version in self.versions:
            self.create_version_item(version)
    
    def create_version_item(self, version: Dict[str, Any]):
        """Δημιουργία item για κάθε έκδοση"""
        is_selected = version['id'] == self.selected_version_id
        
        item_frame = ctk.CTkFrame(
            self.versions_frame,
            fg_color=self.theme_colors["secondary"] if is_selected else "#e8e8e8",
            corner_radius=8,
            border_width=2 if is_selected else 0,
            border_color=self.theme_colors["primary"]
        )
        item_frame.pack(fill="x", pady=5)
        
        # Προσθήκη hover effect με mouse events
        def on_enter(e):
            if not is_selected:
                item_frame.configure(fg_color="#d0d0d0")
        
        def on_leave(e):
            if not is_selected:
                item_frame.configure(fg_color="#e8e8e8")
        
        def on_click(e):
            self.select_version(version['id'])
        
        item_frame.bind("<Enter>", on_enter)
        item_frame.bind("<Leave>", on_leave)
        item_frame.bind("<Button-1>", on_click)
        
        # Version number and date
        version_num = version['version_number']
        created_at = version['created_at']
        
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            date_str = dt.strftime("%d/%m/%Y %H:%M")
        except:
            date_str = created_at
        
        text_color = "white" if version['id'] == self.selected_version_id else "black"
        
        label_v = ctk.CTkLabel(
            item_frame,
            text=f"v{version_num}",
            font=("Roboto", 12, "bold"),
            text_color=text_color
        )
        label_v.pack(anchor="w", padx=10, pady=(8, 2))
        label_v.bind("<Button-1>", on_click)
        
        label_d = ctk.CTkLabel(
            item_frame,
            text=date_str,
            font=("Roboto", 10),
            text_color=text_color
        )
        label_d.pack(anchor="w", padx=10, pady=(0, 2))
        label_d.bind("<Button-1>", on_click)
        
        if version.get('created_by') and version['created_by'] != 'System':
            label_a = ctk.CTkLabel(
                item_frame,
                text=f"Από: {version['created_by']}",
                font=("Roboto", 9),
                text_color=text_color
            )
            label_a.pack(anchor="w", padx=10, pady=(0, 2))
            label_a.bind("<Button-1>", on_click)
        
        if version.get('change_description'):
            desc_text = version['change_description']
            if len(desc_text) > 35:
                desc_text = desc_text[:32] + "..."
            
            label_c = ctk.CTkLabel(
                item_frame,
                text=desc_text,
                font=("Roboto", 9),
                text_color=text_color,
                wraplength=200
            )
            label_c.pack(anchor="w", padx=10, pady=(0, 8))
            label_c.bind("<Button-1>", on_click)
    
    def select_version(self, version_id: str):
        """Επιλογή έκδοσης για προβολή λεπτομερειών"""
        self.selected_version_id = version_id
        self.display_versions()
        self.display_version_details()
    
    def display_version_details(self):
        """Εμφάνιση λεπτομερειών επιλεγμένης έκδοσης"""
        # Καθαρισμός προηγούμενων λεπτομερειών
        for widget in self.details_frame.winfo_children():
            widget.destroy()
        
        if not self.selected_version_id:
            ctk.CTkLabel(
                self.details_frame,
                text="Επιλέξτε μία έκδοση για προβολή",
                text_color="#999"
            ).pack(pady=50)
            return
        
        # Λήψη δεδομένων έκδοσης
        version_data = self.db_manager.get_version_data(self.selected_version_id)
        
        if not version_data:
            ctk.CTkLabel(
                self.details_frame,
                text="Δεν ήταν δυνατή η φόρτωση των δεδομένων",
                text_color="#999"
            ).pack(pady=50)
            return
        
        # Εμφάνιση δεδομένων
        from constants import SPECIAL_FIELD_TRANSLATIONS
        
        # Κύρια πεδία
        main_fields = ['provider', 'number', 'date', 'expiry_date', 'type', 'months', 'comments']
        
        for field in main_fields:
            if field in version_data:
                value = version_data[field]
                
                # Μετάφραση ονόματος πεδίου
                field_display = {
                    'provider': 'Πάροχος',
                    'number': 'Αριθμός',
                    'date': 'Ημερομηνία',
                    'expiry_date': 'Ημερομηνία Λήξης',
                    'type': 'Τύπος',
                    'months': 'Διάρκεια (μήνες)',
                    'comments': 'Σχόλια'
                }.get(field, field)
                
                frame = ctk.CTkFrame(self.details_frame, fg_color="transparent")
                frame.pack(fill="x", padx=10, pady=5)
                
                label = f"{field_display}:"
                ctk.CTkLabel(
                    frame,
                    text=label,
                    font=("Roboto", 11, "bold"),
                    text_color=self.theme_colors["primary"],
                    width=150,
                    anchor="w"
                ).pack(side="left")
                
                value_str = str(value) if value else "—"
                if len(value_str) > 50:
                    value_str = value_str[:47] + "..."
                
                ctk.CTkLabel(
                    frame,
                    text=value_str,
                    font=("Roboto", 10),
                    text_color="black",
                    wraplength=300,
                    justify="left"
                ).pack(side="left", fill="x", expand=True)
        
        # Special fields
        special_data_str = version_data.get('special_data', '{}')
        if special_data_str and special_data_str != '{}':
            try:
                import json
                special_data = json.loads(special_data_str)
                
                if special_data:
                    sep = ctk.CTkFrame(self.details_frame, fg_color="#ddd", height=1)
                    sep.pack(fill="x", pady=10, padx=10)
                    
                    ctk.CTkLabel(
                        self.details_frame,
                        text="Πρόσθετα Πεδία",
                        font=("Roboto", 10, "bold"),
                        text_color=self.theme_colors["primary"]
                    ).pack(anchor="w", padx=10, pady=(5, 5))
                    
                    for key, value in special_data.items():
                        frame = ctk.CTkFrame(self.details_frame, fg_color="transparent")
                        frame.pack(fill="x", padx=10, pady=3)
                        
                        field_display = SPECIAL_FIELD_TRANSLATIONS.get(key, key)
                        
                        ctk.CTkLabel(
                            frame,
                            text=f"{field_display}:",
                            font=("Roboto", 10, "bold"),
                            text_color=self.theme_colors["secondary"],
                            width=150,
                            anchor="w"
                        ).pack(side="left")
                        
                        value_str = str(value) if value else "—"
                        if len(value_str) > 50:
                            value_str = value_str[:47] + "..."
                        
                        ctk.CTkLabel(
                            frame,
                            text=value_str,
                            font=("Roboto", 9),
                            wraplength=300,
                            justify="left"
                        ).pack(side="left", fill="x", expand=True)
            except:
                pass
    
    def restore_version(self):
        """Επαναφορά της σύμβασης σε επιλεγμένη έκδοση"""
        if not self.selected_version_id:
            self._show_messagebox("warning", "Προειδοποίηση", "Επιλέξτε μία έκδοση για επαναφορά")
            return
        
        # Λήψη πληροφοριών έκδοσης
        version_info = next(
            (v for v in self.versions if v['id'] == self.selected_version_id),
            None
        )
        
        if not version_info:
            return
        
        if self._show_messagebox(
            "yesno",
            "Επιβεβαίωση",
            f"Θέλετε να επαναφέρετε τη σύμβαση στην έκδοση {version_info['version_number']};\n\n"
            f"Η τρέχουσα έκδοση θα αποθηκευτεί ως νέα έκδοση."
        ):
            try:
                success = self.db_manager.restore_contract_version(self.selected_version_id)
                
                if success:
                    show_notification(f"✓ Η σύμβαση επαναφέρθηκε στην έκδοση {version_info['version_number']}!", "success")
                    self.load_versions()
                else:
                    self._show_messagebox("error", "Σφάλμα", "Αποτυχία επαναφοράς της σύμβασης")
            except Exception as e:
                logger.error(f"Error restoring version: {e}", exc_info=True)
                self._show_messagebox("error", "Σφάλμα", f"Σφάλμα κατά την επαναφορά: {str(e)}")
    
    def compare_versions(self):
        """Σύγκριση με προηγούμενη έκδοση"""
        if not self.selected_version_id:
            self._show_messagebox("warning", "Προειδοποίηση", "Επιλέξτε μία έκδοση")
            return
        
        # Λήψη πληροφοριών έκδοσης
        version_info = next(
            (v for v in self.versions if v['id'] == self.selected_version_id),
            None
        )
        
        if not version_info:
            return
        
        # Αναζήτηση προηγούμενης έκδοσης
        current_idx = next(
            (i for i, v in enumerate(self.versions) if v['id'] == self.selected_version_id),
            None
        )
        
        if current_idx is None or current_idx >= len(self.versions) - 1:
            self._show_messagebox("info", "Πληροφορία", "Δεν υπάρχει προηγούμενη έκδοση για σύγκριση")
            return
        
        prev_version = self.versions[current_idx + 1]
        
        # Λήψη αλλαγών
        changes = self.db_manager.get_version_changes(
            self.selected_version_id,
            prev_version['id']
        )
        
        # Δημιουργία παραθύρου σύγκρισης
        self.show_comparison_window(version_info, prev_version, changes)
    
    def show_comparison_window(self, current_version: Dict, prev_version: Dict, changes: Dict):
        """Εμφάνιση παραθύρου σύγκρισης"""
        comp_window = ctk.CTkToplevel(self)
        comp_window.title(f"Σύγκριση v{current_version['version_number']} με v{prev_version['version_number']}")
        comp_window.geometry("700x500")
        comp_window.transient(self)
        comp_window.grab_set()
        
        # Header
        header_frame = ctk.CTkFrame(comp_window, fg_color=self.theme_colors["primary"])
        header_frame.pack(fill="x", padx=0, pady=0)
        
        ctk.CTkLabel(
            header_frame,
            text=f"Αλλαγές από v{prev_version['version_number']} σε v{current_version['version_number']}",
            font=("Roboto", 14, "bold"),
            text_color="white"
        ).pack(side="left", padx=15, pady=10)
        
        # Content
        content_frame = ctk.CTkScrollableFrame(comp_window, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        if not changes.get('differences'):
            ctk.CTkLabel(
                content_frame,
                text="Δεν υπάρχουν διαφορές μεταξύ των εκδόσεων",
                text_color="#999"
            ).pack(pady=50)
            return
        
        from constants import SPECIAL_FIELD_TRANSLATIONS
        
        for field, change in changes['differences'].items():
            frame = ctk.CTkFrame(content_frame, fg_color="#f5f5f5", corner_radius=8, border_width=1, border_color="#ddd")
            frame.pack(fill="x", pady=8)
            
            field_display = SPECIAL_FIELD_TRANSLATIONS.get(field, field)
            
            ctk.CTkLabel(
                frame,
                text=f"📝 {field_display}",
                font=("Roboto", 11, "bold"),
                text_color=self.theme_colors["primary"]
            ).pack(anchor="w", padx=10, pady=(8, 5))
            
            from_val = str(change['from']) if change['from'] else "—"
            to_val = str(change['to']) if change['to'] else "—"
            
            inner_frame = ctk.CTkFrame(frame, fg_color="transparent")
            inner_frame.pack(fill="x", padx=10, pady=(0, 8))
            
            ctk.CTkLabel(
                inner_frame,
                text="Από:",
                font=("Roboto", 10, "bold"),
                text_color="#e74c3c"
            ).pack(anchor="w", pady=(0, 2))
            
            ctk.CTkLabel(
                inner_frame,
                text=from_val,
                font=("Roboto", 9),
                text_color="#555",
                wraplength=600,
                justify="left"
            ).pack(anchor="w", padx=10, pady=(0, 8))
            
            ctk.CTkLabel(
                inner_frame,
                text="Σε:",
                font=("Roboto", 10, "bold"),
                text_color="#27ae60"
            ).pack(anchor="w", pady=(0, 2))
            
            ctk.CTkLabel(
                inner_frame,
                text=to_val,
                font=("Roboto", 9),
                text_color="#555",
                wraplength=600,
                justify="left"
            ).pack(anchor="w", padx=10)
    
    def delete_version(self):
        """Διαγραφή επιλεγμένης έκδοσης"""
        if not self.selected_version_id:
            self._show_messagebox("warning", "Προειδοποίηση", "Επιλέξτε μία έκδοση για διαγραφή")
            return
        
        version_info = next(
            (v for v in self.versions if v['id'] == self.selected_version_id),
            None
        )
        
        if not version_info:
            return
        
        if self._show_messagebox(
            "yesno",
            "Επιβεβαίωση",
            f"Θέλετε να διαγράψετε την έκδοση {version_info['version_number']};"
        ):
            try:
                if self.db_manager.delete_contract_version(self.selected_version_id):
                    show_notification(f"✓ Η έκδοση {version_info['version_number']} διαγράφηκε επιτυχώς!", "success")
                    self.selected_version_id = None
                    self.load_versions()
                else:
                    self._show_messagebox("error", "Σφάλμα", "Αποτυχία διαγραφής της έκδοσης")
            except Exception as e:
                logger.error(f"Error deleting version: {e}", exc_info=True)
                self._show_messagebox("error", "Σφάλμα", f"Σφάλμα κατά τη διαγραφή: {str(e)}")
    
    def toggle_maximize(self):
        """Maximize/Restore παράθυρο"""
        if not self.is_maximized:
            # Maximize
            self.state('zoomed')
            self.is_maximized = True
        else:
            # Restore
            self.state('normal')
            self.is_maximized = False
