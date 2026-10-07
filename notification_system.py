import customtkinter as ctk
import tkinter as tk
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class GlobalNotificationManager:
    """Διαχειριστής ειδοποιήσεων που εμφανίζονται σε ξεχωριστό παράθυρο"""
    
    _instance: Optional['GlobalNotificationManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalNotificationManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.notification_window: Optional[tk.Tk] = None
        self.notification_label: Optional[ctk.CTkLabel] = None
        self.notification_queue: List[tuple[str, str]] = []  # (message, color)
        self.notification_pending = False
        self.root: Optional[ctk.CTk] = None
        self.keep_on_top_timer_id: Optional[str] = None
    
    def set_root(self, root: ctk.CTk):
        """Ορισμός του κύριου παράθυρου"""
        self.root = root
    
    def show(self, message: str, notification_type: str = "success", duration_ms: int = 2500):
        """
        Εμφάνιση ειδοποίησης
        
        Args:
            message: Το κείμενο της ειδοποίησης
            notification_type: "success" (πράσινο), "warning" (πορτοκαλί), "error" (κόκκινο)
            duration_ms: Διάρκεια εμφάνισης σε χιλιοστά του δευτερολέπτου
        """
        colors = {
            "success": ("#e8f5e9", "#2e7d32", "#4caf50"),
            "warning": ("#fff3e0", "#e65100", "#ff9800"),
            "error": ("#ffebee", "#c62828", "#f44336")
        }
        
        bg_color, text_color, border_color = colors.get(notification_type, colors["success"])
        
        self.notification_queue.append((message, bg_color, text_color, border_color, duration_ms))
        
        if not self.notification_pending:
            self._display_next_notification()
    
    def _keep_notification_on_top(self):
        """Συνεχής ανύψωση παράθυρου ειδοποίησης μπροστά από όλα τα άλλα"""
        if self.notification_window and self.notification_window.winfo_exists():
            try:
                self.notification_window.lift()
                self.notification_window.attributes("-topmost", True)
            except:
                pass
        
        # Επανάληψη κάθε 100ms
        if self.notification_pending:
            self.keep_on_top_timer_id = self.root.after(100, self._keep_notification_on_top)
    
    def _display_next_notification(self):
        """Εμφάνιση του επόμενου μηνύματος από την ουρά"""
        if not self.notification_queue:
            self.notification_pending = False
            # Ακύρωση του timer για ανύψωση
            if self.keep_on_top_timer_id:
                try:
                    self.root.after_cancel(self.keep_on_top_timer_id)
                except:
                    pass
                self.keep_on_top_timer_id = None
            return
        
        self.notification_pending = True
        message, bg_color, text_color, border_color, duration_ms = self.notification_queue.pop(0)
        
        # Δημιουργία παράθυρου αν δεν υπάρχει
        if self.notification_window is None or not self.notification_window.winfo_exists():
            self._create_notification_window(bg_color, border_color)
        
        # Ενημέρωση χρωμάτων
        self.notification_window.configure(bg=bg_color)
        self.notification_label.configure(text=message, fg=text_color)
        
        # Εμφάνιση και ανύψωση παράθυρου
        self.notification_window.deiconify()
        self.notification_window.lift()
        self.notification_window.attributes("-topmost", True)
        
        # Έναρξη συνεχούς ανύψωσης
        self._keep_notification_on_top()
        
        # Απόκρυψη και εμφάνιση επόμενου
        def hide_and_next():
            if self.notification_window and self.notification_window.winfo_exists():
                self.notification_window.withdraw()
                self.notification_window.attributes("-topmost", False)
            
            # Ακύρωση του timer για ανύψωση
            if self.keep_on_top_timer_id:
                try:
                    self.root.after_cancel(self.keep_on_top_timer_id)
                except:
                    pass
                self.keep_on_top_timer_id = None
            
            # Αν υπάρχουν περισσότερα μηνύματα, εμφάνισε το επόμενο
            if self.notification_queue:
                self.root.after(300, self._display_next_notification)
            else:
                self.notification_pending = False
        
        self.root.after(duration_ms, hide_and_next)
    
    def _create_notification_window(self, bg_color: str, border_color: str):
        """Δημιουργία παράθυρου ειδοποίησης ως Toplevel (όχι δεύτερο Tk root)"""
        
        if not self.root:
            logger.warning("Cannot create notification window: no root set")
            return
        
        # Δημιουργία Toplevel αντί για δεύτερο Tk root
        self.notification_window = tk.Toplevel(self.root)
        self.notification_window.title("")
        self.notification_window.geometry("500x70")
        
        # Ρυθμίσεις παράθυρου για να παραμείνει πάντα μπροστά
        self.notification_window.attributes("-topmost", True)
        self.notification_window.attributes("-toolwindow", True)
        
        # Αφαίρεση περιθωρίου παράθυρου (frameless)
        self.notification_window.overrideredirect(False)
        
        # Τοποθέτηση στο κέντρο-πάνω της οθόνης
        try:
            screen_width = self.notification_window.winfo_screenwidth()
            screen_height = self.notification_window.winfo_screenheight()
            x = (screen_width // 2) - 250
            y = 50
            self.notification_window.geometry(f"500x70+{x}+{y}")
        except Exception:
            pass
        
        # Ρύθμιση χρωμάτων
        self.notification_window.configure(bg=bg_color)
        
        # Frame με border
        border_frame = tk.Frame(self.notification_window, bg=border_color, highlightthickness=0)
        border_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Inner frame για το περιεχόμενο
        inner_frame = tk.Frame(border_frame, bg=bg_color, highlightthickness=0)
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        # Δημιουργία label
        self.notification_label = tk.Label(
            inner_frame,
            text="",
            font=("Roboto", 11),
            bg=bg_color,
            fg="black",
            wraplength=480,
            justify="center",
            pady=10
        )
        self.notification_label.pack(padx=15, pady=5, expand=True)
        
        # Αρχικά κρυμμένο
        self.notification_window.withdraw()


# Global instance
notification_manager = GlobalNotificationManager()


def show_notification(message: str, notification_type: str = "success", duration_ms: int = 2500):
    """Συνάρτηση βοήθειας για εμφάνιση ειδοποιήσεων"""
    notification_manager.show(message, notification_type, duration_ms)
