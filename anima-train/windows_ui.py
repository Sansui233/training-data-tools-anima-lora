from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import ttk


def enable_windows_dpi_awareness() -> str:
    if sys.platform != "win32":
        return "not-windows"

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_bool
        if set_context(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
        if ctypes.get_last_error() == 5:
            return "already-configured"
    except (AttributeError, OSError):
        pass

    try:
        shcore = ctypes.WinDLL("shcore")
        if shcore.SetProcessDpiAwareness(2) == 0:
            return "per-monitor"
    except (AttributeError, OSError):
        pass

    try:
        if ctypes.windll.user32.SetProcessDPIAware():
            return "system-aware"
    except (AttributeError, OSError):
        pass
    return "unavailable"


def configure_tk_for_windows(root: tk.Tk) -> float:
    dpi = float(root.winfo_fpixels("1i"))
    root.tk.call("tk", "scaling", dpi / 72.0)
    style = ttk.Style(root)
    if sys.platform == "win32" and "vista" in style.theme_names():
        style.theme_use("vista")
    return dpi
