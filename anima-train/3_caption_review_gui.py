from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from dataset_sources import collect_training_images


class CaptionReviewApp:
    def __init__(self, root: tk.Tk, data_dir: Path) -> None:
        self.root = root
        self.data_dir = data_dir
        self.images = collect_training_images(data_dir)
        self.index = 0
        self.current_image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.dirty = False

        self.root.title("Caption Review")
        self.root.geometry("1280x820")
        self.root.minsize(900, 560)

        self._build_ui()
        self._bind_keys()

        if not self.images:
            messagebox.showerror("No images", f"No training images found in {data_dir}")
            self.root.destroy()
            return

        self.load_current()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=8)
        left.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self.image_label = ttk.Label(left, anchor="center")
        self.image_label.grid(row=0, column=0, sticky="nsew")
        self.image_label.bind("<Configure>", lambda _event: self.render_image())

        right = ttk.Frame(self.root, padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        self.file_label = ttk.Label(right)
        self.file_label.grid(row=0, column=0, sticky="ew")

        self.status_label = ttk.Label(right)
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(4, 8))

        self.caption_text = tk.Text(right, wrap="word", undo=True, font=("Consolas", 12))
        self.caption_text.grid(row=2, column=0, sticky="nsew")
        self.caption_text.bind("<<Modified>>", self.on_text_modified)

        button_row = ttk.Frame(right)
        button_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        button_row.columnconfigure(2, weight=1)

        ttk.Button(button_row, text="Previous", command=self.previous_image).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(button_row, text="Next", command=self.next_image).grid(
            row=0, column=1, padx=(0, 6)
        )
        ttk.Button(button_row, text="Save", command=self.save_caption).grid(
            row=0, column=3
        )

    def _bind_keys(self) -> None:
        self.root.bind("<Control-s>", lambda _event: self.save_caption())
        self.root.bind("<Control-S>", lambda _event: self.save_caption())
        self.root.bind("<Alt-Left>", lambda _event: self.previous_image())
        self.root.bind("<Alt-Right>", lambda _event: self.next_image())
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
            self.caption_text.edit_modified(False)

    def update_status(self) -> None:
        marker = "modified" if self.dirty else "saved"
        self.status_label.config(text=f"{self.index + 1}/{len(self.images)} - {marker}")

    def load_current(self) -> None:
        self.current_image = Image.open(self.image_path).convert("RGB")
        caption = ""
        if self.caption_path.exists():
            caption = self.caption_path.read_text(encoding="utf-8").strip()

        self.file_label.config(text=self.image_path.name)
        self.caption_text.delete("1.0", "end")
        self.caption_text.insert("1.0", caption)
        self.caption_text.edit_reset()
        self.caption_text.edit_modified(False)
        self.dirty = False
        self.update_status()
        self.render_image()

    def render_image(self) -> None:
        if self.current_image is None:
            return

        box_width = max(self.image_label.winfo_width(), 1)
        box_height = max(self.image_label.winfo_height(), 1)
        width, height = self.current_image.size
        scale = min(box_width / width, box_height / height, 1.0)
        display_size = (max(int(width * scale), 1), max(int(height * scale), 1))
        display = self.current_image.resize(display_size, Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(display)
        self.image_label.config(image=self.photo)

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
            self.root.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review training images and edit captions.")
    parser.add_argument("--data-dir", type=Path, default=Path("train/anima/data"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = tk.Tk()
    CaptionReviewApp(root, args.data_dir.resolve())
    root.mainloop()


if __name__ == "__main__":
    main()
