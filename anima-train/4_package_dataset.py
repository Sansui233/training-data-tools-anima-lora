from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from dataset_sources import collect_training_images


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate image/caption pairs and package the training dataset."
    )
    parser.add_argument("--target-dir", type=Path, default=Path("train/anima"))
    parser.add_argument(
        "--dataset-config",
        type=Path,
        default=Path("anima-train/dataset_config.toml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("anima-train/atomsphere_anima_train_package.zip"),
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_dir = args.target_dir.resolve()
    data_dir = (target_dir / "data").resolve()
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

    try:
        training_images = collect_training_images(data_dir)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    problems: list[str] = []
    pairs: list[tuple[Path, Path]] = []
    for image_path in training_images:
        caption_path = image_path.with_suffix(".txt")
        if not caption_path.is_file():
            problems.append(f"caption is missing: {caption_path}")
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
        for image_path, caption_path in pairs:
            archive.write(image_path, f"anima-train/data/{image_path.name}")
            archive.write(caption_path, f"anima-train/data/{caption_path.name}")

    print(f"packaged {len(pairs)} image/caption pairs -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
