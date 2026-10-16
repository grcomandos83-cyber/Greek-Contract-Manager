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
        self.selected_status: Optional[str] = None
        self._last_stats: Dict[str, Any] = {'total': 0, 'by_status': {}}
        self.stat_tiles: Dict[str, ctk.CTkFrame] = {}
        
        # Setup UI
        self._setup_ui()
        
    def _setup_ui(self):
        # Stats container (top part of dashboard)
        stats_bg = ("#FFFFFF", "#2E2E2E")
        self.stats_frame = ctk.CTkFrame(self, fg_color=stats_bg, corner_radius=12)
        self.stats_frame.pack(fill="x", pady=(15, 12), padx=15)
        
        # Initial stats placeholder
        self.refresh_stats(self._last_stats)

        # Action Buttons (Αφαιρέθηκαν τα διπλότυπα κουμπιά για να αναπνεύσει η στήλη)
        self._create_button("➕ ΝΕΑ ΣΥΜΒΑΣΗ", self.callbacks.get('new_contract'), 
                          self.theme_colors["primary"], pady=(8, 8), font_bold=True)
                          
        self._create_button("⚙ Διαχείριση Ειδών", self.callbacks.get('manage_categories'), 
                          ("gray70", "#555"), pady=6)
        
        self._create_button("📊 Στατιστικά", self.callbacks.get('show_stats'), 
                          self.theme_colors["accent"], pady=6)
                          
        self._create_button("🔔 Ειδοποιήσεις", self.callbacks.get('show_notifications'), 
                          self.theme_colors["warning"], pady=6)
                          
        self._create_button("💾 Εξαγωγή", self.callbacks.get('export_data'), 
                          self.theme_colors["secondary"], pady=(6, 12))

    def _create_button(self, text: str, command: Optional[Callable], 
                      fg_color: str, pady: Any, font_bold: bool = False):
        font = ("Roboto", 14 if font_bold else 13, "bold" if font_bold else "normal")
        btn = ctk.CTkButton(self, text=text, command=command, font=font, fg_color=fg_color, height=36)
        btn.pack(fill="x", padx=15, pady=pady)

    def refresh_stats(self, stats: Dict[str, Any]):
        self._last_stats = stats
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        self.stat_tiles.clear()
            
        total_contracts = stats.get('total', 0)
        by_status = stats.get('by_status', {})
        
        self.stats_frame.columnconfigure(0, weight=1, uniform="tile")
        self.stats_frame.columnconfigure(1, weight=1, uniform="tile")
        
        # 1. Total (Συνολικές) -> Row 0, Col 0
        self._create_stat_tile(
            title="ΣΥΝΟΛΙΚΕΣ:",
            value=str(total_contracts),
            status_key=None,
            color=self.theme_colors.get("primary", "#3B8ED0"),
            row=0, col=0,
            is_large=True
        )
        
        # 2. Expiring soon (Λήγουν σύντομα) -> Row 0, Col 1
        self._create_stat_tile(
            title="ΛΗΓΟΥΝ ΣΥΝΤΟΜΑ:",
            value=str(by_status.get("EXPIRING_SOON", 0)),
            status_key="EXPIRING_SOON",
            color=self.theme_colors.get("warning", "#F39C12"),
            row=0, col=1
        )
        
        # 3. Active (Ενεργές) -> Row 1, Col 0
        self._create_stat_tile(
            title="ΕΝΕΡΓΕΣ:",
            value=str(by_status.get("ACTIVE", 0)),
            status_key="ACTIVE",
            color="#27AE60",
            row=1, col=0
        )
        
        # 4. Expired (Ληγμένες) -> Row 1, Col 1
        self._create_stat_tile(
            title="ΛΗΓΜΕΝΕΣ:",
            value=str(by_status.get("EXPIRED", 0)),
            status_key="EXPIRED",
            color=self.theme_colors.get("danger", "#BE3324"),
            row=1, col=1
        )

    def _create_stat_tile(self, title: str, value: str, status_key: Optional[str], 
                          color: str, row: int, col: int, is_large: bool = False):
        is_selected = (self.selected_status == status_key) and (status_key is not None)
        tile_bg = ("#EFF6FF", "#3D3D3D") if is_selected else ("#F8FAFC", "#333333")
        border_col = color if is_selected else ("#E2E8F0", "#4A4A4A")
        border_w = 2 if is_selected else 1

        tile = ctk.CTkFrame(
            self.stats_frame,
            fg_color=tile_bg,
            corner_radius=8,
            border_width=border_w,
            border_color=border_col,
            cursor="hand2"
        )
        tile.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        self.stat_tiles[str(status_key)] = tile

        lbl_title = ctk.CTkLabel(
            tile,
            text=title,
            font=("Roboto", 10, "bold"),
            text_color=("gray45", "gray70"),
            cursor="hand2"
        )
        lbl_title.pack(anchor="w", padx=10, pady=(6, 1))

        lbl_val = ctk.CTkLabel(
            tile,
            text=value,
            font=("Roboto", 22 if is_large else 18, "bold"),
            text_color=color,
            cursor="hand2"
        )
        lbl_val.pack(anchor="w", padx=10, pady=(0, 6))

        # Click handler
        def on_click(event=None):
            self._handle_stat_click(status_key)

        # Hover effects
        def on_enter(event=None):
            if (self.selected_status != status_key) or (status_key is None):
                tile.configure(border_color=color, border_width=2)

        def on_leave(event=None):
            if (self.selected_status != status_key) or (status_key is None):
                tile.configure(border_color=("#E2E8F0", "#4A4A4A"), border_width=1)

        for w in (tile, lbl_title, lbl_val):
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

    def _handle_stat_click(self, status_key: Optional[str]):
        if status_key is None:
            # Κλικ στις συνολικές -> Επαναφορά σε όλες
            self.selected_status = None
        elif self.selected_status == status_key:
            # Δεύτερο κλικ στο ήδη επιλεγμένο -> Toggle off (όλες)
            self.selected_status = None
        else:
            self.selected_status = status_key

        if self.callbacks.get('filter_status'):
            self.callbacks['filter_status'](self.selected_status)

        self.refresh_stats(self._last_stats)

    def set_selected_status(self, status: Optional[str]):
        self.selected_status = status
        if hasattr(self, '_last_stats') and self._last_stats:
            self.refresh_stats(self._last_stats)

    def update_theme(self, new_colors: Dict[str, str]):
        self.theme_colors = new_colors
        for widget in self.winfo_children():
            widget.destroy()
        self._setup_ui()
