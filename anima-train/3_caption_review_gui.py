from __future__ import annotations

import argparse
import ctypes
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from dataset_sources import collect_training_images
from windows_ui import configure_tk_for_windows, enable_windows_dpi_awareness


COLOR_STYLES = {
    "red": ("#ffd6d6", "#8b0000"),
    "orange": ("#ffd9ad", "#7a3d00"),
    "yellow": ("#fff0a6", "#665200"),
    "green": ("#cfe8cf", "#145c14"),
    "blue": ("#cfe1ff", "#003f8c"),
    "purple": ("#e4d2f4", "#542478"),
    "violet": ("#e8d5f7", "#5b287d"),
    "pink": ("#ffd6e7", "#8a2050"),
    "brown": ("#ddc0a8", "#5d2f10"),
    "black": ("#3a3a3a", "#ffffff"),
    "white": ("#f4f4f4", "#333333"),
    "gray": ("#d8d8d8", "#333333"),
    "grey": ("#d8d8d8", "#333333"),
    "gold": ("#f4d35e", "#5f4800"),
    "golden": ("#f4c542", "#5f4300"),
    "silver": ("#d9dde3", "#38404a"),
    "cyan": ("#c9f3f5", "#075c62"),
    "teal": ("#bfe3df", "#075b53"),
    "turquoise": ("#bcece5", "#075e55"),
    "aqua": ("#c8f1ee", "#075e59"),
    "indigo": ("#d6d4ed", "#30276f"),
    "magenta": ("#f3cce9", "#7c155f"),
    "beige": ("#eee3c7", "#5b5038"),
    "blonde": ("#f5e7a5", "#665813"),
}
SEMANTIC_TERMS = ("eye", "eyes", "hair", "body", "necklace", "necklaces")
APP_BG = "#252525"
PANEL_BG = "#2d2d2d"
IMAGE_BG = "#171717"
INPUT_BG = "#383838"
INPUT_FG = "#eeeeee"
TEXT_MUTED = "#b9b9b9"
TEXT_MAIN = "#f0f0f0"
CONTROL_BG = "#3a3a3a"
CONTROL_ACTIVE_BG = "#464646"
CONTROL_FG = "#f3f3f3"
ACCENT = "#6ea8fe"
FONT_UI = ("Segoe UI", 12)
FONT_UI_SMALL = ("Segoe UI", 11)
FONT_HEADER = ("Segoe UI", 12)
FONT_CAPTION = ("Consolas", 13)
SORT_OPTIONS = (
    "编辑时间顺序",
    "编辑时间倒序",
    "创建时间顺序",
    "创建时间倒序",
    "A 到 Z",
    "Z 到 A",
)
DEFAULT_SORT = "编辑时间顺序"


class CaptionReviewApp:
    def __init__(self, root: tk.Tk, data_dir: Path) -> None:
        self.root = root
        self.data_dir = data_dir
        self.images = collect_training_images(data_dir)
        self.index = 0
        self.current_image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.dirty = False
        self.sort_var = tk.StringVar(value=DEFAULT_SORT)
        self.position_var = tk.DoubleVar(value=1.0)
        self.updating_position = False
        self.dragging_position = False
        self.highlight_job: str | None = None
        self.render_job: str | None = None
        self.last_render_key: tuple[Path, int, int] | None = None
        self.apply_sort(keep_current=False)

        self.root.title("Caption Review")
        self.configure_theme()
        self.center_window(width_ratio=0.9, height_ratio=0.88, margin=64)
        self.root.minsize(
            min(1400, self.root.winfo_screenwidth()),
            min(650, self.root.winfo_screenheight()),
        )

        self._build_ui()
        self._bind_keys()

        if not self.images:
            messagebox.showerror("No images", f"No training images found in {data_dir}")
            self.root.destroy()
            return

        self.load_current()

    def configure_theme(self) -> None:
        self.root.configure(background=APP_BG)
        self.root.option_add("*Font", FONT_UI)
        self.root.option_add("*TCombobox*Listbox.background", INPUT_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", CONTROL_FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#101010")

        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background=APP_BG)
        style.configure("Panel.TFrame", background=PANEL_BG)
        style.configure(
            "App.TLabel",
            background=APP_BG,
            foreground=TEXT_MAIN,
            font=FONT_UI,
        )
        style.configure(
            "Panel.TLabel",
            background=PANEL_BG,
            foreground=TEXT_MAIN,
            font=FONT_UI,
        )
        style.configure(
            "Muted.Panel.TLabel",
            background=PANEL_BG,
            foreground=TEXT_MUTED,
            font=FONT_UI_SMALL,
        )
        style.configure(
            "Header.TLabel",
            background=APP_BG,
            foreground=TEXT_MAIN,
            font=FONT_HEADER,
        )
        style.configure("Image.TLabel", background=IMAGE_BG)
        style.configure(
            "TButton",
            background=CONTROL_BG,
            foreground=CONTROL_FG,
            bordercolor="#555555",
            darkcolor=CONTROL_BG,
            lightcolor=CONTROL_BG,
            font=FONT_UI,
            padding=(14, 8),
        )
        style.map(
            "TButton",
            background=[("active", CONTROL_ACTIVE_BG), ("pressed", "#303030")],
            foreground=[("disabled", "#777777"), ("active", "#ffffff")],
        )
        style.configure(
            "TCombobox",
            fieldbackground=INPUT_BG,
            background=CONTROL_BG,
            foreground=CONTROL_FG,
            arrowcolor=CONTROL_FG,
            bordercolor="#555555",
            darkcolor=CONTROL_BG,
            lightcolor=CONTROL_BG,
            font=FONT_UI,
            padding=(8, 4),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", INPUT_BG)],
            foreground=[("readonly", CONTROL_FG)],
            selectbackground=[("readonly", INPUT_BG)],
            selectforeground=[("readonly", CONTROL_FG)],
        )
        style.configure("Horizontal.TScale", background=PANEL_BG)

    def apply_sort(self, keep_current: bool = True) -> None:
        current_path = self.image_path if keep_current and self.images else None
        selected = self.sort_var.get()

        if selected == "编辑时间倒序":
            self.images.sort(
                key=lambda path: (-path.stat().st_mtime, path.as_posix().casefold())
            )
        elif selected == "创建时间顺序":
            self.images.sort(
                key=lambda path: (path.stat().st_ctime, path.as_posix().casefold())
            )
        elif selected == "创建时间倒序":
            self.images.sort(
                key=lambda path: (-path.stat().st_ctime, path.as_posix().casefold())
            )
        elif selected == "A 到 Z":
            self.images.sort(key=lambda path: path.name.casefold())
        elif selected == "Z 到 A":
            self.images.sort(key=lambda path: path.name.casefold(), reverse=True)
        else:
            self.images.sort(
                key=lambda path: (path.stat().st_mtime, path.as_posix().casefold())
            )

        if current_path in self.images:
            self.index = self.images.index(current_path)
        else:
            self.index = min(self.index, max(len(self.images) - 1, 0))

    def on_sort_changed(self, _event: tk.Event) -> None:
        self.apply_sort(keep_current=True)
        self.position_scale.configure(to=max(len(self.images), 1))
        self.update_status()

    def center_window(
        self,
        width_ratio: float = 0.9,
        height_ratio: float = 0.88,
        margin: int = 0,
    ) -> None:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(round(screen_width * width_ratio), max(screen_width - margin, 1))
        height = min(round(screen_height * height_ratio), max(screen_height - margin, 1))
        x = max((screen_width - width) // 2, 0)
        y = max(((screen_height - height) // 2) - windows_taskbar_height(), 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1, minsize=760)
        self.root.columnconfigure(1, weight=0, minsize=640)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=12, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        self.image_header_label = ttk.Label(left, anchor="center", style="Header.TLabel")
        self.image_header_label.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.image_label = ttk.Label(left, anchor="center", style="Image.TLabel")
        self.image_label.grid(row=1, column=0, sticky="nsew")
        self.image_label.bind("<Configure>", lambda _event: self.schedule_render())
        self.image_label.bind("<Button-1>", lambda _event: self.root.focus_set())

        right = ttk.Frame(self.root, width=640, padding=14, style="Panel.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        right.rowconfigure(4, weight=1)
        right.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(right, anchor="center", style="Panel.TLabel")
        self.status_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.position_scale = ttk.Scale(
            right,
            from_=1,
            to=max(len(self.images), 1),
            variable=self.position_var,
            command=self.preview_position,
            cursor="hand2",
        )
        self.position_scale.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.position_scale.bind("<ButtonPress-1>", self.start_position_drag)
        self.position_scale.bind("<ButtonRelease-1>", self.release_position_drag)

        sort_row = ttk.Frame(right, style="Panel.TFrame")
        sort_row.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        sort_row.columnconfigure(1, weight=1)

        ttk.Label(sort_row, text="排序", style="Panel.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.sort_combo = ttk.Combobox(
            sort_row,
            textvariable=self.sort_var,
            values=SORT_OPTIONS,
            state="readonly",
        )
        self.sort_combo.grid(row=0, column=1, sticky="ew")
        self.sort_combo.bind("<<ComboboxSelected>>", self.on_sort_changed)

        self.jump_tip_label = ttk.Label(right, style="Muted.Panel.TLabel")
        self.jump_tip_label.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        self.caption_text = tk.Text(
            right,
            width=36,
            wrap="word",
            undo=True,
            font=FONT_CAPTION,
            background=INPUT_BG,
            foreground=INPUT_FG,
            insertbackground=INPUT_FG,
            selectbackground=ACCENT,
            selectforeground="#101010",
            relief="flat",
            padx=14,
            pady=12,
        )
        self.caption_text.grid(row=4, column=0, sticky="nsew")
        self.caption_text.bind("<<Modified>>", self.on_text_modified)
        self.configure_highlight_tags()

        button_row = ttk.Frame(right, style="Panel.TFrame")
        button_row.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        button_row.columnconfigure(2, weight=1)

        ttk.Button(button_row, text="Previous", command=self.previous_image).grid(
            row=0, column=0, padx=(0, 10)
        )
        ttk.Button(button_row, text="Next", command=self.next_image).grid(
            row=0, column=1, padx=(0, 10)
        )
        ttk.Button(button_row, text="Save", command=self.save_caption).grid(
            row=0, column=3
        )

    def _bind_keys(self) -> None:
        self.root.bind("<Control-s>", lambda _event: self.save_caption())
        self.root.bind("<Control-S>", lambda _event: self.save_caption())
        self.root.bind("<Alt-Left>", lambda _event: self.previous_image())
        self.root.bind("<Alt-Right>", lambda _event: self.next_image())
        self.root.bind("<Left>", self.handle_previous_shortcut)
        self.root.bind("<Right>", self.handle_next_shortcut)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    @property
    def image_path(self) -> Path:
        return self.images[self.index]

    @property
    def caption_path(self) -> Path:
        return self.image_path.with_suffix(".txt")

    def on_text_modified(self, _event: tk.Event) -> None:
        if self.caption_text.edit_modified():
            self.dirty = True
            self.update_status()
            self.schedule_highlight_refresh()
            self.caption_text.edit_modified(False)

    def configure_highlight_tags(self) -> None:
        self.caption_text.tag_configure(
            "semantic_term",
            background="#e6e6e6",
            foreground="#303030",
        )
        for word, (background, foreground) in COLOR_STYLES.items():
            self.caption_text.tag_configure(
                f"color_{word}",
                background=background,
                foreground=foreground,
            )

    def schedule_highlight_refresh(self) -> None:
        if self.highlight_job is not None:
            self.root.after_cancel(self.highlight_job)
        self.highlight_job = self.root.after(500, self.refresh_highlighting)

    def refresh_highlighting(self) -> None:
        self.highlight_job = None
        content = self.caption_text.get("1.0", "end-1c")
        self.caption_text.tag_remove("semantic_term", "1.0", "end")
        for word in COLOR_STYLES:
            self.caption_text.tag_remove(f"color_{word}", "1.0", "end")

        for term in SEMANTIC_TERMS:
            pattern = re.compile(
                rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])",
                re.IGNORECASE,
            )
            for match in pattern.finditer(content):
                self.caption_text.tag_add(
                    "semantic_term",
                    f"1.0+{match.start()}c",
                    f"1.0+{match.end()}c",
                )

        for word in COLOR_STYLES:
            pattern = re.compile(
                rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])",
                re.IGNORECASE,
            )
            for match in pattern.finditer(content):
                self.caption_text.tag_add(
                    f"color_{word}",
                    f"1.0+{match.start()}c",
                    f"1.0+{match.end()}c",
                )

    def handle_previous_shortcut(self, _event: tk.Event) -> str | None:
        if self.root.focus_get() is self.caption_text:
            return None
        self.previous_image()
        return "break"

    def handle_next_shortcut(self, _event: tk.Event) -> str | None:
        if self.root.focus_get() is self.caption_text:
            return None
        self.next_image()
        return "break"

    def update_status(self) -> None:
        marker = "modified" if self.dirty else "saved"
        self.status_label.config(text=f"{self.index + 1}/{len(self.images)}")
        self.image_header_label.config(text=f"{self.image_path.name} · {marker}")
        self.updating_position = True
        self.position_var.set(float(self.index + 1))
        self.updating_position = False
        if not self.dragging_position:
            self.jump_tip_label.config(text="")

    def start_position_drag(self, _event: tk.Event) -> None:
        self.dragging_position = True
        self.preview_position(str(self.position_var.get()))

    def preview_position(self, value: str) -> None:
        if self.updating_position or not self.images:
            return
        target_index = self.position_to_index(value)
        target_path = self.images[target_index]
        self.jump_tip_label.config(
            text=f"松开跳到 {target_index + 1}/{len(self.images)}: {target_path.name}"
        )

    def release_position_drag(self, _event: tk.Event) -> str:
        if not self.images:
            return "break"
        self.dragging_position = False
        target_index = self.position_to_index(self.position_var.get())
        if target_index == self.index:
            self.update_status()
            return "break"
        if not self.confirm_discard():
            self.update_status()
            return "break"
        self.index = target_index
        self.load_current()
        return "break"

    def position_to_index(self, value: str | int) -> int:
        try:
            position = round(float(value))
        except (TypeError, ValueError):
            position = self.index + 1
        position = min(max(position, 1), len(self.images))
        return position - 1

    def load_current(self) -> None:
        if self.highlight_job is not None:
            self.root.after_cancel(self.highlight_job)
            self.highlight_job = None
        self.current_image = Image.open(self.image_path).convert("RGB")
        caption = ""
        if self.caption_path.exists():
            caption = self.caption_path.read_text(encoding="utf-8").strip()

        self.caption_text.delete("1.0", "end")
        self.caption_text.insert("1.0", caption)
        self.caption_text.edit_reset()
        self.caption_text.edit_modified(False)
        self.refresh_highlighting()
        self.dirty = False
        self.update_status()
        self.last_render_key = None
        self.schedule_render()

    def schedule_render(self) -> None:
        if self.render_job is not None:
            self.root.after_cancel(self.render_job)
        self.render_job = self.root.after(80, self.render_image)

    def render_image(self) -> None:
        self.render_job = None
        if self.current_image is None:
            return

        box_width = max(self.image_label.winfo_width(), 1)
        box_height = max(self.image_label.winfo_height(), 1)
        if box_width <= 1 or box_height <= 1:
            return
        render_key = (self.image_path, box_width, box_height)
        if render_key == self.last_render_key:
            return

        width, height = self.current_image.size
        scale = min(box_width / width, box_height / height)
        display_size = (max(int(width * scale), 1), max(int(height * scale), 1))
        display = self.current_image.resize(display_size, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(display)
        self.image_label.config(image=self.photo)
        self.last_render_key = render_key

    def save_caption(self) -> None:
        text = self.caption_text.get("1.0", "end").strip()
        self.caption_path.write_text(text + "\n", encoding="utf-8")
        self.dirty = False
        self.update_status()

    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        result = messagebox.askyesnocancel(
            "Unsaved caption",
            "Save changes before switching images?",
        )
        if result is None:
            return False
        if result:
            self.save_caption()
        return True

    def previous_image(self) -> None:
        if not self.confirm_discard():
            return
        self.index = (self.index - 1) % len(self.images)
        self.load_current()

    def next_image(self) -> None:
        if not self.confirm_discard():
            return
        self.index = (self.index + 1) % len(self.images)
        self.load_current()

    def close(self) -> None:
        if self.confirm_discard():
            if self.highlight_job is not None:
                self.root.after_cancel(self.highlight_job)
            if self.render_job is not None:
                self.root.after_cancel(self.render_job)
            self.root.destroy()


def windows_taskbar_height() -> int:
    if sys.platform != "win32":
        return 0

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    rect = RECT()
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            work_area_height = rect.bottom - rect.top
            screen_height = ctypes.windll.user32.GetSystemMetrics(1)
            return max(screen_height - work_area_height, 0)
    except (AttributeError, OSError):
        pass
    return 40


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review training images and edit captions.")
    parser.add_argument("--data-dir", type=Path, default=Path("train/anima/data"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    enable_windows_dpi_awareness()
    root = tk.Tk()
    configure_tk_for_windows(root)
    CaptionReviewApp(root, args.data_dir.resolve())
    root.mainloop()


if __name__ == "__main__":
    main()
