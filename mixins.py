from tkinter import messagebox
from typing import Any

class MessageBoxMixin:
    """
    Mixin class that provides a centralized messagebox handling for Toplevel windows.
    Ensures that the dialog is lifted and focused properly without duplicating code.
    """
    def _show_messagebox(self, msg_type: str, title: str, message: str) -> Any:
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass
            
        if msg_type == "error":
            return messagebox.showerror(title, message, parent=self)
        elif msg_type == "warning":
            return messagebox.showwarning(title, message, parent=self)
        elif msg_type == "info":
            return messagebox.showinfo(title, message, parent=self)
        elif msg_type == "yesno":
            return messagebox.askyesno(title, message, parent=self)
        return None
