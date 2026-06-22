from __future__ import annotations

import argparse
import ctypes
import logging
import math
import sys
import time
import tkinter as tk
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageOps, ImageTk, UnidentifiedImageError

from dataset_sources import collect_training_images
from image_naming import (
    is_marked_sliced,
    is_slice_image,
    original_stem,
    slice_number,
)
from windows_ui import configure_tk_for_windows, enable_windows_dpi_awareness


LOGGER = logging.getLogger("image_split")

APP_BG = "#252525"
PANEL_BG = "#2d2d2d"
IMAGE_BG = "#171717"
INPUT_BG = "#383838"
TEXT_MUTED = "#b9b9b9"
TEXT_MAIN = "#f0f0f0"
CONTROL_BG = "#3a3a3a"
CONTROL_ACTIVE_BG = "#464646"
CONTROL_FG = "#f3f3f3"
DANGER_BG = "#8f2f2f"
DANGER_ACTIVE_BG = "#a83a3a"
DANGER_FG = "#ffffff"
ACCENT = "#6ea8fe"
FONT_UI = ("Segoe UI", 12)
FONT_UI_SMALL = ("Segoe UI", 11)
FONT_HEADER = ("Segoe UI", 12)
FONT_OVERLAY = ("Segoe UI", 10, "bold")


def configure_logging(data_dir: Path, level: str) -> Path:
    report_dir = data_dir.parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path = report_dir / "image_split.log"
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    LOGGER.handlers.clear()
    LOGGER.setLevel(level)
    LOGGER.propagate = False
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    LOGGER.addHandler(stream_handler)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)
    return log_path


def configure_dark_theme(root: tk.Tk) -> None:
    root.configure(background=APP_BG)
    root.option_add("*Font", FONT_UI)

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("App.TFrame", background=APP_BG)
    style.configure("Panel.TFrame", background=PANEL_BG)
    style.configure("Card.TFrame", background=INPUT_BG)
    style.configure(
        "Card.TLabel",
        background=INPUT_BG,
        foreground=TEXT_MAIN,
        font=FONT_UI_SMALL,
    )
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
        "Danger.TButton",
        background=DANGER_BG,
        foreground=DANGER_FG,
        bordercolor="#b94a4a",
        darkcolor=DANGER_BG,
        lightcolor=DANGER_BG,
        font=FONT_UI,
        padding=(14, 8),
    )
    style.map(
        "Danger.TButton",
        background=[("active", DANGER_ACTIVE_BG), ("pressed", "#6f2424")],
        foreground=[("disabled", "#777777"), ("active", "#ffffff")],
    )
    style.configure(
        "TCheckbutton",
        background=PANEL_BG,
        foreground=CONTROL_FG,
        font=FONT_UI,
        padding=(4, 4),
    )
    style.map(
        "TCheckbutton",
        background=[("active", PANEL_BG)],
        foreground=[("disabled", "#777777"), ("active", "#ffffff")],
    )
    style.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=INPUT_BG,
        bordercolor=INPUT_BG,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
    )
    style.configure(
        "Horizontal.TScale",
        background=APP_BG,
        troughcolor=INPUT_BG,
    )
    style.configure(
        "Vertical.TScrollbar",
        background=CONTROL_BG,
        troughcolor=PANEL_BG,
        arrowcolor=CONTROL_FG,
        bordercolor="#555555",
    )
    style.configure(
        "TPanedwindow",
        background=APP_BG,
        sashrelief="flat",
    )


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


def find_large_images(
    data_dir: Path,
    max_side: int,
) -> tuple[list[Path], list[tuple[Path, str]]]:
    started_at = time.perf_counter()
    training_images = collect_training_images(data_dir)
    LOGGER.info("扫描 training data：%s，共 %d 个图片文件", data_dir, len(training_images))
    candidates: list[Path] = []
    failures: list[tuple[Path, str]] = []
    for path in training_images:
        if is_slice_image(path):
            continue
        try:
            with Image.open(path) as image:
                if max(image.size) > max_side:
                    candidates.append(path)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            failures.append((path, f"{type(exc).__name__}: {exc}"))
    LOGGER.info(
        "尺寸扫描完成：候选 %d，无法读取 %d，耗时 %.3f 秒",
        len(candidates),
        len(failures),
        time.perf_counter() - started_at,
    )
    return candidates, failures


def find_slice_paths(image_path: Path) -> list[tuple[int, Path]]:
    image_original_stem = original_stem(image_path)
    paths: list[tuple[int, Path]] = []
    for path in image_path.parent.glob("*.webp"):
        number = slice_number(path)
        if number is not None and original_stem(path) == image_original_stem:
            paths.append((number, path))
    return sorted(paths, key=lambda item: item[0])


class ImagePreviewDialog:
    def __init__(self, parent: tk.Tk, image: Image.Image, title: str) -> None:
        self.image = image.copy()
        self.photo: ImageTk.PhotoImage | None = None
        self.render_job: str | None = None

        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.configure(background=APP_BG)
        self.window.minsize(500, 400)
        self.window.transient(parent)

        parent.update_idletasks()
        width = min(round(parent.winfo_width() * 0.82), max(parent.winfo_width() - 80, 500))
        height = min(
            round(parent.winfo_height() * 0.82),
            max(parent.winfo_height() - 80, 400),
        )
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.window,
            background=IMAGE_BG,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.schedule_render())
        self.window.bind("<Escape>", self.close_from_event)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.grab_set()
        self.canvas.focus_set()
        self.schedule_render()
        self.window.wait_window()

    def schedule_render(self) -> None:
        if self.render_job is not None:
            self.window.after_cancel(self.render_job)
        self.render_job = self.window.after(60, self.render)

    def render(self) -> None:
        self.render_job = None
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            return

        scale = min(
            canvas_width / self.image.width,
            canvas_height / self.image.height,
        )
        display_width = max(round(self.image.width * scale), 1)
        display_height = max(round(self.image.height * scale), 1)
        display = self.image.resize(
            (display_width, display_height),
            Image.Resampling.LANCZOS,
        )
        self.photo = ImageTk.PhotoImage(display)
        self.canvas.delete("all")
        self.canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.photo,
            anchor="center",
        )

    def close(self) -> None:
        if self.render_job is not None:
            self.window.after_cancel(self.render_job)
            self.render_job = None
        self.window.grab_release()
        self.window.destroy()

    def close_from_event(self, _event: tk.Event) -> str:
        self.close()
        return "break"


class ImageSplitApp:
    def __init__(
        self,
        root: tk.Tk,
        images: list[Path],
        *,
        webp_quality: int,
        decode_failures: list[tuple[Path, str]],
    ) -> None:
        self.root = root
        self.all_images = images
        self.images = list(images)
        self.webp_quality = webp_quality
        self.decode_failures = decode_failures
        self.index = 0

        self.current_image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.thumbnail_photos: list[ImageTk.PhotoImage] = []
        self.display_scale = 1.0
        self.display_box = (0, 0, 1, 1)
        self.drag_start: tuple[int, int] | None = None
        self.drag_end: tuple[int, int] | None = None
        self.selection: tuple[int, int, int, int] | None = None
        self.pointer_position: tuple[int, int] | None = None
        self.only_unsliced = tk.BooleanVar(value=False)
        self.marked_sliced = tk.BooleanVar(value=False)
        self.position_var = tk.DoubleVar(value=1.0)
        self.updating_position = False
        self.delete_pending = False
        self.render_job: str | None = None
        self.last_render_key: tuple[Path, int, int] | None = None

        self.root.title("Image Split")
        configure_dark_theme(self.root)
        self.center_window(width_ratio=0.9, height_ratio=0.88, margin=64)
        self.root.minsize(
            min(1400, self.root.winfo_screenwidth()),
            min(650, self.root.winfo_screenheight()),
        )

        self._build_ui()
        self._bind_events()
        self.load_current()

        if self.decode_failures:
            self.status_label.config(
                text=f"跳过 {len(self.decode_failures)} 个无法解码的文件"
            )

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

    @property
    def image_path(self) -> Path:
        return self.images[self.index]

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=(14, 12), style="App.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(2, weight=1)

        self.previous_button = ttk.Button(
            top,
            text="上一张",
            command=self.previous_image,
            takefocus=False,
        )
        self.previous_button.grid(row=0, column=0, padx=(0, 8))

        self.progress_label = ttk.Label(
            top,
            width=12,
            anchor="center",
            style="App.TLabel",
        )
        self.progress_label.grid(row=0, column=1, padx=(0, 8))

        self.position_scale = ttk.Scale(
            top,
            from_=1,
            to=max(len(self.images), 1),
            variable=self.position_var,
            command=self.preview_position,
            cursor="hand2",
        )
        self.position_scale.grid(row=0, column=2, sticky="ew")
        self.position_scale.bind("<ButtonRelease-1>", self.release_position_slider)

        self.next_button = ttk.Button(
            top,
            text="下一张",
            command=self.next_image,
            takefocus=False,
        )
        self.next_button.grid(row=0, column=3, padx=(8, 0))

        self.delete_button = ttk.Button(
            top,
            text="删除",
            command=self.handle_delete_button,
            takefocus=False,
            style="Danger.TButton",
        )
        self.delete_button.grid(row=0, column=4, padx=(12, 0))

        self.filter_button = ttk.Checkbutton(
            top,
            text="仅查看未切图",
            variable=self.only_unsliced,
            command=self.apply_filter,
            takefocus=False,
        )
        self.filter_button.grid(row=0, column=5, padx=(12, 0))

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

        image_panel = ttk.Frame(main, style="App.TFrame")
        image_panel.columnconfigure(0, weight=1)
        image_panel.rowconfigure(1, weight=1)
        main.add(image_panel, weight=5)

        self.file_label = ttk.Label(
            image_panel,
            anchor="center",
            style="Header.TLabel",
        )
        self.file_label.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.canvas = tk.Canvas(
            image_panel,
            background=IMAGE_BG,
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.grid(row=1, column=0, sticky="nsew")

        self.selection_actions = ttk.Frame(self.canvas, padding=6, style="Panel.TFrame")
        self.save_button = ttk.Button(
            self.selection_actions,
            text="保存 (Ctrl+S)",
            command=self.save_selection_from_button,
            takefocus=False,
        )
        self.save_button.pack(side="left", padx=(0, 8))
        self.preview_button = ttk.Button(
            self.selection_actions,
            text="预览 (Space)",
            command=self.preview_selection_from_button,
            takefocus=False,
        )
        self.preview_button.pack(side="left")

        self.status_label = ttk.Label(
            image_panel,
            text="拖动鼠标框选，Ctrl+S 保存切图",
            anchor="center",
            style="App.TLabel",
        )
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        thumbnail_panel = ttk.Frame(main, width=300, style="Panel.TFrame")
        thumbnail_panel.grid_propagate(False)
        thumbnail_panel.columnconfigure(0, weight=1)
        thumbnail_panel.rowconfigure(2, weight=1)
        main.add(thumbnail_panel, weight=1)

        self.mark_sliced_checkbox = ttk.Checkbutton(
            thumbnail_panel,
            text="标记为已切图",
            variable=self.marked_sliced,
            command=self.toggle_sliced_marker,
            takefocus=False,
        )
        self.mark_sliced_checkbox.grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        self.slice_count_label = ttk.Label(
            thumbnail_panel,
            text="暂无切图",
            anchor="center",
            style="Panel.TLabel",
        )
        self.slice_count_label.grid(
            row=1, column=0, sticky="ew", pady=(0, 6)
        )

        thumbnail_container = ttk.Frame(thumbnail_panel, style="Panel.TFrame")
        thumbnail_container.grid(row=2, column=0, sticky="nsew")
        thumbnail_container.columnconfigure(0, weight=1)
        thumbnail_container.rowconfigure(0, weight=1)

        self.thumbnail_canvas = tk.Canvas(
            thumbnail_container,
            width=260,
            background=PANEL_BG,
            highlightthickness=0,
        )
        self.thumbnail_canvas.grid(row=0, column=0, sticky="nsew")
        thumbnail_scrollbar = ttk.Scrollbar(
            thumbnail_container,
            orient="vertical",
            command=self.thumbnail_canvas.yview,
        )
        thumbnail_scrollbar.grid(row=0, column=1, sticky="ns")
        self.thumbnail_canvas.configure(yscrollcommand=thumbnail_scrollbar.set)

        self.thumbnail_frame = ttk.Frame(self.thumbnail_canvas, style="Panel.TFrame")
        self.thumbnail_window = self.thumbnail_canvas.create_window(
            (0, 0),
            window=self.thumbnail_frame,
            anchor="nw",
        )
        self.thumbnail_frame.bind("<Configure>", self._update_thumbnail_scrollregion)
        self.thumbnail_canvas.bind("<Configure>", self._resize_thumbnail_frame)

    def _bind_events(self) -> None:
        self.canvas.bind("<Configure>", lambda _event: self.schedule_render())
        self.canvas.bind("<ButtonPress-1>", self.start_selection)
        self.canvas.bind("<B1-Motion>", self.update_selection)
        self.canvas.bind("<ButtonRelease-1>", self.finish_selection)
        self.root.bind("<Control-s>", self.handle_save_shortcut)
        self.root.bind("<Control-S>", self.handle_save_shortcut)
        self.root.bind("<space>", self.handle_preview_shortcut)
        self.root.bind("<Escape>", self.handle_cancel_shortcut)
        self.root.bind("<Left>", lambda _event: self.previous_image())
        self.root.bind("<Right>", lambda _event: self.next_image())
        for widget in (
            self.previous_button,
            self.next_button,
            self.filter_button,
            self.delete_button,
            self.save_button,
            self.preview_button,
            self.mark_sliced_checkbox,
        ):
            widget.bind("<space>", self.handle_preview_shortcut)
            widget.bind(
                "<ButtonRelease-1>",
                self.return_focus_to_canvas,
                add="+",
            )
        self.root.after_idle(self.canvas.focus_set)

    def return_focus_to_canvas(self, _event: tk.Event | None = None) -> None:
        self.root.after_idle(self.canvas.focus_set)

    def _update_thumbnail_scrollregion(self, _event: tk.Event) -> None:
        self.thumbnail_canvas.configure(scrollregion=self.thumbnail_canvas.bbox("all"))

    def _resize_thumbnail_frame(self, event: tk.Event) -> None:
        self.thumbnail_canvas.itemconfigure(self.thumbnail_window, width=event.width)

    def load_current(self) -> None:
        started_at = time.perf_counter()
        self.reset_delete_button()
        with Image.open(self.image_path) as image:
            image.load()
            self.current_image = ImageOps.exif_transpose(image).copy()
        LOGGER.info(
            "加载大图：%s，尺寸 %d × %d，耗时 %.3f 秒",
            self.image_path.name,
            self.current_image.width,
            self.current_image.height,
            time.perf_counter() - started_at,
        )

        self.selection = None
        self.drag_start = None
        self.drag_end = None
        self.pointer_position = None
        self.last_render_key = None
        self.marked_sliced.set(is_marked_sliced(self.image_path))
        self.update_file_label()
        self.progress_label.config(text=f"{self.index + 1} / {len(self.images)}")
        self.updating_position = True
        self.position_var.set(float(self.index + 1))
        self.updating_position = False
        self.status_label.config(text="拖动鼠标框选，Ctrl+S 保存切图")
        self.schedule_render()
        self.load_thumbnails()
        self.return_focus_to_canvas()

    def reset_delete_button(self) -> None:
        self.delete_pending = False
        if hasattr(self, "delete_button"):
            self.delete_button.config(text="删除")

    def preview_position(self, _value: str) -> None:
        if self.updating_position:
            return

    def release_position_slider(self, _event: tk.Event) -> str:
        if not self.images:
            return "break"
        target_index = self.position_to_index(self.position_var.get())
        if target_index == self.index:
            self.updating_position = True
            self.position_var.set(float(self.index + 1))
            self.updating_position = False
            return "break"
        self.index = target_index
        self.load_current()
        return "break"

    def position_to_index(self, value: str | float) -> int:
        try:
            position = round(float(value))
        except (TypeError, ValueError):
            position = self.index + 1
        position = min(max(position, 1), len(self.images))
        return position - 1

    def update_file_label(self) -> None:
        if self.current_image is None:
            return
        width, height = self.current_image.size
        has_slices = bool(find_slice_paths(self.image_path))
        split_status = (
            "已切图"
            if is_marked_sliced(self.image_path) or has_slices
            else "待切图"
        )
        self.file_label.config(
            text=f"{self.image_path.name}  ·  {width} × {height}  ·  {split_status}"
        )

    def schedule_render(self) -> None:
        if self.render_job is not None:
            self.root.after_cancel(self.render_job)
        self.render_job = self.root.after(80, self.render_image)

    def render_image(self) -> None:
        self.render_job = None
        if self.current_image is None:
            return

        canvas_width = max(self.canvas.winfo_width(), 1)
        canvas_height = max(self.canvas.winfo_height(), 1)
        if canvas_width <= 1 or canvas_height <= 1:
            return
        render_key = (self.image_path, canvas_width, canvas_height)
        if render_key == self.last_render_key:
            self.draw_selection_overlay()
            return

        started_at = time.perf_counter()
        image_width, image_height = self.current_image.size
        self.display_scale = min(
            canvas_width / image_width,
            canvas_height / image_height,
            1.0,
        )
        display_width = max(int(image_width * self.display_scale), 1)
        display_height = max(int(image_height * self.display_scale), 1)
        offset_x = (canvas_width - display_width) // 2
        offset_y = (canvas_height - display_height) // 2
        self.display_box = (
            offset_x,
            offset_y,
            offset_x + display_width,
            offset_y + display_height,
        )

        display = self.current_image.resize(
            (display_width, display_height),
            Image.Resampling.LANCZOS,
        )
        self.photo = ImageTk.PhotoImage(display)
        self.canvas.delete("all")
        self.canvas.create_image(offset_x, offset_y, image=self.photo, anchor="nw")
        self.last_render_key = render_key
        self.draw_selection_overlay()
        render_seconds = time.perf_counter() - started_at
        LOGGER.log(
            logging.INFO if render_seconds >= 0.2 else logging.DEBUG,
            "渲染大图：显示尺寸 %d × %d，耗时 %.3f 秒",
            display_width,
            display_height,
            render_seconds,
        )

    def clamp_to_image(self, x: int, y: int) -> tuple[int, int]:
        left, top, right, bottom = self.display_box
        return min(max(x, left), right), min(max(y, top), bottom)

    def start_selection(self, event: tk.Event) -> None:
        self.selection = None
        self.pointer_position = (event.x, event.y)
        self.drag_start = self.clamp_to_image(event.x, event.y)
        self.drag_end = self.drag_start
        self.draw_selection_overlay()

    def update_selection(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        self.pointer_position = (event.x, event.y)
        self.drag_end = self.clamp_to_image(event.x, event.y)
        self.draw_selection_overlay()

    def finish_selection(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        self.pointer_position = (event.x, event.y)
        self.drag_end = self.clamp_to_image(event.x, event.y)
        x1, y1 = self.drag_start
        x2, y2 = self.drag_end
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        self.drag_start = None
        self.drag_end = None

        if right - left < 2 or bottom - top < 2:
            self.selection = None
            self.status_label.config(text="选区过小，请重新框选")
            self.draw_selection_overlay()
            return

        image_left, image_top, _, _ = self.display_box
        original_width, original_height = self.current_image.size
        original_left = max(math.floor((left - image_left) / self.display_scale), 0)
        original_top = max(math.floor((top - image_top) / self.display_scale), 0)
        original_right = min(
            math.ceil((right - image_left) / self.display_scale),
            original_width,
        )
        original_bottom = min(
            math.ceil((bottom - image_top) / self.display_scale),
            original_height,
        )
        self.selection = (
            original_left,
            original_top,
            original_right,
            original_bottom,
        )
        self.status_label.config(
            text=(
                f"选区 {original_right - original_left} × "
                f"{original_bottom - original_top}  ·  Ctrl+S 保存"
            )
        )
        self.draw_selection_overlay()

    def selection_on_canvas(self) -> tuple[int, int, int, int] | None:
        if self.drag_start is not None and self.drag_end is not None:
            x1, y1 = self.drag_start
            x2, y2 = self.drag_end
            return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        if self.selection is None:
            return None

        image_left, image_top, _, _ = self.display_box
        left, top, right, bottom = self.selection
        return (
            round(image_left + left * self.display_scale),
            round(image_top + top * self.display_scale),
            round(image_left + right * self.display_scale),
            round(image_top + bottom * self.display_scale),
        )

    def draw_selection_overlay(self) -> None:
        self.canvas.delete("selection_overlay")
        selection = self.selection_on_canvas()
        if selection is None:
            return

        image_left, image_top, image_right, image_bottom = self.display_box
        left, top, right, bottom = selection
        self.canvas.create_rectangle(
            image_left,
            image_top,
            image_right,
            top,
            fill="black",
            outline="",
            stipple="gray50",
            tags="selection_overlay",
        )
        self.canvas.create_rectangle(
            image_left,
            bottom,
            image_right,
            image_bottom,
            fill="black",
            outline="",
            stipple="gray50",
            tags="selection_overlay",
        )
        self.canvas.create_rectangle(
            image_left,
            top,
            left,
            bottom,
            fill="black",
            outline="",
            stipple="gray50",
            tags="selection_overlay",
        )
        self.canvas.create_rectangle(
            right,
            top,
            image_right,
            bottom,
            fill="black",
            outline="",
            stipple="gray50",
            tags="selection_overlay",
        )
        self.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            outline="#ffcc00",
            width=2,
            tags="selection_overlay",
        )
        self.draw_selection_size(left, top, right, bottom)
        if self.selection is not None and self.drag_start is None:
            self.canvas.create_window(
                image_right - 12,
                image_top + 12,
                window=self.selection_actions,
                anchor="ne",
                tags="selection_overlay",
            )

    def draw_selection_size(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
    ) -> None:
        if self.selection is not None and self.drag_start is None:
            selection_left, selection_top, selection_right, selection_bottom = (
                self.selection
            )
            width = selection_right - selection_left
            height = selection_bottom - selection_top
        else:
            width = max(round((right - left) / self.display_scale), 0)
            height = max(round((bottom - top) / self.display_scale), 0)

        pointer_x, pointer_y = self.pointer_position or (right, bottom)
        label_x = pointer_x + 14
        label_y = pointer_y + 14
        text_id = self.canvas.create_text(
            label_x,
            label_y,
            text=f"{width} × {height} px",
            fill="white",
            font=FONT_OVERLAY,
            anchor="nw",
            tags="selection_overlay",
        )
        text_box = self.canvas.bbox(text_id)
        if text_box is None:
            return

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        shift_x = min(canvas_width - text_box[2] - 8, 0)
        shift_y = min(canvas_height - text_box[3] - 8, 0)
        if shift_x or shift_y:
            self.canvas.move(text_id, shift_x, shift_y)
            text_box = self.canvas.bbox(text_id)
            if text_box is None:
                return

        background_id = self.canvas.create_rectangle(
            text_box[0] - 5,
            text_box[1] - 3,
            text_box[2] + 5,
            text_box[3] + 3,
            fill=IMAGE_BG,
            outline="#ffcc00",
            tags="selection_overlay",
        )
        self.canvas.tag_lower(background_id, text_id)

    def slice_paths(self) -> list[tuple[int, Path]]:
        return find_slice_paths(self.image_path)

    def handle_save_shortcut(self, _event: tk.Event) -> str:
        if self.selection is not None:
            self.save_selection()
        return "break"

    def save_selection_from_button(self) -> None:
        self.save_selection()
        self.return_focus_to_canvas()

    def handle_preview_shortcut(self, _event: tk.Event) -> str:
        if self.selection is not None:
            self.preview_selection()
        return "break"

    def preview_selection_from_button(self) -> None:
        self.preview_selection()
        self.return_focus_to_canvas()

    def handle_cancel_shortcut(self, _event: tk.Event) -> str:
        self.cancel_selection()
        self.reset_delete_button()
        return "break"

    def cancel_selection(self) -> None:
        self.selection = None
        self.drag_start = None
        self.drag_end = None
        self.pointer_position = None
        self.canvas.delete("selection_overlay")
        self.status_label.config(text="拖动鼠标框选，Ctrl+S 保存切图")

    def handle_delete_button(self) -> None:
        if not self.images:
            return
        if not self.delete_pending:
            self.delete_pending = True
            self.delete_button.config(text="确认删除")
            self.status_label.config(text=f"再次点击确认删除：{self.image_path.name}")
            self.return_focus_to_canvas()
            return
        self.delete_current_image()
        self.return_focus_to_canvas()

    def delete_current_image(self) -> None:
        delete_path = self.image_path
        caption_path = delete_path.with_suffix(".txt")
        deleted: list[Path] = []
        for path in (delete_path, caption_path):
            if path.exists():
                path.unlink()
                deleted.append(path)

        self.all_images = [path for path in self.all_images if path != delete_path]
        self.images = [path for path in self.images if path != delete_path]
        self.selection = None
        self.drag_start = None
        self.drag_end = None
        self.pointer_position = None
        self.current_image = None
        self.photo = None
        self.canvas.delete("all")
        self.thumbnail_photos.clear()
        for child in self.thumbnail_frame.winfo_children():
            child.destroy()

        LOGGER.info(
            "删除当前图片：%s，caption=%s",
            delete_path,
            caption_path if caption_path in deleted else "missing",
        )

        if not self.images:
            self.position_scale.configure(to=1)
            self.position_var.set(1.0)
            self.progress_label.config(text="0 / 0")
            self.file_label.config(text="没有剩余图片")
            self.status_label.config(text=f"已删除 {delete_path.name}，没有剩余图片")
            self.root.after(600, self.root.destroy)
            return

        self.index = min(self.index, len(self.images) - 1)
        self.position_scale.configure(to=max(len(self.images), 1))
        self.status_label.config(text=f"已删除 {delete_path.name}")
        self.load_current()

    def preview_selection(self) -> None:
        if self.current_image is None or self.selection is None:
            return
        preview = self.current_image.crop(self.selection)
        ImagePreviewDialog(self.root, preview, "切图预览")

    def open_slice_preview(self, path: Path) -> None:
        try:
            with Image.open(path) as image:
                image.load()
                preview = ImageOps.exif_transpose(image).copy()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            messagebox.showerror("无法预览", f"{path.name}\n{exc}")
            return
        ImagePreviewDialog(self.root, preview, path.name)

    def save_selection(self) -> None:
        if self.current_image is None or self.selection is None:
            messagebox.showinfo("未选择区域", "请先在图片上框选需要保存的区域。")
            return

        existing = self.slice_paths()
        next_number = existing[-1][0] + 1 if existing else 1
        output_path = self.image_path.with_name(
            f"{original_stem(self.image_path)}_slice_{next_number}.webp"
        )
        cropped = self.current_image.crop(self.selection)
        cropped.save(
            output_path,
            format="WEBP",
            quality=self.webp_quality,
            method=6,
        )
        self.status_label.config(text=f"已保存 {output_path.name}")
        self.selection = None
        self.pointer_position = None
        self.draw_selection_overlay()
        self.load_thumbnails()
        self.update_file_label()
        if self.only_unsliced.get():
            self.apply_filter()

    def load_thumbnails(self) -> None:
        started_at = time.perf_counter()
        for child in self.thumbnail_frame.winfo_children():
            child.destroy()
        self.thumbnail_photos.clear()

        paths = self.slice_paths()
        if not paths:
            self.slice_count_label.config(text="暂无切图")
            LOGGER.debug("当前图片没有已有切图")
            return

        self.slice_count_label.config(text=f"有 {len(paths)} 张切图")

        for _, path in paths:
            try:
                with Image.open(path) as image:
                    image.load()
                    thumbnail = ImageOps.exif_transpose(image).copy()
                thumbnail.thumbnail((230, 170), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(thumbnail)
                self.thumbnail_photos.append(photo)
                card = ttk.Frame(
                    self.thumbnail_frame,
                    padding=(6, 6, 6, 10),
                    style="Card.TFrame",
                )
                card.pack(fill="x", pady=(0, 8))
                image_label = ttk.Label(
                    card,
                    image=photo,
                    anchor="center",
                    cursor="hand2",
                    style="Image.TLabel",
                )
                image_label.pack(fill="x")
                image_label.bind(
                    "<Button-1>",
                    lambda _event, preview_path=path: self.open_slice_preview(
                        preview_path
                    ),
                )
                ttk.Label(
                    card,
                    text=path.name,
                    anchor="center",
                    style="Card.TLabel",
                ).pack(fill="x", pady=(6, 0))
            except (UnidentifiedImageError, OSError, ValueError):
                ttk.Label(
                    self.thumbnail_frame,
                    text=f"无法读取：{path.name}",
                    anchor="center",
                    style="Muted.Panel.TLabel",
                ).pack(fill="x", pady=4)
        thumbnail_seconds = time.perf_counter() - started_at
        LOGGER.log(
            logging.INFO if thumbnail_seconds >= 0.2 else logging.DEBUG,
            "加载切图缩略图：%d 张，耗时 %.3f 秒",
            len(paths),
            thumbnail_seconds,
        )

    def previous_image(self) -> None:
        if not self.images:
            return
        self.index = (self.index - 1) % len(self.images)
        self.load_current()

    def next_image(self) -> None:
        if not self.images:
            return
        self.index = (self.index + 1) % len(self.images)
        self.load_current()

    def apply_filter(self) -> None:
        current_path = self.image_path if self.images else None
        current_index = self.index
        if self.only_unsliced.get():
            self.images = [
                path
                for path in self.all_images
                if not is_marked_sliced(path) and not find_slice_paths(path)
            ]
        else:
            self.images = list(self.all_images)

        self.position_scale.configure(to=max(len(self.images), 1))
        if not self.images:
            self.index = 0
            self.current_image = None
            self.photo = None
            self.canvas.delete("all")
            self.file_label.config(text="没有符合筛选条件的图片")
            self.progress_label.config(text="0 / 0")
            self.position_var.set(1.0)
            self.status_label.config(text="全部大图都已有切图")
            self.slice_count_label.config(text="")
            for child in self.thumbnail_frame.winfo_children():
                child.destroy()
            self.previous_button.state(["disabled"])
            self.next_button.state(["disabled"])
            return

        self.previous_button.state(["!disabled"])
        self.next_button.state(["!disabled"])
        if current_path in self.images:
            self.index = self.images.index(current_path)
        else:
            self.index = min(current_index, len(self.images) - 1)
        self.load_current()

    def toggle_sliced_marker(self) -> None:
        if not self.images:
            self.marked_sliced.set(False)
            return

        old_path = self.image_path
        should_mark = self.marked_sliced.get()
        if should_mark == is_marked_sliced(old_path):
            return

        new_stem = original_stem(old_path) + ("_sliced" if should_mark else "")
        new_path = old_path.with_name(new_stem + old_path.suffix)
        old_caption = old_path.with_suffix(".txt")
        new_caption = new_path.with_suffix(".txt")

        if new_path.exists() or (old_caption.exists() and new_caption.exists()):
            self.marked_sliced.set(is_marked_sliced(old_path))
            messagebox.showerror(
                "无法重命名",
                f"目标文件已存在：{new_path.name}",
            )
            return

        try:
            old_path.rename(new_path)
            if old_caption.exists():
                old_caption.rename(new_caption)
        except Exception as exc:
            if new_caption.exists() and not old_caption.exists():
                new_caption.rename(old_caption)
            if new_path.exists() and not old_path.exists():
                new_path.rename(old_path)
            self.marked_sliced.set(is_marked_sliced(old_path))
            messagebox.showerror("无法重命名", str(exc))
            return

        self.all_images = [
            new_path if path == old_path else path for path in self.all_images
        ]
        self.images = [new_path if path == old_path else path for path in self.images]
        self.index = self.images.index(new_path)
        LOGGER.info("更新切图标记：%s -> %s", old_path.name, new_path.name)
        self.update_file_label()
        self.load_thumbnails()
        if self.only_unsliced.get() and should_mark:
            self.apply_filter()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select and save slices from source images with a long side over a threshold."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("train/anima/data"),
    )
    parser.add_argument("--max-side", type=int, default=2048)
    parser.add_argument("--webp-quality", type=int, default=98)
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_side < 1:
        raise SystemExit("--max-side must be greater than 0")
    if not 0 <= args.webp_quality <= 100:
        raise SystemExit("--webp-quality must be between 0 and 100")

    data_dir = args.data_dir.resolve()
    log_path = configure_logging(data_dir, args.log_level)
    startup_started_at = time.perf_counter()
    LOGGER.info("启动 Image Split")
    LOGGER.info("日志文件：%s", log_path)
    dpi_awareness = enable_windows_dpi_awareness()
    LOGGER.info("Windows DPI awareness：%s", dpi_awareness)
    try:
        images, failures = find_large_images(
            data_dir,
            args.max_side,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    LOGGER.info("创建 Tk window")
    root = tk.Tk()
    dpi = configure_tk_for_windows(root)
    LOGGER.info(
        "Tk %s，monitor DPI %.1f，tk scaling %s",
        root.tk.call("info", "patchlevel"),
        dpi,
        root.tk.call("tk", "scaling"),
    )
    if not images:
        messagebox.showinfo(
            "没有待切图片",
            f"指定目录中没有长边大于 {args.max_side} 的未切图文件。",
            parent=root,
        )
        root.destroy()
        return

    ImageSplitApp(
        root,
        images,
        webp_quality=args.webp_quality,
        decode_failures=failures,
    )
    LOGGER.info("GUI 启动完成，总耗时 %.3f 秒", time.perf_counter() - startup_started_at)
    root.mainloop()


if __name__ == "__main__":
    main()
