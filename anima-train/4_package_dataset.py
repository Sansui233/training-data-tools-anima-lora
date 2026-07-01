from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from dataset_sources import collect_caption_files, collect_training_images, find_caption_for_image


def archive_safe_stem(stem: str) -> str:
    cleaned = "".join(
        char if char.isascii() and (char.isalnum() or char in "-_") else "_"
        for char in stem
    ).strip("_")
    if cleaned == stem and cleaned:
        return stem
    digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned or 'image'}_{digest}"


def unique_archive_name(path: Path, used_names: set[str]) -> str:
    base = archive_safe_stem(path.stem)
    candidate = f"{base}{path.suffix.lower()}"
    index = 2
    while candidate.casefold() in used_names:
        candidate = f"{base}_{index}{path.suffix.lower()}"
        index += 1
    used_names.add(candidate.casefold())
    return candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate image/caption pairs and package the training dataset."
    )
    parser.add_argument("--target-dir", type=Path, default=Path("train/anima"))
    parser.add_argument(
        "--source-dir",
        type=Path,
        action="append",
        dest="source_dirs",
        default=None,
        help="Training dataset directory containing data/; repeat to package multiple sources.",
    )
    parser.add_argument(
        "--dataset-config",
        type=Path,
        default=Path("anima-train/dataset_config.toml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("anima-train/anima_train_package.zip"),
    )
    parser.add_argument(
        "--training-script",
        type=Path,
        default=Path("anima-train/train_anima_lora_4090.sh"),
    )
    parser.add_argument(
        "--training-notes",
        type=Path,
        default=Path("anima-train/AUTODL_TRAINING.md"),
    )
    parser.add_argument(
        "--skip-missing-caption",
        action="store_true",
        help="Skip images without matching captions instead of failing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dirs = args.source_dirs or [args.target_dir]
    data_dirs = [(source_dir.resolve() / "data").resolve() for source_dir in source_dirs]
    dataset_config = args.dataset_config.resolve()
    training_script = args.training_script.resolve()
    training_notes = args.training_notes.resolve()
    output_path = args.output.resolve()

    if not dataset_config.is_file():
        raise SystemExit(f"dataset config does not exist: {dataset_config}")
    if not training_script.is_file():
        raise SystemExit(f"training script does not exist: {training_script}")
    if not training_notes.is_file():
        raise SystemExit(f"training notes do not exist: {training_notes}")

    problems: list[str] = []
    skipped_missing_caption: list[str] = []
    pairs: list[tuple[Path, Path]] = []
    source_counts: dict[str, int] = {}
    for data_dir in data_dirs:
        try:
            training_images = collect_training_images(data_dir)
            caption_files = collect_caption_files(data_dir)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc

        source_counts[str(data_dir)] = len(training_images)
        for image_path in training_images:
            caption_path = find_caption_for_image(image_path, caption_files)
            if caption_path is None:
                message = f"caption is missing for basename: {image_path.stem} in {data_dir}"
                if args.skip_missing_caption:
                    skipped_missing_caption.append(message)
                else:
                    problems.append(message)
                continue
            pairs.append((image_path, caption_path))

    if problems:
        for problem in problems:
            print(f"error: {problem}")
        raise SystemExit(f"dataset is incomplete: {len(problems)} problem(s)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(dataset_config, "anima-train/dataset_config.toml")
        archive.write(training_script, "anima-train/train_anima_lora_4090.sh")
        archive.write(training_notes, "anima-train/AUTODL_TRAINING.md")
        used_names: set[str] = set()
        for image_path, caption_path in pairs:
            archive_image_name = unique_archive_name(image_path, used_names)
            archive_caption_name = f"{Path(archive_image_name).stem}.txt"
            archive.write(image_path, f"anima-train/data/{archive_image_name}")
            archive.write(caption_path, f"anima-train/data/{archive_caption_name}")

    for data_dir, count in source_counts.items():
        print(f"source {data_dir}: {count} images")
    for skipped in skipped_missing_caption:
        print(f"skipped: {skipped}")
    print(f"packaged {len(pairs)} image/caption pairs -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
