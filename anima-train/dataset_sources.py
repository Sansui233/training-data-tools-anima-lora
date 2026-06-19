from __future__ import annotations

from pathlib import Path
from typing import Iterable


TRAINING_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def collect_source_files(
    source_root: Path,
    source_dirs: Iterable[Path],
) -> list[Path]:
    """Return direct child files from selected source directories without recursion."""
    source_root = source_root.resolve()
    inputs: set[Path] = set()
    for source_dir in source_dirs:
        selected_dir = source_dir.resolve()
        try:
            relative_dir = selected_dir.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"source directory is outside {source_root}: {source_dir}") from exc
        if len(relative_dir.parts) not in (1, 2):
            raise ValueError(
                f"source directory must be at depth 1 or 2 under {source_root}: {source_dir}"
            )
        if not selected_dir.is_dir():
            raise FileNotFoundError(f"source subdirectory does not exist: {selected_dir}")
        inputs.update(path for path in selected_dir.iterdir() if path.is_file())
    return sorted(inputs, key=lambda path: path.as_posix().casefold())


def collect_training_images(data_dir: Path) -> list[Path]:
    if not data_dir.is_dir():
        raise FileNotFoundError(f"training data directory does not exist: {data_dir}")
    return sorted(
        (
            path
            for path in data_dir.iterdir()
            if path.is_file() and path.suffix.lower() in TRAINING_IMAGE_EXTENSIONS
        ),
        key=lambda path: path.as_posix().casefold(),
    )
