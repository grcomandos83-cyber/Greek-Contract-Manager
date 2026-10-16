import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
from tkcalendar import DateEntry
import json
import os
import shutil
import uuid
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

from constants import COLOR_THEMES, PDF_FOLDER, SETTINGS_FILE, SPECIAL_FIELD_TRANSLATIONS
from utils import validate_date, calculate_expiry_date, get_resource_path, get_contract_status
from signals import SignalManager, Signals
from contract_versions_view import ContractVersionsWindow
from mixins import MessageBoxMixin
from notification_system import show_notification

# =========================================================================
# === ΚΛΑΣΗ: ΔΙΑΧΕΙΡΙΣΗ ΚΑΤΗΓΟΡΙΩΝ (ΝΕΟ) ===
# =========================================================================

class CategoryManagerWindow(MessageBoxMixin, ctk.CTkToplevel):
    def __init__(self, master: Any, categories: List[str], db_manager: Any, on_close_callback: Optional[Any] = None):
        super().__init__(master)
        
        import os
        try:
            self.iconbitmap(get_resource_path(os.path.join("assets", "app.ico")))
        except Exception:
            pass
            
        self.categories = categories
        self.db_manager = db_manager
        self.on_close_callback = on_close_callback
        
        self.title("Διαχείριση Ειδών")
        self.geometry("400x500")
        
        # Κεντράρισμα σε σχέση με το master αν είναι δυνατόν, αλλιώς στην οθόνη
        try:
            x = master.winfo_x() + 50
            y = master.winfo_y() + 50
        except:
            x = (self.winfo_screenwidth() // 2) - 200
            y = (self.winfo_screenheight() // 2) - 250
            
        self.geometry(f"+{x}+{y}")
        
        self.transient(master)
        self.grab_set()
        self.attributes("-topmost", True)
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self._setup_ui()

    def _setup_ui(self):
        ctk.CTkLabel(self, text="Επεξεργασία Λίστας", font=("Roboto", 18, "bold")).pack(pady=10)
        ctk.CTkButton(self, text="+ Νέο Είδος", command=self.add_category_dialog, fg_color="green").pack(pady=5, padx=20, fill="x")
        
        self.cat_scroll = ctk.CTkScrollableFrame(self, label_text="Υπάρχοντα Είδη")
        self.cat_scroll.pack(pady=10, padx=20, fill="both", expand=True)
        
        self.refresh_list()

    def refresh_list(self):
        for widget in self.cat_scroll.winfo_children(): widget.destroy()
        for cat in self.categories:
            row = ctk.CTkFrame(self.cat_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=cat, anchor="w").pack(side="left", padx=5)
            
            btn_del = ctk.CTkButton(row, text="🗑", width=30, fg_color="#c0392b", command=lambda c=cat: self.delete_category(c))
            btn_del.pack(side="right", padx=2)
            
            btn_edit = ctk.CTkButton(row, text="✎", width=30, fg_color="#d35400", command=lambda c=cat: self.edit_category_dialog(c))
            btn_edit.pack(side="right", padx=2)

    def add_category_dialog(self):
        self.attributes("-topmost", False)
        new_type = ctk.CTkInputDialog(text="Όνομα νέου είδους:", title="Προσθήκη").get_input()
        self.attributes("-topmost", True)

        if new_type:
            new_type = new_type.strip()
            if new_type and new_type not in self.categories:
                self.categories.append(new_type)
                self._save_settings()
                self.refresh_list()
                SignalManager.emit(Signals.CATEGORIES_UPDATED)
            elif new_type in self.categories:
                self._show_messagebox("warning", "Προσοχή", "Το είδος υπάρχει ήδη.")

    def edit_category_dialog(self, old_name: str):
        affected_count_preview = 0
        try:
            pre_check = self.db_manager.get_contracts_by_type(old_name)
            affected_count_preview = len(pre_check)
        except Exception:
            affected_count_preview = 0

        prompt_text = f"Μετονομασία '{old_name}' σε:"
        if affected_count_preview > 0:
            prompt_text = (
                f"⚠ ΠΡΟΣΟΧΗ: Το είδος '{old_name}' χρησιμοποιείται σε {affected_count_preview} "
                f"συμβάσεις.\nΌλες θα ενημερωθούν αυτόματα.\n\n"
                f"Μετονομασία '{old_name}' σε:"
            )

        self.attributes("-topmost", False)
        dlg = ctk.CTkInputDialog(text=prompt_text, title="Επεξεργασία Είδους")
        new_name = dlg.get_input()
        self.attributes("-topmost", True)

        if new_name:
            new_name = new_name.strip()
            if new_name and new_name != old_name:
                if new_name in self.categories:
                    self._show_messagebox("error", "Σφάλμα", "Υπάρχει ήδη κατηγορία με αυτό το όνομα.")
                    return
                index = self.categories.index(old_name)
                self.categories[index] = new_name
                self._save_settings()

                try:
                    updated_count, updated_ids = self.db_manager.rename_category_in_contracts(old_name, new_name)
                except Exception as db_err:
                    self._show_messagebox(
                        "error",
                        "Σφάλμα Βάσης Δεδομένων",
                        f"Αποτυχία ενημέρωσης συμβάσεων:\n{str(db_err)}"
                    )
                    return

                self.refresh_list()
                rename_info = {
                    "action": "rename",
                    "old_name": old_name,
                    "new_name": new_name,
                    "updated_count": updated_count,
                    "updated_ids": updated_ids
                }
                SignalManager.emit(Signals.CATEGORIES_UPDATED, rename_info)
                SignalManager.emit(Signals.CONTRACT_UPSERTED, {"bulk_rename": True, "info": rename_info})

                if updated_count > 0:
                    msg = (
                        f"Το είδος μετονομάστηκε με επιτυχία.\n\n"
                        f"Ενημερώθηκαν αυτόματα: {updated_count} συμβάσεις.\n"
                        f"Δημιουργήθηκαν και αντίστοιχες εκδόσεις (versions) για κάθε ενημερωμένη σύμβαση."
                    )
                else:
                    msg = "Το είδος μετονομάστηκε. Δεν υπήρχαν συμβάσεις να ενημερωθούν."

                self._show_messagebox("info", "Επιτυχία", msg)

    def delete_category(self, cat_name: str):
        if self._show_messagebox("yesno", "Διαγραφή", f"Διαγραφή κατηγορίας '{cat_name}';"):
            self.categories.remove(cat_name)
            self._save_settings()
            self.refresh_list()
            SignalManager.emit(Signals.CATEGORIES_UPDATED)

    def _save_settings(self):
        settings = {"categories": self.categories}
        try:
            # Note: This overwrites settings. We assume ContractApp handles partial reads or we read-modify-write.
            # To be safer we should read existing settings first, but for simplicity here strictly following existing logic pattern.
            # Ideally ContractApp passes a persist_callback.
            # We will try to preserve other settings if file exists.
            existing_settings = {}
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    existing_settings = json.load(f)
            
            existing_settings["categories"] = self.categories
            
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f: 
                json.dump(existing_settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def _on_close(self):
        self.destroy()
        if self.on_close_callback:
            self.on_close_callback()

# =========================================================================
# === ΚΛΑΣΗ: ΑΝΑΔΥΟΜΕΝΗ ΦΟΡΜΑ ΕΙΣΑΓΩΓΗΣ (UPDATED) ===
# =========================================================================

class ContractFormToplevel(MessageBoxMixin, ctk.CTkToplevel):
    def __init__(self, master: Any, db_manager: Any, categories: List[str], 
                 contract_to_edit: Optional[Dict[str, Any]] = None, 
                 current_theme: Optional[str] = None):
        super().__init__(master)
        
        import os
        try:
            self.iconbitmap(get_resource_path(os.path.join("assets", "app.ico")))
        except Exception:
            pass
            
        self.master = master
        self.db_manager = db_manager
        self.categories = categories
        self.contract_to_edit = contract_to_edit
        self.current_theme = current_theme or "Minimalist"
        
        self.special_fields: Dict[str, Any] = {}
        self.result_contract: Optional[Dict[str, Any]] = None
        
        self.title_text = "Νέα Σύμβαση" if contract_to_edit is None else "Επεξεργασία Σύμβασης"
        self.title(self.title_text)

        self.width = 500
        self.height = 600
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (self.width // 2)
        y = (screen_height // 2) - (self.height // 2)
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")
        
        self.transient(master) 
        self.attributes("-topmost", True)
        self.grab_set() 

        self.grid_columnconfigure(0, weight=1)
        
        self._setup_form()
        
        # Subscribe to category changes
        SignalManager.subscribe(Signals.CATEGORIES_UPDATED, self._on_categories_signal)
        
        if self.contract_to_edit:
            self._load_edit_data(contract_to_edit)

    def _on_categories_signal(self, data=None):
        self._update_combo_box(data)

    def destroy(self):
        # Unsubscribe before closing
        SignalManager.unsubscribe(Signals.CATEGORIES_UPDATED, self._on_categories_signal)
        super().destroy()
            
    def _setup_form(self) -> None:
        # Use scrollable frame for main content
        main_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.lbl_mode = ctk.CTkLabel(main_frame, text=self.title_text, font=("Roboto", 20, "bold"))
        self.lbl_mode.pack(pady=10)
        
        def create_aligned_entry(parent, label_text, placeholder="") -> ctk.CTkEntry:
            row_frame = ctk.CTkFrame(parent, fg_color="transparent")
            row_frame.pack(pady=4, padx=0, fill="x")
            ctk.CTkLabel(row_frame, text=label_text, width=150, anchor="w").pack(side="left")
            entry = ctk.CTkEntry(row_frame, placeholder_text=placeholder)
            entry.pack(side="right", fill="x", expand=True)
            return entry

        self.entry_provider = create_aligned_entry(main_frame, "Όνομα Παρόχου:", "Πάροχος")
        self.entry_number = create_aligned_entry(main_frame, "Αριθμός Σύμβασης:", "Αριθμός")
        
        date_frame_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        date_frame_row.pack(pady=4, padx=0, fill="x")
        ctk.CTkLabel(date_frame_row, text="Ημερομηνία Σύμβασης:", width=150, anchor="w").pack(side="left")

        theme_colors = COLOR_THEMES.get(self.current_theme, COLOR_THEMES["Minimalist"])
        self.entry_date = DateEntry(date_frame_row, 
                                    date_pattern='dd/mm/yyyy',
                                    width=12, 
                                    background=theme_colors['primary'], 
                                    foreground='white', 
                                    borderwidth=2,
                                    font=("Roboto", 12))
        self.entry_date.pack(side="right", fill="x", expand=True)
        self.entry_date.set_date(datetime.now())

        self.entry_months = create_aligned_entry(main_frame, "Διάρκεια (Μήνες):", "Σε μήνες")

        type_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        type_frame.pack(pady=8, padx=0, fill="x")
        ctk.CTkLabel(type_frame, text="Είδος Σύμβασης:", width=150, anchor="w").pack(side="left")
        self.combo_type = ctk.CTkComboBox(type_frame, values=self.categories, command=self.show_dynamic_fields)
        self.combo_type.set(self.categories[0] if self.categories else "Επιλέξτε Είδος")
        self.combo_type.pack(side="left", fill="x", expand=True)
        
        btn_manage = ctk.CTkButton(type_frame, text="⚙", width=30, command=self.open_category_manager, fg_color="#444")
        btn_manage.pack(side="right", padx=(5, 0))
        
        self.dynamic_fields_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.dynamic_fields_frame.pack(pady=5, padx=0, fill="x")
        
        comments_label = ctk.CTkLabel(main_frame, text="Σχόλια - Παρατηρήσεις:", anchor="w")
        comments_label.pack(pady=(10, 5), fill="x")
        self.text_comments = ctk.CTkTextbox(main_frame, height=80)
        self.text_comments.pack(pady=(0, 8), fill="x")

        # Multiple PDF support
        self.selected_pdf_paths: List[str] = []
        
        pdf_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        pdf_frame.pack(pady=10, fill="x")
        
        self.btn_pdf = ctk.CTkButton(pdf_frame, text="Επιλογή Αρχείων PDF 📎",
                                     command=self._select_pdf_files, fg_color="#555")
        self.btn_pdf.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_clear_pdfs = ctk.CTkButton(pdf_frame, text="🗑", width=40,
                                            command=self._clear_pdfs, fg_color="#d9534f")
        self.btn_clear_pdfs.pack(side="right")
        
        # PDF list display
        self.pdf_list_frame = ctk.CTkScrollableFrame(main_frame, height=50, fg_color="transparent")
        self.pdf_list_frame.pack(pady=(0, 5), fill="x")

        action_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        action_row.pack(pady=10, fill="x")
        
        ctk.CTkButton(action_row, text="Αποθήκευση", command=self._save_and_close, 
                     fg_color=theme_colors["primary"]).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # Κουμπί διαχείρισης εκδόσεων (μόνο για υπάρχουσες συμβάσεις)
        if self.contract_to_edit:
            ctk.CTkButton(action_row, text="📋 Εκδόσεις", command=self._show_versions, 
                         fg_color="#8e44ad", width=100).pack(side="left", padx=(0, 5))
        
        ctk.CTkButton(action_row, text="Ακύρωση", command=self.destroy, 
                     fg_color="transparent", border_width=1, border_color="red", text_color="red").pack(side="right", fill="x", expand=True, padx=(5, 0))

        self.show_dynamic_fields(self.combo_type.get())

    def _load_edit_data(self, contract: Dict[str, Any]) -> None:
        self.entry_provider.insert(0, contract.get('provider', ''))
        self.entry_number.insert(0, contract.get('number', ''))
        self.entry_months.insert(0, contract.get('months', ''))
        self.combo_type.set(contract.get('type', self.categories[0] if self.categories else "Επιλέξτε Είδος"))
        
        self.entry_date.delete(0, 'end')
        self.entry_date.insert(0, contract.get('date', datetime.now().strftime('%d/%m/%Y'))) 

        self.text_comments.delete("1.0", "end")
        self.text_comments.insert("0.0", contract.get('comments', ''))
        
        # Load multiple PDFs
        pdf_paths = contract.get('pdf_paths', [])
        if not pdf_paths and contract.get('pdf_path'):
            # Backward compatibility: convert single pdf_path to list
            pdf_paths = [contract.get('pdf_path')]
        
        self.selected_pdf_paths = pdf_paths if pdf_paths else []
        self._update_pdf_list_display()

        self.show_dynamic_fields(contract.get('type', ''))
        
        special_data_str = contract.get('special_data', '{}')
        if special_data_str:
            try:
                special_data = json.loads(special_data_str) if isinstance(special_data_str, str) else special_data_str
                while isinstance(special_data, str):
                    try:
                        special_data = json.loads(special_data)
                    except Exception:
                        break
                if isinstance(special_data, dict):
                    for key, value in special_data.items():
                        if key in self.special_fields:
                            widget = self.special_fields[key]
                            if isinstance(widget, ctk.CTkEntry):
                                widget.insert(0, value)
            except Exception:
                pass

    def show_dynamic_fields(self, choice: str) -> None:
        for widget in self.dynamic_fields_frame.winfo_children():
            widget.destroy()
        
        self.special_fields = {}

        def create_dynamic_entry(placeholder_text: str) -> ctk.CTkEntry:
            entry = ctk.CTkEntry(self.dynamic_fields_frame, placeholder_text=placeholder_text)
            entry.pack(pady=5, fill="x")
            return entry

        from constants import CATEGORY_DYNAMIC_FIELDS
        fields_config = CATEGORY_DYNAMIC_FIELDS.get(choice, {})
        for field_key, field_label in fields_config.items():
            self.special_fields[field_key] = create_dynamic_entry(field_label)

        # Removed pack() and pack_forget() to maintain original layout position.

    def _select_pdf_files(self) -> None:
        """Επιλογή πολλαπλών αρχείων PDF"""
        self.attributes("-topmost", False)
        self.grab_release()
        filenames = filedialog.askopenfilenames(parent=self.master, filetypes=[("PDF files", "*.pdf")])
        self.grab_set()
        self.attributes("-topmost", True)
        
        if filenames:
            # Add new files to the list (avoid duplicates)
            for filename in filenames:
                if filename not in self.selected_pdf_paths:
                    self.selected_pdf_paths.append(filename)
            self._update_pdf_list_display()
    
    def _clear_pdfs(self) -> None:
        """Καθαρισμός όλων των επιλεγμένων PDF"""
        self.selected_pdf_paths = []
        self._update_pdf_list_display()
    
    def _remove_pdf(self, pdf_path: str) -> None:
        """Αφαίρεση συγκεκριμένου PDF από τη λίστα"""
        if pdf_path in self.selected_pdf_paths:
            self.selected_pdf_paths.remove(pdf_path)
            self._update_pdf_list_display()
    
    def _update_pdf_list_display(self) -> None:
        """Ενημέρωση της εμφάνισης της λίστας PDF"""
        # Clear existing widgets
        for widget in self.pdf_list_frame.winfo_children():
            widget.destroy()
        
        if not self.selected_pdf_paths:
            ctk.CTkLabel(self.pdf_list_frame, text="Δεν έχουν επιλεγεί αρχεία PDF",
                        text_color="gray", font=("Roboto", 11)).pack(pady=3)
            self.btn_pdf.configure(text="Επιλογή Αρχείων PDF 📎", fg_color="#555")
        else:
            self.btn_pdf.configure(text=f"PDF: {len(self.selected_pdf_paths)} αρχεία ✓",
                                  fg_color="#2fa572")
            
            for pdf_path in self.selected_pdf_paths:
                pdf_frame = ctk.CTkFrame(self.pdf_list_frame, fg_color=("#e0e0e0", "#2b2b2b"),
                                        corner_radius=6, border_width=1,
                                        border_color=("#cccccc", "#444444"))
                pdf_frame.pack(fill="x", pady=2, padx=2)
                
                filename = os.path.basename(pdf_path)
                ctk.CTkLabel(pdf_frame, text=f"📄 {filename}", anchor="w",
                           font=("Roboto", 11)).pack(side="left", fill="x", expand=True, padx=5, pady=3)
                
                ctk.CTkButton(pdf_frame, text="✖", width=25, height=20, fg_color="#d9534f",
                             hover_color="#c0392b", corner_radius=4,
                             command=lambda p=pdf_path: self._remove_pdf(p)).pack(side="right", padx=3, pady=2)

    def _save_and_close(self) -> None:
        provider = self.entry_provider.get()
        number = self.entry_number.get()
        date = self.entry_date.get()
        months = self.entry_months.get()
        c_type = self.combo_type.get()
        comments = self.text_comments.get("1.0", "end-1c").strip()
        
        if not provider or not number:
            self._show_messagebox("error", "Σφάλμα", "Απαιτείται Όνομα Παρόχου και Αριθμός.")
            return

        if not validate_date(date):
            self._show_messagebox("error", "Σφάλμα Ημερομηνίας", "Παρακαλώ εισάγετε έγκυρη Ημερομηνία Σύμβασης (DD/MM/YYYY).")
            return

        is_months_valid = months.isdigit() and int(months) > 0
        expiry_date = calculate_expiry_date(date, months) if is_months_valid else None
        
        # Process multiple PDF files
        final_pdf_paths = []
        
        # Get existing PDF paths if editing
        existing_pdf_paths = []
        if self.contract_to_edit:
            existing_pdf_paths = self.contract_to_edit.get('pdf_paths', [])
            if not existing_pdf_paths and self.contract_to_edit.get('pdf_path'):
                existing_pdf_paths = [self.contract_to_edit.get('pdf_path')]
        
        for pdf_path in self.selected_pdf_paths:
            try:
                # Check if this is an existing file (already in PDF_FOLDER)
                if pdf_path in existing_pdf_paths or pdf_path.startswith(PDF_FOLDER):
                    final_pdf_paths.append(pdf_path)
                else:
                    # New file - copy to PDF_FOLDER
                    file_name = os.path.basename(pdf_path)
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    # Add a counter to avoid duplicates when multiple files are selected
                    counter = len(final_pdf_paths)
                    new_filename = f"{timestamp}_{counter}_{file_name}"
                    destination = os.path.join(PDF_FOLDER, new_filename)
                    
                    if not os.path.exists(destination):
                        shutil.copy(pdf_path, destination)
                    final_pdf_paths.append(destination)
                    
            except Exception as e:
                self._show_messagebox("error", "Σφάλμα PDF",
                                   f"Αποτυχία αντιγραφής PDF {os.path.basename(pdf_path)}: {e}")
                return

        special_data = {}
        for key, widget in self.special_fields.items():
            if isinstance(widget, ctk.CTkEntry):
                value = widget.get().strip()
                if value: special_data[key] = value
        
        new_id = self.contract_to_edit['id'] if self.contract_to_edit else str(uuid.uuid4())
        
        # Backward compatibility: keep pdf_path for first PDF
        first_pdf = final_pdf_paths[0] if final_pdf_paths else ""
        
        self.result_contract = {
            'id': new_id,
            'provider': provider, 'number': number, 'date': date,
            'months': months, 'type': c_type, 'comments': comments,
            'expiry_date': expiry_date,
            'pdf_path': first_pdf,  # Backward compatibility
            'pdf_paths': final_pdf_paths,  # New multiple PDF support
            'special_data': special_data
        }
        
        # Δημιουργία έκδοσης αν είναι ενημέρωση (όχι νέα σύμβαση)
        if self.contract_to_edit:
            try:
                change_desc = "Ενημέρωση σύμβασης"
                self.db_manager.create_contract_version(
                    self.result_contract,
                    change_desc,
                    "Χρήστης"
                )
            except Exception as e:
                print(f"Warning: Could not create version: {e}")
        
        self.destroy() 

    def open_category_manager(self) -> None:
        self.attributes("-topmost", False) 
        
        # The window now updates via signals, no callback needed here for data.
        # But we still want to reset topmost.
        def on_manager_close():
             self.attributes("-topmost", True)

        CategoryManagerWindow(self, self.categories, self.db_manager, on_close_callback=on_manager_close)

    def _update_combo_box(self, data=None) -> None:
        self.combo_type.configure(values=self.categories)
        if self.categories:
            current = self.combo_type.get()

            renamed_to = None
            if isinstance(data, dict) and data.get("action") == "rename":
                old_name = data.get("old_name")
                new_name = data.get("new_name")
                if (old_name and current and
                    current.strip().lower() == old_name.strip().lower() and
                    new_name in self.categories):
                    renamed_to = new_name

            if renamed_to is not None:
                self.combo_type.set(renamed_to)
                self.show_dynamic_fields(renamed_to)
            elif current not in self.categories:
                self.combo_type.set(self.categories[0])
                self.show_dynamic_fields(self.categories[0])
        else:
            self.combo_type.set("")
    
    def _show_versions(self) -> None:
        """Εμφάνιση παραθύρου διαχείρισης εκδόσεων"""
        if not self.contract_to_edit:
            self._show_messagebox("warning", "Προειδοποίηση", "Μπορείτε να δείτε εκδόσεις μόνο για υπάρχουσες συμβάσεις")
            return
        
        try:
            contract_name = self.entry_provider.get() or "Σύμβαση"
            theme_colors = COLOR_THEMES.get(self.current_theme, COLOR_THEMES["Minimalist"])
            
            ContractVersionsWindow(
                self,
                self.db_manager,
                self.contract_to_edit['id'],
                contract_name,
                theme_colors
            )
        except Exception as e:
            self._show_messagebox("error", "Σφάλμα", f"Αποτυχία ανοίγματος εκδόσεων: {str(e)}")

# =========================================================================
# === ΚΛΑΣΗ: ΠΑΡΑΘΥΡΟ ΠΡΟΧΩΡΗΜΕΝΗΣ ΑΝΑΖΗΤΗΣΗΣ ===
# =========================================================================

class AdvancedSearchToplevel(MessageBoxMixin, ctk.CTkToplevel):
    STATUS_MAP: Dict[str, str] = {
        "Όλες": "Όλες",
        "Ενεργές": "ACTIVE",
        "Λήγουν Σύντομα": "EXPIRING_SOON",
        "Ληγμένες": "EXPIRED",
        "Χωρίς Ημ/νία": "NO_DATE"
    }

    def __init__(self, master: Any, db_manager: Any, categories: List[str], current_theme: Optional[str] = None):
        super().__init__(master)
        
        import os
        try:
            self.iconbitmap(get_resource_path(os.path.join("assets", "app.ico")))
        except Exception:
            pass
            
        self.master = master
        self.db_manager = db_manager
        self.categories = categories
        self.current_theme = current_theme or "Minimalist"
        self.search_results: List[Dict[str, Any]] = []
        
        # Pagination settings
        self.page_size = 50
        self.current_page = 1
        self.total_pages = 1
        
        self.title("Προχωρημένη Αναζήτηση")
        self.geometry("600x700")
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (600 // 2)
        y = (screen_height // 2) - (700 // 2)
        self.geometry(f"+{x}+{y}")
        
        self.transient(master)
        self.grab_set()
        self.attributes("-topmost", True)
        
        self.theme_colors = COLOR_THEMES.get(self.current_theme, COLOR_THEMES["Minimalist"])
        
        self._setup_advanced_search_ui()
        
        # Subscribe to category changes
        SignalManager.subscribe(Signals.CATEGORIES_UPDATED, self._on_categories_signal)

    def _on_categories_signal(self, data=None):
        # Master already reloads settings/categories if it's the main app,
        # but for safety we refresh our combo with newest data.
        valid_values = ["Όλα"] + self.categories
        self.combo_category.configure(values=valid_values)
        current = self.combo_category.get()

        if isinstance(data, dict) and data.get("action") == "rename":
            old_name = data.get("old_name")
            new_name = data.get("new_name")
            if (old_name and current and
                current.strip().lower() == old_name.strip().lower() and
                new_name in self.categories):
                self.combo_category.set(new_name)
                return

        if current and current not in valid_values:
            self.combo_category.set("Όλα")

    def destroy(self):
        # Unsubscribe before closing
        SignalManager.unsubscribe(Signals.CATEGORIES_UPDATED, self._on_categories_signal)
        super().destroy()
        
    def _setup_advanced_search_ui(self) -> None:
        main_frame = ctk.CTkScrollableFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(main_frame, text="Προχωρημένη Αναζήτηση", 
                     font=("Roboto", 20, "bold")).pack(pady=10)
        
        basic_frame = ctk.CTkFrame(main_frame)
        basic_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(basic_frame, text="Βασική Αναζήτηση", 
                     font=("Roboto", 16, "bold")).pack(pady=5)
        
        self.entry_search = ctk.CTkEntry(basic_frame, placeholder_text="🔍 Αναζήτηση σε ΟΛΑ τα πεδία...")
        self.entry_search.pack(fill="x", padx=10, pady=5)
        
        filter_frame = ctk.CTkFrame(main_frame)
        filter_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(filter_frame, text="Φίλτρα", 
                     font=("Roboto", 16, "bold")).pack(pady=5)
        
        filter_grid = ctk.CTkFrame(filter_frame, fg_color="transparent")
        filter_grid.pack(fill="x", padx=10, pady=5)
        filter_grid.columnconfigure(0, weight=1)
        filter_grid.columnconfigure(1, weight=1)
        
        ctk.CTkLabel(filter_grid, text="Είδος Σύμβασης:").grid(row=0, column=0, sticky="w", padx=5)
        self.combo_category = ctk.CTkComboBox(filter_grid, values=["Όλα"] + self.categories)
        self.combo_category.set("Όλα")
        self.combo_category.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        
        ctk.CTkLabel(filter_grid, text="Κατάσταση:").grid(row=1, column=0, sticky="w", padx=5)
        self.combo_status = ctk.CTkComboBox(filter_grid, 
                                          values=list(self.STATUS_MAP.keys()))
        self.combo_status.set("Όλες")
        self.combo_status.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        
        ctk.CTkLabel(filter_grid, text="PDF:").grid(row=2, column=0, sticky="w", padx=5)
        self.combo_pdf = ctk.CTkComboBox(filter_grid, values=["Όλες", "Με PDF", "Χωρίς PDF"])
        self.combo_pdf.set("Όλες")
        self.combo_pdf.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        
        date_frame = ctk.CTkFrame(main_frame)
        date_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(date_frame, text="Φίλτρα Ημερομηνίας", 
                     font=("Roboto", 16, "bold")).pack(pady=5)
        
        date_type_frame = ctk.CTkFrame(date_frame, fg_color="transparent")
        date_type_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(date_type_frame, text="Τύπος Ημερομηνίας:").pack(side="left")
        self.date_type_var = ctk.StringVar(value="date")
        ctk.CTkRadioButton(date_type_frame, text="Ημ/νία Σύμβασης", 
                          variable=self.date_type_var, value="date").pack(side="left", padx=10)
        ctk.CTkRadioButton(date_type_frame, text="Ημ/νία Λήξης", 
                          variable=self.date_type_var, value="expiry_date").pack(side="left", padx=10)
        
        date_range_frame = ctk.CTkFrame(date_frame, fg_color="transparent")
        date_range_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(date_range_frame, text="Από:").pack(side="left")
        self.entry_date_from = ctk.CTkEntry(date_range_frame, placeholder_text="ΗΗ/ΜΜ/ΕΕΕΕ", width=100)
        self.entry_date_from.pack(side="left", padx=5)
        
        ctk.CTkLabel(date_range_frame, text="Έως:").pack(side="left", padx=(20, 0))
        self.entry_date_to = ctk.CTkEntry(date_range_frame, placeholder_text="ΗΗ/ΜΜ/ΕΕΕΕ", width=100)
        self.entry_date_to.pack(side="left", padx=5)
        
        btn_today = ctk.CTkButton(date_range_frame, text="Σήμερα", width=80,
                                command=self.set_today_date)
        btn_today.pack(side="right", padx=5)
        
        special_frame = ctk.CTkFrame(main_frame)
        special_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(special_frame, text="Ειδικά Πεδία", 
                     font=("Roboto", 16, "bold")).pack(pady=5)
        
        self.special_fields = {}
        special_fields_grid = ctk.CTkFrame(special_frame, fg_color="transparent")
        special_fields_grid.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(special_fields_grid, text="Νομικό Πρόσωπο:").grid(row=0, column=0, sticky="w", padx=5)
        self.special_fields['legal_entity'] = ctk.CTkEntry(special_fields_grid, placeholder_text="Φίλτρο Νομικού Προσώπου")
        self.special_fields['legal_entity'].grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        
        ctk.CTkLabel(special_fields_grid, text="Πρόγραμμα:").grid(row=1, column=0, sticky="w", padx=5)
        self.special_fields['program'] = ctk.CTkEntry(special_fields_grid, placeholder_text="Φίλτρο Προγράμματος")
        self.special_fields['program'].grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        
        ctk.CTkLabel(special_fields_grid, text="Ίδρυμα:").grid(row=2, column=0, sticky="w", padx=5)
        self.special_fields['concerns_institute'] = ctk.CTkEntry(special_fields_grid, placeholder_text="Φίλτρο Ιδρύματος")
        self.special_fields['concerns_institute'].grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        
        special_fields_grid.columnconfigure(1, weight=1)
        
        action_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        action_frame.pack(fill="x", pady=20)
        
        ctk.CTkButton(action_frame, text="🔍 Εκτέλεση Αναζήτησης", 
                     command=self.execute_search,
                     fg_color=self.theme_colors["primary"]).pack(side="left", padx=5, fill="x", expand=True)
        
        ctk.CTkButton(action_frame, text="🧹 Καθαρισμός Φίλτρων", 
                     command=self.clear_filters,
                     fg_color="#7f8c8d").pack(side="left", padx=5, fill="x", expand=True)
        
        ctk.CTkButton(action_frame, text="✕ Κλείσιμο", 
                     command=self.destroy,
                     fg_color="#c0392b").pack(side="left", padx=5, fill="x", expand=True)
        
        results_frame = ctk.CTkFrame(main_frame)
        results_frame.pack(fill="both", expand=True, pady=10)
        
        ctk.CTkLabel(results_frame, text="Αποτελέσματα", 
                     font=("Roboto", 16, "bold")).pack(pady=5)
        
        self.results_label = ctk.CTkLabel(results_frame, text="Πατήστε 'Εκτέλεση Αναζήτησης' για αποτελέσματα")
        self.results_label.pack(pady=5)
        
        self.results_scroll = ctk.CTkScrollableFrame(results_frame, height=200)
        self.results_scroll.pack(fill="both", expand=True, padx=10, pady=5)
        
    def set_today_date(self) -> None:
        today = datetime.now().strftime('%d/%m/%Y')
        self.entry_date_to.delete(0, 'end')
        self.entry_date_to.insert(0, today)
        
        one_year_ago = (datetime.now() - relativedelta(years=1)).strftime('%d/%m/%Y')
        self.entry_date_from.delete(0, 'end')
        self.entry_date_from.insert(0, one_year_ago)
    
    def clear_filters(self) -> None:
        self.entry_search.delete(0, 'end')
        self.combo_category.set("Όλα")
        self.combo_status.set("Όλες")
        self.combo_pdf.set("Όλες")
        self.entry_date_from.delete(0, 'end')
        self.entry_date_to.delete(0, 'end')
        self.date_type_var.set("date")
        
        for field in self.special_fields.values():
            if isinstance(field, ctk.CTkEntry):
                field.delete(0, 'end')
        
        for widget in self.results_scroll.winfo_children():
            widget.destroy()
        self.results_label.configure(text="Πατήστε 'Εκτέλεση Αναζήτησης' για αποτελέσματα")
    
    def execute_search(self) -> None:
        try:
            raw_status = self.combo_status.get()
            mapped_status = self.STATUS_MAP.get(raw_status, raw_status)

            search_params: Dict[str, Any] = {
                'search_text': self.entry_search.get().strip(),
                'category_filter': self.combo_category.get(),
                'status_filter': mapped_status,
                'date_from': self.entry_date_from.get().strip(),
                'date_to': self.entry_date_to.get().strip(),
                'date_type': self.date_type_var.get(),
                'has_pdf': None,
                'special_field': {}
            }
            
            pdf_filter = self.combo_pdf.get()
            if pdf_filter == "Με PDF":
                search_params['has_pdf'] = True
            elif pdf_filter == "Χωρίς PDF":
                search_params['has_pdf'] = False
            
            for field_name, widget in self.special_fields.items():
                value = widget.get().strip()
                if value:
                    search_params['special_field'][field_name] = value
            
            if search_params['date_from'] and not validate_date(search_params['date_from']):
                self._show_messagebox("error", "Σφάλμα", "Μη έγκυρη ημερομηνία 'Από'")
                return
                
            if search_params['date_to'] and not validate_date(search_params['date_to']):
                self._show_messagebox("error", "Σφάλμα", "Μη έγκυρη ημερομηνία 'Έως'")
                return
            
            self.search_results = self.db_manager.advanced_search_contracts(search_params)
            self.current_page = 1
            self.total_pages = (len(self.search_results) + self.page_size - 1) // self.page_size
            if self.total_pages < 1: self.total_pages = 1
            self.display_search_results()
            
        except Exception as e:
            messagebox.showerror("Σφάλμα", f"Αποτυχία αναζήτησης: {e}")
    
    def display_search_results(self) -> None:
        for widget in self.results_scroll.winfo_children():
            widget.destroy()
        
        count = len(self.search_results)
        self.results_label.configure(text=f"Βρέθηκαν {count} συμβάσεις")
        
        if count == 0:
            ctk.CTkLabel(self.results_scroll, text="Δεν βρέθηκαν συμβάσεις που να ταιριάζουν με τα κριτήρια").pack(pady=10)
            return
        
        # Calculate slice
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_contracts = self.search_results[start_idx:end_idx]

        for contract in page_contracts:
            self._create_result_card(contract)
            
        self._create_pagination_controls()

    def _create_pagination_controls(self):
        control_frame = ctk.CTkFrame(self.results_scroll, fg_color="transparent")
        control_frame.pack(pady=10, fill="x")

        # Info Label
        info_text = f"Σελίδα {self.current_page} από {self.total_pages}"
        ctk.CTkLabel(control_frame, text=info_text, font=("Roboto", 11, "bold")).pack(side="top", pady=(0, 5))
        
        btn_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        btn_frame.pack(side="top")

        # Prev Button
        state_prev = "normal" if self.current_page > 1 else "disabled"
        ctk.CTkButton(btn_frame, text="❮", width=40, state=state_prev,
                     command=self._prev_page, fg_color=self.theme_colors["primary"]).pack(side="left", padx=5)

        # Next Button
        state_next = "normal" if self.current_page < self.total_pages else "disabled"
        ctk.CTkButton(btn_frame, text="❯", width=40, state=state_next,
                     command=self._next_page, fg_color=self.theme_colors["primary"]).pack(side="left", padx=5)

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.display_search_results()
            try:
                # Scroll to top of results
                self.results_scroll._parent_canvas.yview_moveto(0)
            except:
                pass

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.display_search_results()
            try:
                self.results_scroll._parent_canvas.yview_moveto(0)
            except:
                pass
    
    def _create_result_card(self, contract: Dict[str, Any]) -> None:
        card = ctk.CTkFrame(self.results_scroll, corner_radius=12, fg_color=("#f5f5f5", "#2b2b2b"), border_width=1, border_color="#e0e0e0")
        card.pack(fill="x", pady=5, padx=5)
        
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(fill="x", padx=10, pady=8)
        
        ctk.CTkLabel(info_frame, text=contract['provider'], 
                     font=("Roboto", 14, "bold"),
                     text_color=self.theme_colors["primary"]).pack(anchor="w")
        
        basic_info = f"Αρ: {contract['number']} | {contract['type']} | Σύμβαση: {contract['date']}"
        if contract.get('expiry_date'):
            basic_info += f" | Λήξη: {contract['expiry_date']}"
        
        ctk.CTkLabel(info_frame, text=basic_info, 
                     font=("Roboto", 11)).pack(anchor="w", pady=(2, 0))
        
        if contract.get('comments'):
            ctk.CTkLabel(info_frame, text=f"Σχόλια: {contract['comments']}", 
                         font=("Roboto", 10, "italic"),
                         text_color="#7f8c8d").pack(anchor="w", pady=(2, 0))
        
        action_frame = ctk.CTkFrame(card, fg_color="transparent")
        action_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(action_frame, text="✎ Επεξεργασία", width=100,
                      command=lambda c=contract: self.edit_contract(c)).pack(side="left", padx=2)
        
        pdf_paths = contract.get('pdf_paths', [])
        if not pdf_paths and contract.get('pdf_path'):
            # Backward compatibility for παλιές εγγραφές
            pdf_paths = [contract.get('pdf_path')]

        existing_pdf_paths = []
        missing_pdf_count = 0
        for pdf_path in pdf_paths:
            if pdf_path and os.path.exists(pdf_path):
                existing_pdf_paths.append(pdf_path)
            elif pdf_path:
                missing_pdf_count += 1

        if existing_pdf_paths:
            # Αν υπάρχουν διαθέσιμα PDF, άνοιξε το πρώτο
            ctk.CTkButton(
                action_frame,
                text="📄 PDF",
                width=80,
                command=lambda p=existing_pdf_paths[0]: self.open_pdf(p)
            ).pack(side="left", padx=2)

        if missing_pdf_count > 0 and not existing_pdf_paths:
            # Αν δεν υπάρχει κανένα διαθέσιμο PDF αλλά υπήρχαν μονοπάτια, εμφάνισε προειδοποίηση
            ctk.CTkLabel(
                action_frame,
                text="⚠ PDF λείπει",
                font=("Roboto", 11, "bold"),
                text_color="#e74c3c"
            ).pack(side="left", padx=4)
        
        if get_contract_status(contract.get('expiry_date')) == "EXPIRED":
            ctk.CTkButton(action_frame, text="🔄 Ανανέωση", width=85,
                          fg_color="#2fa572", hover_color="#219150",
                          command=lambda c=contract: self.renew_contract(c)).pack(side="left", padx=2)
        
        ctk.CTkButton(action_frame, text="👁️ Προβολή", width=80,
                      command=lambda c=contract: self.view_contract(c)).pack(side="left", padx=2)
    
    def renew_contract(self, contract: Dict[str, Any]) -> None:
        self.master.renew_contract(contract)

    def edit_contract(self, contract: Dict[str, Any]) -> None:
        self.master.edit_contract(contract)
        # The main app handles refreshing via signals when the edit form is saved.
        self.destroy()
    
    def view_contract(self, contract: Dict[str, Any]) -> None:
        view_window = ctk.CTkToplevel(self)
        view_window.title(f"Προβολή Σύμβασης - {contract['provider']}")
        view_window.geometry("500x400")
        
        view_window.transient(self)
        view_window.grab_set()
        
        main_frame = ctk.CTkScrollableFrame(view_window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        fields = [
            ("Πάροχος", contract['provider']),
            ("Αριθμός Σύμβασης", contract['number']),
            ("Ημερομηνία Σύμβασης", contract['date']),
            ("Διάρκεια (μήνες)", contract['months']),
            ("Είδος", contract['type']),
            ("Ημερομηνία Λήξης", contract.get('expiry_date', 'N/A')),
        ]
        
        for label, value in fields:
            row = ctk.CTkFrame(main_frame, fg_color="transparent")
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=label, font=("Roboto", 12, "bold"), width=150, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=str(value), font=("Roboto", 12)).pack(side="left")
        
        if contract.get('comments'):
            ctk.CTkLabel(main_frame, text="Σχόλια:", font=("Roboto", 12, "bold")).pack(anchor="w", pady=(10, 5))
            comments_text = ctk.CTkTextbox(main_frame, height=60)
            comments_text.pack(fill="x", pady=5)
            comments_text.insert("1.0", contract['comments'])
            comments_text.configure(state="disabled")
        
        special_data_str = contract.get('special_data', '{}')
        if special_data_str:
            try:
                special_data = json.loads(special_data_str) if isinstance(special_data_str, str) else special_data_str
                while isinstance(special_data, str):
                    try:
                        special_data = json.loads(special_data)
                    except Exception:
                        break
                if isinstance(special_data, dict) and special_data:
                    ctk.CTkLabel(main_frame, text="Ειδικά Πεδία:", font=("Roboto", 12, "bold")).pack(anchor="w", pady=(10, 5))
                    for key, value in special_data.items():
                        if value:
                            greek_key = SPECIAL_FIELD_TRANSLATIONS.get(key, key.replace('_', ' ').title())
                            row = ctk.CTkFrame(main_frame, fg_color="transparent")
                            row.pack(fill="x", pady=2)
                            ctk.CTkLabel(row, text=greek_key, font=("Roboto", 11), width=150, anchor="w").pack(side="left")
                            ctk.CTkLabel(row, text=str(value), font=("Roboto", 11)).pack(side="left")
            except Exception:
                pass
    
    def open_pdf(self, path: str) -> None:
        """Άνοιγμα PDF με έλεγχο ύπαρξης αρχείου"""
        if not os.path.exists(path):
            messagebox.showerror(
                title="Σφάλμα",
                message=f"Το αρχείο PDF δεν βρέθηκε:\n\n{path}\n\nΤο αρχείο ίσως έχει διαγραφεί ή μετακινηθεί.",
                parent=self
            )
            return
        
        try: 
            os.startfile(path)
        except Exception as e:
            try:
                import subprocess, sys
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.call([opener, path])
            except Exception as e2:
                messagebox.showerror(
                    title="Σφάλμα",
                    message=f"Αποτυχία ανοίγματος PDF:\n{str(e2)}",
                    parent=self
                )


# =========================================================================
# === ΚΛΑΣΗ: ΓΡΗΓΟΡΗ ΑΝΑΝΕΩΣΗ / ΠΑΡΑΤΑΣΗ ΣΥΜΒΑΣΗΣ (1-CLICK RENEW) ===
# =========================================================================

class ContractRenewToplevel(MessageBoxMixin, ctk.CTkToplevel):
    """
    Παράθυρο Γρήγορης Ανανέωσης / Παράτασης Σύμβασης (1-Click Renew)
    
    Επιτρέπει την άμεση ανανέωση σύμβασης για 12, 24 ή προσαρμοσμένους μήνες,
    θέτοντας αυτόματα ως νέα έναρξη την ημερομηνία λήξης της προηγούμενης
    (για συνεχή κάλυψη) ή τη σημερινή ημερομηνία, αρχειοθετώντας ταυτόχρονα
    την τρέχουσα κατάσταση στο ιστορικό εκδόσεων (contract_versions).
    """
    def __init__(self, master: Any, db_manager: Any, contract: Dict[str, Any], current_theme: str = "Minimalist"):
        super().__init__(master)
        
        try:
            self.iconbitmap(get_resource_path(os.path.join("assets", "app.ico")))
        except Exception:
            pass
            
        self.master = master
        self.db_manager = db_manager
        self.contract = contract
        self.current_theme = current_theme or "Minimalist"
        self.theme_colors = COLOR_THEMES.get(self.current_theme, COLOR_THEMES["Minimalist"])
        
        provider = contract.get('provider', 'Σύμβαση')
        self.title(f"Ανανέωση Σύμβασης - {provider}")
        
        self.width = 520
        self.height = 680
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (self.width // 2)
        y = (screen_height // 2) - (self.height // 2)
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")
        
        self.transient(master)
        self.grab_set()
        self.attributes("-topmost", True)
        
        # Προαιρετικό νέο PDF
        self.new_pdf_path: Optional[str] = None
        
        self._setup_ui()
        self.bind("<Escape>", lambda e: self.destroy())

    def _setup_ui(self) -> None:
        # Header banner
        header_frame = ctk.CTkFrame(self, fg_color=self.theme_colors["accent"], corner_radius=0)
        header_frame.pack(fill="x", padx=0, pady=0)
        
        ctk.CTkLabel(
            header_frame,
            text="🔄 Γρήγορη Ανανέωση / Παράταση Σύμβασης",
            font=("Roboto", 16, "bold"),
            text_color="white"
        ).pack(pady=12, padx=15, anchor="w")
        
        # Main scrollable frame
        main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_scroll.pack(fill="both", expand=True, padx=15, pady=(10, 5))
        
        # 1. Summary Card τρέχουσας σύμβασης
        provider = self.contract.get('provider', '')
        c_type = self.contract.get('type', '')
        number = self.contract.get('number', '')
        old_date = self.contract.get('date', 'N/A')
        old_expiry = self.contract.get('expiry_date', 'N/A')
        old_months = str(self.contract.get('months', '12'))
        
        summary_frame = ctk.CTkFrame(main_scroll, fg_color=("gray90", "#2b2b2b"), corner_radius=8,
                                     border_width=1, border_color=("gray80", "#3a3a3a"))
        summary_frame.pack(fill="x", pady=(0, 15))
        
        top_row = ctk.CTkFrame(summary_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=(10, 4))
        
        ctk.CTkLabel(
            top_row,
            text=f"{provider} ({c_type})",
            font=("Roboto", 15, "bold"),
            text_color=self.theme_colors["primary"]
        ).pack(side="left")
        
        status = get_contract_status(old_expiry)
        if status == "EXPIRED":
            st_text, st_col = "ΕΛΗΞΕ", self.theme_colors["danger"]
        elif status == "EXPIRING_SOON":
            st_text, st_col = "ΠΡΟΣ ΛΗΞΗ", self.theme_colors["warning"]
        elif status == "ACTIVE":
            st_text, st_col = "ΕΝΕΡΓΗ", self.theme_colors["accent"]
        else:
            st_text, st_col = "ΧΩΡΙΣ ΛΗΞΗ", "gray"
            
        ctk.CTkLabel(
            top_row,
            text=f" {st_text} ",
            font=("Roboto", 11, "bold"),
            text_color="white",
            fg_color=st_col,
            corner_radius=4
        ).pack(side="right")
        
        info_text = f"Αρ. Σύμβασης: {number}  |  Τρέχουσα Έναρξη: {old_date}  |  Λήξη: {old_expiry}"
        ctk.CTkLabel(
            summary_frame,
            text=info_text,
            font=("Roboto", 12),
            text_color=("gray30", "gray80")
        ).pack(anchor="w", padx=12, pady=(0, 10))
        
        # 2. Νέα Ημερομηνία Έναρξης
        sec1 = ctk.CTkFrame(main_scroll, fg_color="transparent")
        sec1.pack(fill="x", pady=(0, 12))
        
        ctk.CTkLabel(sec1, text="1. Νέα Ημερομηνία Έναρξης:", font=("Roboto", 13, "bold")).pack(anchor="w", pady=(0, 5))
        
        today_str = datetime.now().strftime('%d/%m/%Y')
        has_valid_old_expiry = validate_date(old_expiry)
        
        preset_date_frame = ctk.CTkFrame(sec1, fg_color="transparent")
        preset_date_frame.pack(fill="x", pady=(0, 6))
        
        if has_valid_old_expiry:
            ctk.CTkButton(
                preset_date_frame,
                text=f"📅 Από παλιά λήξη ({old_expiry})",
                font=("Roboto", 11),
                fg_color=self.theme_colors["secondary"],
                hover_color=self.theme_colors["primary"],
                height=28,
                command=lambda: self._set_start_date(old_expiry)
            ).pack(side="left", padx=(0, 6))
        
        ctk.CTkButton(
            preset_date_frame,
            text=f"📅 Από σήμερα ({today_str})",
            font=("Roboto", 11),
            fg_color="#555",
            hover_color="#444",
            height=28,
            command=lambda: self._set_start_date(today_str)
        ).pack(side="left")
        
        date_row = ctk.CTkFrame(sec1, fg_color="transparent")
        date_row.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(date_row, text="Επιλογή Ημερομηνίας:", width=160, anchor="w").pack(side="left")
        
        self.entry_date = DateEntry(
            date_row,
            date_pattern='dd/mm/yyyy',
            width=12,
            background=self.theme_colors['primary'],
            foreground='white',
            borderwidth=2,
            font=("Roboto", 12)
        )
        self.entry_date.pack(side="right", fill="x", expand=True)
        
        # Έξυπνη προεπιλογή ημερομηνίας
        default_start = old_expiry if has_valid_old_expiry else today_str
        try:
            d = datetime.strptime(default_start, '%d/%m/%Y').date()
            self.entry_date.set_date(d)
        except Exception:
            self.entry_date.set_date(datetime.now().date())
            
        self.entry_date.bind("<<DateEntrySelected>>", lambda e: self._update_preview())
        
        # 3. Νέα Διάρκεια (Μήνες)
        sec2 = ctk.CTkFrame(main_scroll, fg_color="transparent")
        sec2.pack(fill="x", pady=(5, 12))
        
        ctk.CTkLabel(sec2, text="2. Νέα Διάρκεια (Μήνες):", font=("Roboto", 13, "bold")).pack(anchor="w", pady=(0, 5))
        
        months_btn_frame = ctk.CTkFrame(sec2, fg_color="transparent")
        months_btn_frame.pack(fill="x", pady=(0, 6))
        
        ctk.CTkButton(
            months_btn_frame,
            text="12 Μήνες (1 έτος)",
            width=120,
            height=28,
            fg_color=self.theme_colors["primary"],
            font=("Roboto", 11, "bold"),
            command=lambda: self._set_months(12)
        ).pack(side="left", padx=(0, 6))
        
        ctk.CTkButton(
            months_btn_frame,
            text="24 Μήνες (2 έτη)",
            width=120,
            height=28,
            fg_color=self.theme_colors["primary"],
            font=("Roboto", 11, "bold"),
            command=lambda: self._set_months(24)
        ).pack(side="left", padx=(0, 6))
        
        if old_months.isdigit() and int(old_months) > 0 and int(old_months) not in (12, 24):
            ctk.CTkButton(
                months_btn_frame,
                text=f"Ίδια ({old_months} μ.)",
                width=100,
                height=28,
                fg_color="#555",
                hover_color="#444",
                font=("Roboto", 11),
                command=lambda: self._set_months(int(old_months))
            ).pack(side="left")
        else:
            ctk.CTkButton(
                months_btn_frame,
                text="36 Μήνες",
                width=90,
                height=28,
                fg_color="#555",
                hover_color="#444",
                font=("Roboto", 11),
                command=lambda: self._set_months(36)
            ).pack(side="left")
            
        custom_months_row = ctk.CTkFrame(sec2, fg_color="transparent")
        custom_months_row.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(custom_months_row, text="Μήνες (προσαρμογή):", width=160, anchor="w").pack(side="left")
        
        self.entry_months = ctk.CTkEntry(custom_months_row, placeholder_text="π.χ. 12")
        self.entry_months.pack(side="right", fill="x", expand=True)
        
        default_m = old_months if (old_months.isdigit() and int(old_months) > 0) else "12"
        self.entry_months.insert(0, default_m)
        self.entry_months.bind("<KeyRelease>", lambda e: self._update_preview())
        
        # 4. Ζωντανή Προεπισκόπηση Νέας Λήξης
        self.preview_card = ctk.CTkFrame(
            main_scroll,
            fg_color=("white", "#1e272e"),
            border_width=2,
            border_color=self.theme_colors["accent"],
            corner_radius=10
        )
        self.preview_card.pack(fill="x", pady=(5, 15), padx=2)
        
        self.lbl_preview_expiry = ctk.CTkLabel(
            self.preview_card,
            text="",
            font=("Roboto", 16, "bold"),
            text_color=self.theme_colors["accent"]
        )
        self.lbl_preview_expiry.pack(pady=(10, 2), padx=10)
        
        self.lbl_preview_sub = ctk.CTkLabel(
            self.preview_card,
            text="",
            font=("Roboto", 12),
            text_color=("gray30", "gray80")
        )
        self.lbl_preview_sub.pack(pady=(0, 10), padx=10)
        
        # 5. Προαιρετικά Στοιχεία (Αριθμός & Νέο PDF)
        sec3 = ctk.CTkFrame(main_scroll, fg_color="transparent")
        sec3.pack(fill="x", pady=(0, 10))
        
        num_row = ctk.CTkFrame(sec3, fg_color="transparent")
        num_row.pack(fill="x", pady=2)
        ctk.CTkLabel(num_row, text="Αρ. Σύμβασης / Παραρτήματος:", width=180, anchor="w", font=("Roboto", 12)).pack(side="left")
        self.entry_number = ctk.CTkEntry(num_row)
        self.entry_number.pack(side="right", fill="x", expand=True)
        self.entry_number.insert(0, number)
        
        pdf_row = ctk.CTkFrame(sec3, fg_color="transparent")
        pdf_row.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(pdf_row, text="Νέο PDF Ανανέωσης:", width=180, anchor="w", font=("Roboto", 12)).pack(side="left")
        
        self.btn_select_pdf = ctk.CTkButton(
            pdf_row,
            text="📎 Προσθήκη PDF...",
            width=140,
            height=26,
            font=("Roboto", 11),
            fg_color="#555",
            hover_color="#444",
            command=self._select_renewal_pdf
        )
        self.btn_select_pdf.pack(side="left", padx=(0, 6))
        
        self.lbl_pdf_name = ctk.CTkLabel(pdf_row, text="", font=("Roboto", 11, "italic"), text_color="gray")
        self.lbl_pdf_name.pack(side="left", fill="x", expand=True)
        
        self.btn_remove_pdf = ctk.CTkButton(
            pdf_row,
            text="✖",
            width=24,
            height=24,
            fg_color="#d9534f",
            hover_color="#c0392b",
            command=self._remove_renewal_pdf
        )
        
        # 6. Αυτόματη Σημείωση στα Σχόλια
        sec4 = ctk.CTkFrame(main_scroll, fg_color="transparent")
        sec4.pack(fill="x", pady=(0, 10))
        
        self.var_add_note = ctk.BooleanVar(value=True)
        cb = ctk.CTkCheckBox(
            sec4,
            text="Αυτόματη καταγραφή ανανέωσης στα σχόλια",
            variable=self.var_add_note,
            font=("Roboto", 12)
        )
        cb.pack(anchor="w", pady=(0, 4))
        
        self.lbl_note_preview = ctk.CTkLabel(
            sec4,
            text="",
            font=("Roboto", 11, "italic"),
            text_color=("gray40", "gray70"),
            anchor="w"
        )
        self.lbl_note_preview.pack(fill="x", padx=25)
        
        # Action Buttons (Κάτω μπάρα)
        btn_bar = ctk.CTkFrame(self, fg_color=("gray95", "#202020"), corner_radius=0)
        btn_bar.pack(fill="x", side="bottom", padx=0, pady=0)
        
        btn_container = ctk.CTkFrame(btn_bar, fg_color="transparent")
        btn_container.pack(fill="x", padx=15, pady=12)
        
        self.btn_confirm = ctk.CTkButton(
            btn_container,
            text="🔄 Επιβεβαίωση Ανανέωσης",
            font=("Roboto", 13, "bold"),
            height=38,
            fg_color=self.theme_colors["accent"],
            hover_color="#219150" if self.theme_colors["accent"] != "#219150" else "#1b7943",
            command=self._confirm_renewal
        )
        self.btn_confirm.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(
            btn_container,
            text="✕ Ακύρωση",
            font=("Roboto", 13),
            height=38,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme_colors["danger"],
            text_color=self.theme_colors["danger"],
            hover_color=self.theme_colors["light_danger"],
            width=100,
            command=self.destroy
        ).pack(side="right")
        
        # Αρχικός υπολογισμός προεπισκόπησης
        self._update_preview()
        
        # Εστίαση στο κουμπί επιβεβαίωσης ώστε να εκτελείται με Enter!
        self.btn_confirm.focus()
        self.bind("<Return>", lambda e: self._confirm_renewal())

    def _set_start_date(self, date_str: str) -> None:
        try:
            d = datetime.strptime(date_str, '%d/%m/%Y').date()
            self.entry_date.set_date(d)
            self._update_preview()
        except Exception:
            pass

    def _set_months(self, months: int) -> None:
        self.entry_months.delete(0, 'end')
        self.entry_months.insert(0, str(months))
        self._update_preview()

    def _update_preview(self) -> None:
        start_date = self.entry_date.get()
        months_str = self.entry_months.get().strip()
        
        if not validate_date(start_date):
            self.lbl_preview_expiry.configure(text="❌ Μη έγκυρη ημερομηνία έναρξης", text_color="#e74c3c")
            self.lbl_preview_sub.configure(text="")
            return
            
        if not (months_str.isdigit() and int(months_str) > 0):
            self.lbl_preview_expiry.configure(text="❌ Εισάγετε έγκυρους μήνες (> 0)", text_color="#e74c3c")
            self.lbl_preview_sub.configure(text="")
            return
            
        months = int(months_str)
        new_expiry = calculate_expiry_date(start_date, months)
        if new_expiry:
            self.lbl_preview_expiry.configure(
                text=f"📅 Νέα Ημερομηνία Λήξης: {new_expiry}",
                text_color=self.theme_colors["accent"]
            )
            self.lbl_preview_sub.configure(
                text=f"Νέα Περίοδος: {start_date}  ➜  {new_expiry}  ({months} μήνες)",
                text_color=("gray20", "gray80")
            )
            if hasattr(self, 'lbl_note_preview'):
                today_s = datetime.now().strftime('%d/%m/%Y')
                self.lbl_note_preview.configure(
                    text=f"Σημείωση: [Ανανέωση {today_s}: {months} μήνες (έως {new_expiry})]"
                )
        else:
            self.lbl_preview_expiry.configure(text="❌ Σφάλμα υπολογισμού", text_color="#e74c3c")
            self.lbl_preview_sub.configure(text="")

    def _select_renewal_pdf(self) -> None:
        self.attributes("-topmost", False)
        self.grab_release()
        filename = filedialog.askopenfilename(
            parent=self.master,
            filetypes=[("PDF files", "*.pdf")]
        )
        self.grab_set()
        self.attributes("-topmost", True)
        
        if filename:
            self.new_pdf_path = filename
            base = os.path.basename(filename)
            display_name = base if len(base) <= 25 else base[:22] + "..."
            self.lbl_pdf_name.configure(text=f"📄 {display_name}")
            self.btn_remove_pdf.pack(side="left", padx=4)

    def _remove_renewal_pdf(self) -> None:
        self.new_pdf_path = None
        self.lbl_pdf_name.configure(text="")
        self.btn_remove_pdf.pack_forget()

    def _confirm_renewal(self) -> None:
        start_date = self.entry_date.get()
        months_str = self.entry_months.get().strip()
        
        if not validate_date(start_date):
            self._show_messagebox("error", "Σφάλμα Ημερομηνίας",
                                 "Παρακαλώ εισάγετε έγκυρη Ημερομηνία Έναρξης (DD/MM/YYYY).")
            return
            
        if not (months_str.isdigit() and int(months_str) > 0):
            self._show_messagebox("error", "Σφάλμα Διάρκειας",
                                 "Η διάρκεια πρέπει να είναι θετικός ακέραιος αριθμός μηνών (π.χ. 12, 24).")
            return
            
        months = int(months_str)
        new_expiry = calculate_expiry_date(start_date, months)
        if not new_expiry:
            self._show_messagebox("error", "Σφάλμα Υπολογισμού",
                                 "Δεν ήταν δυνατός ο υπολογισμός της νέας ημερομηνίας λήξης.")
            return
            
        # 1. Ανάκτηση τρέχουσας κατάστασης από τη βάση
        fresh_contract = self.db_manager.get_contract_by_id(self.contract['id'])
        contract_to_archive = fresh_contract if fresh_contract else self.contract
        
        # 2. Αρχειοθέτηση της τρέχουσας σύμβασης στο ιστορικό εκδόσεων (Contract Versions)
        version_desc = f"Ανανέωση σύμβασης: Νέα έναρξη {start_date}, διάρκεια {months} μήνες (νέα λήξη: {new_expiry})"
        try:
            self.db_manager.create_contract_version(
                contract_to_archive,
                version_desc,
                "User (Ανανέωση)"
            )
        except Exception as ver_err:
            logger.warning(f"Αδυναμία δημιουργίας έκδοσης για σύμβαση {self.contract['id']}: {ver_err}")
            
        # 3. Αντιγραφή νέου PDF αν επιλέχθηκε
        new_pdf_dest = None
        if self.new_pdf_path and os.path.exists(self.new_pdf_path):
            try:
                if not os.path.exists(PDF_FOLDER):
                    os.makedirs(PDF_FOLDER)
                file_name = os.path.basename(self.new_pdf_path)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                new_pdf_dest = os.path.join(PDF_FOLDER, f"{timestamp}_renew_{file_name}")
                shutil.copy(self.new_pdf_path, new_pdf_dest)
            except Exception as pdf_err:
                logger.error(f"Σφάλμα αντιγραφής νέου PDF: {pdf_err}")
                
        # 4. Προετοιμασία ανανεωμένης σύμβασης
        updated_contract = dict(contract_to_archive)
        updated_contract['date'] = start_date
        updated_contract['months'] = str(months)
        updated_contract['expiry_date'] = new_expiry
        
        # Καθαρισμός special_data ώστε να είναι dictionary
        raw_special = contract_to_archive.get('special_data')
        if isinstance(raw_special, dict):
            updated_contract['special_data'] = raw_special
        elif isinstance(raw_special, str) and raw_special.strip():
            try:
                parsed_s = json.loads(raw_special)
                while isinstance(parsed_s, str):
                    parsed_s = json.loads(parsed_s)
                updated_contract['special_data'] = parsed_s if isinstance(parsed_s, dict) else {}
            except Exception:
                updated_contract['special_data'] = {}
        else:
            updated_contract['special_data'] = {}
        
        new_num = self.entry_number.get().strip()
        if new_num:
            updated_contract['number'] = new_num
            
        if new_pdf_dest:
            current_pdfs = list(updated_contract.get('pdf_paths', []))
            if new_pdf_dest not in current_pdfs:
                current_pdfs.append(new_pdf_dest)
            updated_contract['pdf_paths'] = current_pdfs
            if not updated_contract.get('pdf_path'):
                updated_contract['pdf_path'] = new_pdf_dest
                
        if self.var_add_note.get():
            today_note_date = datetime.now().strftime('%d/%m/%Y')
            auto_note = f"[Ανανέωση {today_note_date}: {months} μήνες (έως {new_expiry})]"
            old_comm = (updated_contract.get('comments') or '').strip()
            updated_contract['comments'] = f"{old_comm}\n{auto_note}".strip() if old_comm else auto_note
            
        # 5. Ενημέρωση στη βάση δεδομένων
        try:
            self.db_manager.update_contract(updated_contract)
        except Exception as db_err:
            logger.error(f"Σφάλμα ενημέρωσης σύμβασης στη βάση: {db_err}", exc_info=True)
            self._show_messagebox("error", "Σφάλμα Βάσης", f"Αποτυχία ενημέρωσης σύμβασης:\n\n{str(db_err)}")
            return
            
        # 6. Εκπομπή σήματος για live UI & Dashboard refresh
        SignalManager.emit(Signals.CONTRACT_UPSERTED, updated_contract)
        
        # 7. Ειδοποίηση επιτυχίας
        provider_name = updated_contract.get('provider', 'Η σύμβαση')
        show_notification(
            f"Η σύμβαση '{provider_name}' ανανεώθηκε επιτυχώς έως {new_expiry}!\nΗ προηγούμενη κατάσταση αποθηκεύτηκε στο ιστορικό εκδόσεων.",
            "success"
        )
        
        # 8. Κλείσιμο παραθύρου
        self.destroy()

