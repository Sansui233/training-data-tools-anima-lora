from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from dataset_sources import collect_training_images
from source_map import connect, mapped_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate mapped image/caption pairs and package the training dataset."
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_dir = args.target_dir.resolve()
    data_dir = (target_dir / "data").resolve()
    source_map_path = data_dir / "sourmap.json"
    dataset_config = args.dataset_config.resolve()
    output_path = args.output.resolve()

    if not source_map_path.is_file():
        raise SystemExit(f"source map does not exist: {source_map_path}")
    if not dataset_config.is_file():
        raise SystemExit(f"dataset config does not exist: {dataset_config}")

    try:
        training_images = collect_training_images(data_dir)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    problems: list[str] = []
    with connect(source_map_path) as source_map:
        for mapping in source_map.images.values():
            image_path, _, image_exists, _ = mapped_artifacts(
                mapping
            )
            if image_path.parent != data_dir:
                problems.append(f"mapped image is outside target data directory: {image_path}")
                continue
            if not image_exists:
                problems.append(f"mapped target image is missing: {image_path}")

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
        for image_path, caption_path in pairs:
            archive.write(image_path, f"anima-train/data/{image_path.name}")
            archive.write(caption_path, f"anima-train/data/{caption_path.name}")

    print(f"packaged {len(pairs)} image/caption pairs -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
