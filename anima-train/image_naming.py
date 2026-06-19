from __future__ import annotations

import re
from pathlib import Path


SLICE_SUFFIX_PATTERN = re.compile(r"_slice_(\d+)$", re.IGNORECASE)
SLICED_SUFFIX_PATTERN = re.compile(r"_sliced$", re.IGNORECASE)


def parse_image_stem(stem: str) -> tuple[str, int | None]:
    original = stem
    slice_number: int | None = None
    while True:
        sliced_match = SLICED_SUFFIX_PATTERN.search(original)
        if sliced_match:
            original = original[: sliced_match.start()]
            continue
        slice_match = SLICE_SUFFIX_PATTERN.search(original)
        if slice_match:
            if slice_number is None:
                slice_number = int(slice_match.group(1))
            original = original[: slice_match.start()]
            continue
        return original, slice_number


def original_stem(path: Path) -> str:
    return parse_image_stem(path.stem)[0]


def slice_number(path: Path) -> int | None:
    return parse_image_stem(path.stem)[1]


def is_slice_image(path: Path) -> bool:
    return slice_number(path) is not None


def is_marked_sliced(path: Path) -> bool:
    return SLICED_SUFFIX_PATTERN.search(path.stem) is not None
