---
name: replace-training-image
description: Safely replace an Anima dataset image by converting a source image to WebP quality 98 in the raw data directory, optionally deleting the original source image, and optionally replacing the matching file in a training data directory. Use when the user asks to replace, convert, overwrite, or update an image in this Anima dataset project, especially when matching source raw images to hashed or sliced training images.
---

# Replace Training Image

Use this workflow for project-level image replacement from `F:\AI\Datasets\images`.
The dataset scripts live in `anima-train`, raw images live under `raws`, and training data lives under `train`.

## Required Inputs

When the user asks to replace an image, gather these paths before doing destructive work:

1. Source image path in the raw data directory.
2. Replaced file path in the raw data directory, usually the WebP path created beside the source image.
3. Training data directory or target training file path, optional.

If any required path is unclear, ask for it before converting or deleting files.

## Workflow

1. Inspect the project context before writing:
   - Read or reuse `anima-train\1_convert_image.py`.
   - Confirm the source image exists.
   - Confirm whether the raw WebP output path already exists.
   - If a training data path is provided, inspect that directory or target file before replacing anything.

2. Convert the source image:
   - Call `convert_image()` from `anima-train\1_convert_image.py` instead of reimplementing conversion.
   - Use `output_format="webp"`, `webp_quality=98`, and `webp_lossless=False`.
   - Save the output to the raw data directory unless the user explicitly gives another raw output path.
   - Preserve dimensions and EXIF orientation through the existing converter.

3. Find the training replacement candidate when a training data directory is provided:
   - Compare source and target by normalized basename, not by exact filename.
   - Ignore status suffixes: `_sliced` and `_slice_<number>`.
   - Ignore trailing hash chunks like `_d2e662d7d4`; remove one or more trailing underscore-prefixed hex chunks of 8 to 16 characters before comparing.
   - Prefer a single existing WebP candidate whose normalized basename matches the source WebP normalized basename.
   - If multiple candidates match, list them and ask the user which one to replace.
   - If no candidate matches, report that and ask whether to use an explicitly named target file.

4. Confirm before replacing training data:
   - Show the source WebP file path.
   - Show the exact target training file path that would be overwritten.
   - Ask for confirmation before copying over the target file.
   - Do not overwrite a training file based only on a guessed match.

5. Delete the original source image only after a successful WebP conversion:
   - If the user already requested deletion, delete the original after conversion succeeds.
   - If deletion was not explicitly requested, ask before deleting.
   - Use `Remove-Item -LiteralPath` for deletion on Windows.

6. Verify after writes:
   - Confirm the original source image exists or has been deleted as intended.
   - Confirm the raw WebP exists.
   - If training data was replaced, confirm the target file exists.
   - Open the raw WebP and target WebP with PIL and report format, dimensions, and mode.
   - Compare file sizes when raw and training target should be identical.

## Matching Helper

Use this normalization logic when scanning a training data directory:

```python
import re
from pathlib import Path

STATUS_SUFFIX_RE = re.compile(r"(_sliced|_slice_\d+)$", re.IGNORECASE)
HASH_SUFFIX_RE = re.compile(r"_[0-9a-f]{8,16}$", re.IGNORECASE)

def normalized_image_base(path: Path) -> str:
    stem = path.stem
    changed = True
    while changed:
        changed = False
        new_stem = STATUS_SUFFIX_RE.sub("", stem)
        if new_stem != stem:
            stem = new_stem
            changed = True
            continue
        new_stem = HASH_SUFFIX_RE.sub("", stem)
        if new_stem != stem:
            stem = new_stem
            changed = True
    return stem.casefold()
```

When matching the recent example:

- Source WebP: `HFx_SCkbkAADov0_6f430aa137.webp`
- Target candidate: `HFx_SCkbkAADov0_6f430aa137_d2e662d7d4.webp`
- Both normalize to `hfx_sckbkaadov0`, so the target is a candidate, but still requires user confirmation before overwrite.

## Safety Rules

- Never use recursive deletion for this workflow.
- Never delete the source image before confirming conversion succeeded.
- Never replace more than one training file without explicit user confirmation.
- Keep local filenames unchanged except for the requested raw WebP output and explicit target overwrite.
- Do not modify captions unless the user explicitly asks for caption changes.
