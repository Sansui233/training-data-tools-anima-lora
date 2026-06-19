from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from dataset_sources import collect_source_files
from image_naming import original_stem
from source_map import (
    connect,
    file_sha256,
    get_mapping,
    mapped_artifacts,
    source_key,
    upsert_mapping,
)


def safe_stem(path: Path) -> str:
    cleaned = "".join(
        char if char.isascii() and (char.isalnum() or char in "-_") else "_"
        for char in path.stem
    ).strip("_")
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return f"{cleaned or 'image'}_{digest}"


def convert_image(
    src: Path,
    dst: Path,
    *,
    output_format: str,
    webp_quality: int,
    webp_lossless: bool,
) -> dict[str, object]:
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
        else:
            output.save(dst, format="PNG")

        return {
            "source": str(src),
            "output": str(dst),
            "width": output.width,
            "height": output.height,
            "mode": output.mode,
        }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


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
    parser.add_argument("--format", choices=("webp", "png"), default="webp")
    parser.add_argument("--webp-quality", type=int, default=98)
    parser.add_argument("--webp-lossless", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 <= args.webp_quality <= 100:
        raise SystemExit("--webp-quality must be between 0 and 100")

    source_root = Path("raws").resolve()
    target_dir = args.target_dir.resolve()
    out_dir = (args.out_dir or target_dir / "data").resolve()
    report_dir = (args.report_dir or target_dir / "reports").resolve()
    source_map_path = out_dir / "sourmap.json"

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

    with connect(source_map_path) as source_map:
        for src in inputs:
            key = source_key(source_root, src)
            dst = out_dir / f"{safe_stem(src)}.{args.format}"
            try:
                digest = file_sha256(src)
                existing = get_mapping(source_map, key)
                if existing is not None:
                    (
                        mapped_image_path,
                        caption_path,
                        image_exists,
                        caption_exists,
                    ) = mapped_artifacts(existing)
                else:
                    mapped_image_path = dst
                    caption_path = dst.with_suffix(".txt")
                    image_exists = False
                    caption_exists = False
                if (
                    not args.force
                    and existing is not None
                    and existing["source_hash"] == digest
                    and mapped_image_path.parent == out_dir
                    and mapped_image_path.suffix.lower() == dst.suffix.lower()
                    and original_stem(mapped_image_path) == original_stem(dst)
                    and existing["output_format"] == args.format
                    and existing["output_quality"] == (
                        args.webp_quality if args.format == "webp" else None
                    )
                    and bool(existing["output_lossless"]) == (
                        args.webp_lossless if args.format == "webp" else False
                    )
                    and image_exists
                ):
                    skipped.append(
                        {
                            "source": str(src),
                            "output": existing["output_path"],
                            "caption": str(caption_path),
                            "image_exists": image_exists,
                            "caption_exists": caption_exists,
                            "reason": (
                                "mapped output and caption exist"
                                if caption_exists
                                else "mapped output exists; caption missing"
                            ),
                        }
                    )
                    status = "caption exists" if caption_exists else "caption missing"
                    print(f"skipped {src.name}: mapped output exists; {status}")
                    continue

                result = convert_image(
                    src,
                    dst,
                    output_format=args.format,
                    webp_quality=args.webp_quality,
                    webp_lossless=args.webp_lossless,
                )
                upsert_mapping(
                    source_map,
                    key=key,
                    source_path=src,
                    source_hash=digest,
                    output_path=dst,
                    output_format=args.format,
                    output_quality=args.webp_quality if args.format == "webp" else None,
                    output_lossless=args.webp_lossless if args.format == "webp" else False,
                    width=int(result["width"]),
                    height=int(result["height"]),
                    mode=str(result["mode"]),
                )
                converted.append(result)
                print(f"converted {src.name} -> {dst.name}")
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
        "source_map": str(source_map_path),
        "output_format": args.format,
        "webp_quality": args.webp_quality if args.format == "webp" else None,
        "webp_lossless": args.webp_lossless if args.format == "webp" else None,
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

