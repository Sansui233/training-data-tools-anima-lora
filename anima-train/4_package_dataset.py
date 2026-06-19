from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from dataset_sources import collect_source_files
from source_map import connect, get_mapping, mapped_artifacts, source_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate mapped image/caption pairs and package the training dataset."
    )
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        dest="source_dirs",
        required=True,
        help="Depth-1 or depth-2 directory under raws; repeat to select multiple",
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
    source_root = Path("raws").resolve()
    source_dirs = args.source_dirs
    target_dir = args.target_dir.resolve()
    data_dir = (target_dir / "data").resolve()
    source_map_path = data_dir / "sourmap.json"
    dataset_config = args.dataset_config.resolve()
    output_path = args.output.resolve()

    try:
        source_inputs = collect_source_files(source_root, source_dirs)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    if not source_map_path.is_file():
        raise SystemExit(f"source map does not exist: {source_map_path}")
    if not dataset_config.is_file():
        raise SystemExit(f"dataset config does not exist: {dataset_config}")

    pairs: list[tuple[Path, Path]] = []
    problems: list[str] = []
    seen_outputs: set[Path] = set()
    with connect(source_map_path) as source_map:
        for src in source_inputs:
            mapping = get_mapping(source_map, source_key(source_root, src))
            if mapping is None:
                problems.append(f"no source map entry: {src}")
                continue
            image_path, caption_path, image_exists, caption_exists = mapped_artifacts(
                mapping
            )
            if image_path.parent != data_dir:
                problems.append(f"mapped image is outside target data directory: {image_path}")
                continue
            if not image_exists:
                problems.append(f"mapped target image is missing: {image_path}")
            if not caption_exists:
                problems.append(f"mapped caption is missing: {caption_path}")
            if image_exists and caption_exists:
                if image_path in seen_outputs:
                    problems.append(f"duplicate mapped target image: {image_path}")
                    continue
                seen_outputs.add(image_path)
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
