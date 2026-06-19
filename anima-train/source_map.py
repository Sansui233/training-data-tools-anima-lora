from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


class SourceMap:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = {"version": 1, "source_images": {}}

    def __enter__(self) -> SourceMap:
        if self.path.is_file():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or not isinstance(
                loaded.get("source_images"), dict
            ):
                raise ValueError(f"invalid source map: {self.path}")
            self.data = loaded
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.save()

    @property
    def images(self) -> dict[str, dict[str, Any]]:
        return self.data["source_images"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_key(source_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(source_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def connect(source_map_path: Path) -> SourceMap:
    return SourceMap(source_map_path)


def get_mapping(source_map: SourceMap, key: str) -> dict[str, Any] | None:
    return source_map.images.get(key)


def mapped_artifacts(
    mapping: Mapping[str, Any],
) -> tuple[Path, Path, bool, bool]:
    image_path = Path(mapping["output_path"]).resolve()
    caption_path = image_path.with_suffix(".txt")
    return image_path, caption_path, image_path.is_file(), caption_path.is_file()


def upsert_mapping(
    source_map: SourceMap,
    *,
    key: str,
    source_path: Path,
    source_hash: str,
    output_path: Path,
    output_format: str,
    output_quality: int | None,
    output_lossless: bool,
    width: int,
    height: int,
    mode: str,
) -> None:
    stat = source_path.stat()
    now = datetime.now(UTC).isoformat()
    existing = source_map.images.get(key, {})
    source_map.images[key] = {
        "source_key": key,
        "source_path": str(source_path),
        "source_hash": source_hash,
        "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "output_path": str(output_path),
        "output_format": output_format,
        "output_quality": output_quality,
        "output_lossless": output_lossless,
        "width": width,
        "height": height,
        "mode": mode,
        "converted_at": existing.get("converted_at", now),
        "updated_at": now,
    }
    source_map.save()