import customtkinter as ctk
from typing import Callable, Dict, Any, Optional

class DashboardView(ctk.CTkFrame):
    def __init__(self, master: Any, 
                 callbacks: Dict[str, Callable], 
                 theme_colors: Dict[str, str], 
                 **kwargs):
        super().__init__(master, **kwargs)
        
        self.callbacks = callbacks
        self.theme_colors = theme_colors
        
        # Setup UI
        self._setup_ui()
        
    def _setup_ui(self):
        # Stats container (top part of dashboard)
        # Use a tuple for (light_color, dark_color) or just explicit light color
        # Light mode: White or very light gray. Dark mode: #3a3a3a
        stats_bg = ("#FFFFFF", "#3a3a3a")
        self.stats_frame = ctk.CTkFrame(self, fg_color=stats_bg, corner_radius=10)
        self.stats_frame.pack(fill="x", pady=15, padx=15)
        
        # Initial stats placeholder
        self.refresh_stats({'total': 0, 'by_status': {}})

        # Action Buttons
        self._create_button("➕ ΝΕΑ ΣΥΜΒΑΣΗ", self.callbacks.get('new_contract'), 
                          self.theme_colors["primary"], pady=10, font_bold=True)
                          
        self._create_button("⚙ Διαχείριση Ειδών", self.callbacks.get('manage_categories'), 
                          ("gray70", "#555"), pady=10)
        
        self._create_button("📊 Στατιστικά", self.callbacks.get('show_stats'), 
                          self.theme_colors["accent"], pady=5)
                          
        self._create_button("🔔 Ειδοποιήσεις", self.callbacks.get('show_notifications'), 
                          self.theme_colors["warning"], pady=5)
                          
        self._create_button("🎯 Προχωρημένη Αναζήτηση", self.callbacks.get('advanced_search'), 
                          self.theme_colors["secondary"], pady=5)
                          
        self._create_button("💾 Εξαγωγή", self.callbacks.get('export_data'), 
                          self.theme_colors["secondary"], pady=5)
        
        self._create_button("🎨 Αλλαγή Χρώματος", self.callbacks.get('change_theme'), 
                          self.theme_colors["secondary"], pady=10)

    def _create_button(self, text: str, command: Optional[Callable], 
                      fg_color: str, pady: int, font_bold: bool = False):
        font = ("Roboto", 15 if font_bold else 13, "bold" if font_bold else "normal")
        btn = ctk.CTkButton(self, text=text, command=command, font=font, fg_color=fg_color)
        btn.pack(fill="x", padx=15, pady=pady)

    def refresh_stats(self, stats: Dict[str, Any]):
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
            
        total_contracts = stats.get('total', 0)
        by_status = stats.get('by_status', {})
        
        self.stats_frame.columnconfigure(0, weight=1)
        self.stats_frame.columnconfigure(1, weight=1)
        
        self._create_stat_label("ΣΥΝΟΛΙΚΕΣ ΣΥΜΒΑΣΕΙΣ:", 0, 0, pady=(10, 0))
        self._create_stat_label(str(total_contracts), 1, 0, 30, "bold", self.theme_colors["primary"], pady=(0, 5))
        
        self._create_stat_label("ΕΝΕΡΓΕΣ:", 2, 0)
        self._create_stat_label(str(by_status.get("ACTIVE", 0)), 3, 0, 20, "bold", "#2ecc71", pady=(0, 10))
        
        self._create_stat_label("ΛΗΓΟΥΝ ΣΥΝΤΟΜΑ:", 0, 1, pady=(10, 0))
        self._create_stat_label(str(by_status.get("EXPIRING_SOON", 0)), 1, 1, 20, "bold", self.theme_colors["warning"], pady=(0, 5))
        
        self._create_stat_label("ΛΗΓΜΕΝΕΣ:", 2, 1)
        self._create_stat_label(str(by_status.get("EXPIRED", 0)), 3, 1, 20, "bold", self.theme_colors["danger"], pady=(0, 10))

    def _create_stat_label(self, text: str, row: int, col: int, size: int = 12, 
                          weight: str = "normal", text_color: Optional[str] = None, pady: Any = 0):
        font = ("Roboto", size, weight) if weight == "bold" else ("Roboto", size)
        lbl = ctk.CTkLabel(self.stats_frame, text=text, font=font)
        if text_color:
            lbl.configure(text_color=text_color)
        lbl.grid(row=row, column=col, padx=20, pady=pady, sticky="w")

    def update_theme(self, new_colors: Dict[str, str]):
        self.theme_colors = new_colors
        # Re-render to apply colors
        for widget in self.winfo_children():
            widget.destroy()
        self._setup_ui()
