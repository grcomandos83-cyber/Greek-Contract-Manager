import customtkinter as ctk
import json
import os
from typing import Callable, Dict, List, Optional, Any, Set
from utils import get_contract_status
from constants import SPECIAL_FIELD_TRANSLATIONS

class ContractListView(ctk.CTkScrollableFrame):
    def __init__(self, master: Any, 
                 callbacks: Dict[str, Callable], 
                 theme_colors: Dict[str, str], 
                 **kwargs):
        super().__init__(master, label_text="Λίστα Συμβάσεων", **kwargs)
        
        self.callbacks = callbacks
        self.theme_colors = theme_colors
        self.contracts: List[Dict[str, Any]] = []
        self.contract_cards: Dict[str, ctk.CTkFrame] = {}
        
        # Pagination settings
        self.page_size = 50
        self.current_page = 1
        self.total_pages = 1
        


    def update_contracts(self, contracts: List[Dict[str, Any]]):
        self.contracts = contracts
        self.current_page = 1
        self.total_pages = (len(self.contracts) + self.page_size - 1) // self.page_size
        if self.total_pages < 1: self.total_pages = 1
        self._refresh_display()

    def _refresh_display(self):
        # Clear existing
        for card in self.contract_cards.values():
            card.pack_forget()
            card.destroy()
        self.contract_cards.clear()
        
        if not self.contracts:
            no_contracts_label = ctk.CTkLabel(self, text="Δεν βρέθηκαν συμβάσεις.")
            no_contracts_label.pack(pady=20)
            self.contract_cards['no_contracts'] = no_contracts_label 
            return

        # Calculate slice
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_contracts = self.contracts[start_idx:end_idx]

        for contract in page_contracts:
            card = self._create_card(contract)
            card.pack(pady=8, padx=10, fill="x")
            self.contract_cards[contract['id']] = card

        # Pagination Controls
        self._create_pagination_controls()

    def _create_pagination_controls(self):
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(pady=20, fill="x")
        self.contract_cards['pagination_controls'] = control_frame

        # Info Label
        info_text = f"Σελίδα {self.current_page} από {self.total_pages} (Σύνολο: {len(self.contracts)})"
        ctk.CTkLabel(control_frame, text=info_text, font=("Roboto", 12, "bold")).pack(side="top", pady=(0, 10))
        
        btn_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        btn_frame.pack(side="top")

        # Prev Button
        state_prev = "normal" if self.current_page > 1 else "disabled"
        ctk.CTkButton(btn_frame, text="❮ Προηγούμενη", width=120, state=state_prev,
                     command=self._prev_page, fg_color=self.theme_colors["primary"]).pack(side="left", padx=10)

        # Next Button
        state_next = "normal" if self.current_page < self.total_pages else "disabled"
        ctk.CTkButton(btn_frame, text="Επόμενη ❯", width=120, state=state_next,
                     command=self._next_page, fg_color=self.theme_colors["primary"]).pack(side="left", padx=10)

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._refresh_display()
            try:
                self._parent_canvas.yview_moveto(0)
            except:
                pass

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._refresh_display()
            try:
                self._parent_canvas.yview_moveto(0)
            except:
                pass

    def _create_card(self, contract: Dict[str, Any]) -> ctk.CTkFrame:
        expiry_date_str = contract.get('expiry_date')
        status = get_contract_status(expiry_date_str)
        
        if status == "EXPIRED": 
            status_text, status_color = "ΕΛΗΞΕ", self.theme_colors["danger"]
        elif status == "EXPIRING_SOON": 
            status_text, status_color = "ΠΡΟΣ ΛΗΞΗ (90μ.)", self.theme_colors["warning"]
        elif status == "ACTIVE": 
            status_text, status_color = "ΕΝΕΡΓΗ", self.theme_colors["accent"]
        else: 
            status_text, status_color = "ΔΕΝ ΥΠΟΛΟΓΙΣΤΗΚΕ", "gray"

        # Use None/Transparent for natural light/dark adaptation, or specific tuple
        # Card background: White in Light, Dark Gray in Dark
        card_fg = ("#FFFFFF", "#2b2b2b") 
        border_col = ("#E0E0E0", "#3a3a3a")
        
        card = ctk.CTkFrame(self, corner_radius=10, fg_color=card_fg, border_width=1, border_color=border_col)
        
        grid_frame = ctk.CTkFrame(card, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=5)
        grid_frame.columnconfigure(0, weight=1) 
        grid_frame.columnconfigure(1, weight=0) 
        
        # Checkbox/Status area
        checkbox_frame = ctk.CTkFrame(grid_frame, fg_color="transparent")
        checkbox_frame.grid(row=0, column=1, rowspan=3, sticky="ne", padx=5, pady=5)
        
        ctk.CTkLabel(checkbox_frame, text=" "+status_text+" ", font=("Roboto", 11, "bold"), 
                    text_color="white", fg_color=status_color, corner_radius=5).pack(side="top", pady=(0, 5), padx=5, anchor="e")
        
        # Action Buttons
        action_frame = ctk.CTkFrame(checkbox_frame, fg_color="transparent")
        action_frame.pack(side="bottom")
        
        ctk.CTkButton(action_frame, text="✎", width=30, fg_color="#d35400", height=24,
                     command=lambda c=contract: self.callbacks['edit_contract'](c)).pack(side="left", padx=2)
        
        ctk.CTkButton(action_frame, text="🗑", width=30, fg_color=self.theme_colors["danger"], height=24,
                     command=lambda c=contract['id']: self.callbacks['delete_contract'](c)).pack(side="left", padx=2)
        
        # Display multiple PDF buttons with integrity check
        pdf_paths = contract.get('pdf_paths', [])
        if not pdf_paths and contract.get('pdf_path'):
            # Backward compatibility
            pdf_paths = [contract.get('pdf_path')]
        
        existing_pdf_paths = []
        missing_pdf_count = 0
        for pdf_path in pdf_paths:
            if pdf_path and os.path.exists(pdf_path):
                existing_pdf_paths.append(pdf_path)
            elif pdf_path:
                missing_pdf_count += 1
        
        if existing_pdf_paths:
            # Εμφάνιση ενός συνοπτικού κουμπιού αντί για πολλά εικονίδια
            pdf_count = len(existing_pdf_paths)
            btn_text = "📄 PDF" if pdf_count == 1 else f"📄 {pdf_count} PDF"
            # Άνοιγμα του πρώτου PDF (το πιο βασικό)
            first_pdf = existing_pdf_paths[0]
            ctk.CTkButton(
                action_frame,
                text=btn_text,
                width=90,
                fg_color=self.theme_colors["primary"],
                height=24,
                command=lambda p=first_pdf: self.callbacks['open_pdf'](p)
            ).pack(side="left", padx=2)
        
        if missing_pdf_count > 0:
            # Quick visual warning for missing PDFs
            warn_text = "⚠ PDF λείπει" if missing_pdf_count == 1 else f"⚠ {missing_pdf_count} PDF λείπουν"
            ctk.CTkLabel(
                action_frame,
                text=warn_text,
                font=("Roboto", 11, "bold"),
                text_color=self.theme_colors.get("danger", "#e74c3c")
            ).pack(side="left", padx=4)
        
        # Contract Info
        ctk.CTkLabel(grid_frame, text=contract['provider'], font=("Roboto", 18, "bold"), 
                    text_color=self.theme_colors["primary"]).grid(row=0, column=0, sticky="w")
        
        ctk.CTkLabel(grid_frame, text=f"({contract['type']})", font=("Roboto", 15, "bold"), 
                    text_color=("gray60", "#7b91a7")).grid(row=0, column=0, sticky="e", padx=(0, 150)) 
        
        info = f"Αρ: {contract['number']} | Ημ/νία Σύμβ.: {contract['date']} | Διάρκεια: {contract['months']} μήνες | Λήξη: {contract.get('expiry_date', 'N/A')}"
        ctk.CTkLabel(grid_frame, text=info, font=("Roboto", 14), text_color=("gray10", "gray90")).grid(row=1, column=0, sticky="w", pady=(2, 0))
        
        # Special Fields
        special_data_str = contract.get('special_data', '{}')
        special_data_dict = {}
        if special_data_str:
            try:
                special_data_dict = json.loads(special_data_str)
            except json.JSONDecodeError:
                pass
        
        translated_data = []
        for key, value in special_data_dict.items():
            if value and value is not False:
                greek_key = SPECIAL_FIELD_TRANSLATIONS.get(key, key.replace('_', ' ').title())
                translated_data.append(f"{greek_key}: {value}")
        
        special_data_str = ", ".join(translated_data)
        if special_data_str: 
            ctk.CTkLabel(grid_frame, text=f"Ειδικά: {special_data_str}", font=("Roboto", 13, "italic"), 
                        text_color=("gray40", "#7e8c8d"), wraplength=450).grid(row=2, column=0, sticky="w", pady=(2, 0))
        
        if contract.get('comments'): 
            ctk.CTkLabel(grid_frame, text=f"Σχόλια: {contract['comments']}", font=("Roboto", 13, "italic"), 
                        text_color=("gray40", "silver"), wraplength=450).grid(row=3, column=0, sticky="w", pady=(2, 0))
        
        return card

    def update_theme(self, new_colors: Dict[str, str]):
        self.theme_colors = new_colors
        self._refresh_display()
