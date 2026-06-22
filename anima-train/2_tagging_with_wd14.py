from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from dataset_sources import collect_caption_files, collect_training_images, find_caption_for_image
from image_naming import original_stem


DEFAULT_SD_SCRIPTS_DIR = Path("F:/AI/sd-scripts")
DEFAULT_REPO_ID = "SmilingWolf/wd-eva02-large-tagger-v3"
DEFAULT_TRIGGER = "atomsphere_style"
TEMP_CAPTION_EXTENSION = ".txt"
BLOCKED_TAGS = {
    "weibo_username",
    "weibo_logo",
    "original",
    "photoshop_(medium)",
    "signature",
    "sample_watermark",
    "twitter_username",
    "character_name",
    "copyright_name",
    "copyright",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate filtered WD14 captions through sd-scripts, with trigger word prepended."
    )
    parser.add_argument("--target-dir", type=Path, default=Path("train/anima"))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--sd-scripts-dir", type=Path, default=DEFAULT_SD_SCRIPTS_DIR)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--trigger", default=DEFAULT_TRIGGER)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-data-loader-n-workers", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="Keep the temporary staging directory for inspection.",
    )
    return parser.parse_args()


def split_tags(caption: str) -> list[str]:
    return [tag.strip() for tag in caption.replace("\n", " ").split(",") if tag.strip()]


def normalize_for_filter(tag: str) -> str:
    return tag.strip().lower().replace(" ", "_")


def filter_tags(tags: list[str], trigger: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    trigger_key = normalize_for_filter(trigger)

    for tag in [trigger, *tags]:
        key = normalize_for_filter(tag)
        if not key or key in seen:
            continue
        if key in BLOCKED_TAGS:
            continue
        result.append(tag)
        seen.add(key)

    if trigger_key not in seen:
        result.insert(0, trigger)
    elif normalize_for_filter(result[0]) != trigger_key:
        result = [tag for tag in result if normalize_for_filter(tag) != trigger_key]
        result.insert(0, trigger)
    return result


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def stage_image(source: Path, staging_dir: Path) -> Path:
    staged = staging_dir / source.name
    try:
        staged.symlink_to(source)
        return staged
    except OSError as symlink_exc:
        try:
            os.link(source, staged)
            return staged
        except OSError as hardlink_exc:
            raise OSError(
                "failed to stage image with symlink or hardlink; "
                f"no copy fallback is used. symlink error: {symlink_exc}; "
                f"hardlink error: {hardlink_exc}"
            ) from hardlink_exc
    return staged


def build_sd_command(
    python_exe: Path,
    wd14_script: Path,
    image_dir: Path,
    model_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    return [
        str(python_exe),
        str(wd14_script),
        "--onnx",
        "--repo_id",
        args.repo_id,
        "--model_dir",
        str(model_dir),
        "--batch_size",
        str(args.batch_size),
        "--max_data_loader_n_workers",
        str(args.max_data_loader_n_workers),
        "--caption_extension",
        TEMP_CAPTION_EXTENSION,
        "--thresh",
        str(args.threshold),
        "--undesired_tags",
        ", ".join(sorted(BLOCKED_TAGS)),
        str(image_dir),
    ]


def main() -> int:
    args = parse_args()
    target_dir = args.target_dir.resolve()
    data_dir = (args.data_dir or target_dir / "data").resolve()
    report_dir = (args.report_dir or target_dir / "reports").resolve()
    sd_scripts_dir = args.sd_scripts_dir.resolve()
    model_dir = (args.model_dir or sd_scripts_dir / "wd14_tagger_model").resolve()
    wd14_script = (sd_scripts_dir / "finetune" / "tag_images_by_wd14_tagger.py").resolve()
    python_exe = (sd_scripts_dir / ".venv" / "Scripts" / "python.exe").resolve()
    staging_dir = (report_dir / "wd14_staging").resolve()

    if not sd_scripts_dir.is_dir():
        raise SystemExit(f"sd-scripts directory does not exist: {sd_scripts_dir}")
    if not wd14_script.is_file():
        raise SystemExit(f"WD14 tagger script does not exist: {wd14_script}")
    if not python_exe.is_file():
        raise SystemExit(f"sd-scripts Python does not exist: {python_exe}")

    report_dir.mkdir(parents=True, exist_ok=True)
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    try:
        training_images = collect_training_images(data_dir)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    caption_files = collect_caption_files(data_dir)
    pending_bases: set[str] = set()
    staged_pairs: list[tuple[Path, Path, Path]] = []
    skipped: list[dict[str, object]] = []

    for image_path in training_images:
        image_base = original_stem(image_path)
        existing_caption = find_caption_for_image(image_path, caption_files)
        if not args.force and (existing_caption is not None or image_base in pending_bases):
            skipped.append(
                {
                    "image": str(image_path),
                    "caption": str(existing_caption or image_path.with_suffix(".txt")),
                    "caption_exists": existing_caption is not None,
                    "reason": (
                        "same basename caption exists"
                        if existing_caption is not None
                        else "same basename image is already queued"
                    ),
                }
            )
            continue

        staged_image = stage_image(image_path, staging_dir)
        staged_pairs.append((image_path, staged_image, image_path.with_suffix(".txt")))
        pending_bases.add(image_base)

    successes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    if staged_pairs:
        command = build_sd_command(
            python_exe=python_exe,
            wd14_script=wd14_script,
            image_dir=staging_dir,
            model_dir=model_dir,
            args=args,
        )
        print("Running WD14 tagger:")
        print(" ".join(command))
        subprocess.run(command, cwd=sd_scripts_dir, check=True)

    for image_path, staged_image, caption_path in staged_pairs:
        staged_caption = staged_image.with_suffix(TEMP_CAPTION_EXTENSION)
        try:
            if not staged_caption.is_file():
                raise FileNotFoundError(f"staged caption was not generated: {staged_caption}")
            raw_tags = split_tags(staged_caption.read_text(encoding="utf-8"))
            tags = filter_tags(raw_tags, args.trigger)
            caption_path.write_text(", ".join(tags) + "\n", encoding="utf-8")
            successes.append(
                {
                    "image": str(image_path),
                    "caption": str(caption_path),
                    "raw_tag_count": len(raw_tags),
                    "tag_count": len(tags),
                }
            )
        except Exception as exc:
            failures.append(
                {"image": str(image_path), "error": f"{type(exc).__name__}: {exc}"}
            )

    write_jsonl(report_dir / "wd14_captions.jsonl", successes)
    write_jsonl(report_dir / "wd14_skipped.jsonl", skipped)
    write_jsonl(report_dir / "wd14_failures.jsonl", failures)

    summary = {
        "training_image_count": len(training_images),
        "image_count": len(staged_pairs),
        "caption_count": len(successes),
        "skipped_count": len(skipped),
        "failed_count": len(failures),
        "target_dir": str(target_dir),
        "data_dir": str(data_dir),
        "sd_scripts_dir": str(sd_scripts_dir),
        "model_dir": str(model_dir),
        "repo_id": args.repo_id,
        "trigger": args.trigger,
        "threshold": args.threshold,
    }
    (report_dir / "wd14_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.keep_staging:
        shutil.rmtree(staging_dir, ignore_errors=True)

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
