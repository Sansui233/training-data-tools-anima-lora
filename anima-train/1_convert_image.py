from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import shutil
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from dataset_sources import (
    collect_caption_files,
    collect_source_files,
    collect_training_images,
    find_caption_for_image,
)
from image_naming import original_stem


def default_worker_count() -> int:
    cpu_count = os.cpu_count() or 4
    return max(1, min(32, cpu_count))


def resolve_worker_count(requested_workers: int, job_count: int) -> int:
    if job_count < 1:
        return 0
    worker_count = default_worker_count() if requested_workers == 0 else requested_workers
    return max(1, min(worker_count, job_count))


def convert_image(
    src: Path,
    dst: Path,
    *,
    output_format: str,
    webp_quality: int,
    webp_lossless: bool,
    jpg_quality: int,
    jpg_max_side: int,
) -> dict[str, object]:
    with Image.open(src) as image:
        source_width, source_height = image.size

    if (
        output_format == "jpg"
        and src.suffix.lower() in {".jpg", ".jpeg"}
        and max(source_width, source_height) <= jpg_max_side
    ):
        shutil.copy2(src, dst)
        with Image.open(dst) as image:
            width, height = image.size
            mode = image.mode
        return {
            "source": str(src),
            "output": str(dst),
            "width": width,
            "height": height,
            "mode": mode,
            "copied_without_reencode": True,
        }

    with Image.open(src) as image:
        image.load()
        normalized = ImageOps.exif_transpose(image)
        if normalized.mode in {"RGBA", "LA"}:
            output = normalized
        elif normalized.mode == "P" and "transparency" in normalized.info:
            output = normalized.convert("RGBA")
        else:
            output = normalized.convert("RGB")

        if output_format == "webp":
            output.save(
                dst,
                format="WEBP",
                quality=webp_quality,
                lossless=webp_lossless,
                method=6,
            )
        elif output_format == "jpg":
            if output.mode in {"RGBA", "LA"} or (
                output.mode == "P" and "transparency" in output.info
            ):
                rgba_output = output.convert("RGBA")
                background = Image.new("RGB", rgba_output.size, (255, 255, 255))
                background.paste(rgba_output, mask=rgba_output.getchannel("A"))
                output = background
            else:
                output = output.convert("RGB")
            if max(output.size) > jpg_max_side:
                scale = jpg_max_side / max(output.size)
                output = output.resize(
                    (round(output.width * scale), round(output.height * scale)),
                    Image.Resampling.LANCZOS,
                )
            output.save(
                dst,
                format="JPEG",
                quality=jpg_quality,
                subsampling=0,
                optimize=True,
            )
        else:
            output.save(dst, format="PNG")

        return {
            "source": str(src),
            "output": str(dst),
            "width": output.width,
            "height": output.height,
            "mode": output.mode,
            "copied_without_reencode": False,
        }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def collect_existing_image_names(
    train_root: Path,
    out_dir: Path,
) -> dict[str, Path]:
    """Collect original image basenames from train/*/data once per run."""
    data_dirs = {
        path.resolve()
        for path in train_root.glob("*/data")
        if path.is_dir()
    }
    data_dirs.add(out_dir.resolve())

    existing: dict[str, Path] = {}
    for data_dir in sorted(data_dirs, key=lambda path: path.as_posix().casefold()):
        if not data_dir.is_dir():
            continue
        for image_path in collect_training_images(data_dir):
            existing.setdefault(original_stem(image_path), image_path)
    return existing


def collect_captions_by_dir(image_paths: list[Path]) -> dict[Path, list[Path]]:
    captions_by_dir: dict[Path, list[Path]] = {}
    for parent in sorted(
        {path.parent.resolve() for path in image_paths},
        key=lambda path: path.as_posix().casefold(),
    ):
        captions_by_dir[parent] = collect_caption_files(parent)
    return captions_by_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Incrementally compile readable source images into a training dataset."
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
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--format", choices=("webp", "png", "jpg"), default="webp")
    parser.add_argument("--webp-quality", type=int, default=98)
    parser.add_argument("--webp-lossless", action="store_true")
    parser.add_argument("--jpg-quality", type=int, default=100)
    parser.add_argument("--jpg-max-side", type=int, default=4096)
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel conversion workers; 0 chooses an automatic CPU-based default",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 <= args.webp_quality <= 100:
        raise SystemExit("--webp-quality must be between 0 and 100")
    if not 1 <= args.jpg_quality <= 100:
        raise SystemExit("--jpg-quality must be between 1 and 100")
    if args.jpg_max_side < 1:
        raise SystemExit("--jpg-max-side must be at least 1")
    if args.workers < 0:
        raise SystemExit("--workers must be at least 0")

    source_root = Path("raws").resolve()
    target_dir = args.target_dir.resolve()
    out_dir = (args.out_dir or target_dir / "data").resolve()
    report_dir = (args.report_dir or target_dir / "reports").resolve()

    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    converted: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    source_dirs = args.source_dirs
    try:
        inputs = collect_source_files(source_root, source_dirs)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    existing_images = collect_existing_image_names(Path("train").resolve(), out_dir)
    captions_by_dir = collect_captions_by_dir(list(existing_images.values()))
    captions_by_dir.setdefault(
        out_dir.resolve(),
        collect_caption_files(out_dir) if out_dir.is_dir() else [],
    )
    jobs: list[tuple[Path, Path]] = []
    for src in inputs:
        dst = out_dir / f"{src.stem}.{args.format}"
        output_original_name = original_stem(dst)
        existing_image = existing_images.get(output_original_name)
        if existing_image is not None and not args.force:
            caption_path = find_caption_for_image(
                existing_image,
                captions_by_dir.get(existing_image.parent.resolve()),
            )
            skipped.append(
                {
                    "source": str(src),
                    "output": str(existing_image),
                    "caption": str(caption_path) if caption_path else str(existing_image.with_suffix(".txt")),
                    "image_exists": True,
                    "caption_exists": caption_path is not None,
                    "reason": "same basename output exists",
                }
            )
            status = "caption exists" if caption_path else "caption missing"
            print(f"skipped {src.name}: same basename output exists; {status}")
            continue

        jobs.append((src, dst))
        existing_images[output_original_name] = dst

    worker_count = resolve_worker_count(args.workers, len(jobs))
    if jobs:
        print(f"converting {len(jobs)} image(s) with {worker_count} worker(s)")

    if worker_count:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    convert_image,
                    src,
                    dst,
                    output_format=args.format,
                    webp_quality=args.webp_quality,
                    webp_lossless=args.webp_lossless,
                    jpg_quality=args.jpg_quality,
                    jpg_max_side=args.jpg_max_side,
                ): (src, dst)
                for src, dst in jobs
            }
            for future in as_completed(futures):
                src, dst = futures[future]
                try:
                    result = future.result()
                    converted.append(result)
                    action = "copied" if result.get("copied_without_reencode") else "converted"
                    print(f"{action} {src.name} -> {dst.name}")
                except (UnidentifiedImageError, OSError, ValueError) as exc:
                    failed.append({"source": str(src), "error": f"{type(exc).__name__}: {exc}"})
                    print(f"failed {src.name}: {type(exc).__name__}: {exc}")

    write_jsonl(report_dir / "converted_images.jsonl", converted)
    write_jsonl(report_dir / "skipped_conversions.jsonl", skipped)
    write_jsonl(report_dir / "failed_conversions.jsonl", failed)

    summary = {
        "input_count": len(inputs),
        "converted_count": len(converted),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "source_root": str(source_root),
        "source_dirs": [str(path.resolve()) for path in source_dirs],
        "target_dir": str(target_dir),
        "output_dir": str(out_dir),
        "output_format": args.format,
        "webp_quality": args.webp_quality if args.format == "webp" else None,
        "webp_lossless": args.webp_lossless if args.format == "webp" else None,
        "jpg_quality": args.jpg_quality if args.format == "jpg" else None,
        "jpg_max_side": args.jpg_max_side if args.format == "jpg" else None,
        "workers": worker_count,
        "requested_workers": args.workers,
        "failed_report": str(report_dir / "failed_conversions.jsonl"),
    }
    (report_dir / "conversion_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

