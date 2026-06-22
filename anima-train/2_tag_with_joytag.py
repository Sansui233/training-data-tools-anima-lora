from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
import torch.amp.autocast_mode
import torchvision.transforms.functional as TVF
from PIL import Image

from dataset_sources import collect_caption_files, collect_training_images, find_caption_for_image
from image_naming import original_stem


def import_joytag(repo_dir: Path):
    sys.path.insert(0, str(repo_dir))
    from Models import VisionModel  # type: ignore

    return VisionModel


def prepare_image(image: Image.Image, target_size: int) -> torch.Tensor:
    image = image.convert("RGB")
    width, height = image.size
    max_dim = max(width, height)
    padded = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
    padded.paste(image, ((max_dim - width) // 2, (max_dim - height) // 2))

    if max_dim != target_size:
        padded = padded.resize((target_size, target_size), Image.LANCZOS)

    image_tensor = TVF.pil_to_tensor(padded)
    image_tensor = image_tensor / 255.0
    image_tensor = TVF.normalize(
        image_tensor,
        mean=[0.48145466, 0.4578275, 0.40821073],
        std=[0.26862954, 0.26130258, 0.27577711],
    )
    return image_tensor


@torch.no_grad()
def predict_tags(
    image_path: Path,
    model,
    top_tags: list[str],
    device: torch.device,
    threshold: float,
) -> tuple[list[str], dict[str, float]]:
    with Image.open(image_path) as image:
        image_tensor = prepare_image(image, model.image_size)

    batch = {"image": image_tensor.unsqueeze(0).to(device)}
    with torch.amp.autocast_mode.autocast(device.type, enabled=device.type == "cuda"):
        preds = model(batch)
        tag_preds = preds["tags"].sigmoid().cpu()[0]

    scores = {top_tags[i]: float(tag_preds[i]) for i in range(len(top_tags))}
    predicted_tags = [tag for tag, score in scores.items() if score > threshold]
    return predicted_tags, scores


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate JoyTag captions for training images.")
    parser.add_argument("--target-dir", type=Path, default=Path("train/anima"))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--joytag-repo", type=Path, default=Path("joytag"))
    parser.add_argument("--model-dir", type=Path, default=Path("joytag/models"))
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--trigger", default="atomsphere_style")
    parser.add_argument("--threshold", type=float, default=0.4)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_dir = args.target_dir.resolve()
    data_dir = (args.data_dir or target_dir / "data").resolve()
    joytag_repo = args.joytag_repo.resolve()
    model_dir = args.model_dir.resolve()
    report_dir = (args.report_dir or target_dir / "reports").resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device(args.device)

    images: list[tuple[Path, Path]] = []
    skipped: list[dict[str, object]] = []
    try:
        training_images = collect_training_images(data_dir)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    caption_files = collect_caption_files(data_dir)
    caption_bases = {original_stem(path) for path in caption_files}
    pending_bases: set[str] = set()

    for image_path in training_images:
        image_base = original_stem(image_path)
        existing_caption = find_caption_for_image(image_path, caption_files)
        if not args.force and (existing_caption is not None or image_base in pending_bases):
            caption_path = existing_caption or image_path.with_suffix(".txt")
            skipped.append(
                {
                    "image": str(image_path),
                    "caption": str(caption_path),
                    "image_exists": True,
                    "caption_exists": existing_caption is not None,
                    "reason": (
                        "same basename caption exists"
                        if existing_caption is not None
                        else "same basename image is already queued"
                    ),
                }
            )
            continue
        caption_path = image_path.with_suffix(".txt")
        images.append((image_path, caption_path))
        pending_bases.add(image_base)

    successes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    if images:
        VisionModel = import_joytag(joytag_repo)
        model = VisionModel.load_model(model_dir)
        model.eval()
        model.to(device)

        top_tags_path = model_dir / "top_tags.txt"
        top_tags = [
            line.strip()
            for line in top_tags_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        model = None
        top_tags = []

    for index, (image_path, caption_path) in enumerate(images, start=1):
        try:
            assert model is not None
            tags, scores = predict_tags(image_path, model, top_tags, device, args.threshold)
            caption = ", ".join([args.trigger, *tags])
            caption_path.write_text(caption + "\n", encoding="utf-8")
            caption_bases.add(original_stem(caption_path))
            successes.append(
                {
                    "image": str(image_path),
                    "caption": str(caption_path),
                    "tag_count": len(tags),
                    "top_scores": sorted(
                        scores.items(), key=lambda item: item[1], reverse=True
                    )[:20],
                }
            )
            print(f"[{index}/{len(images)}] tagged {image_path.name}: {len(tags)} tags")
        except Exception as exc:
            failures.append(
                {"image": str(image_path), "error": f"{type(exc).__name__}: {exc}"}
            )
            print(f"[{index}/{len(images)}] failed {image_path.name}: {exc}")

    write_jsonl(report_dir / "joytag_captions.jsonl", successes)
    write_jsonl(report_dir / "joytag_skipped.jsonl", skipped)
    write_jsonl(report_dir / "joytag_failures.jsonl", failures)
    summary = {
        "training_image_count": len(training_images),
        "existing_caption_base_count": len(caption_bases),
        "image_count": len(images),
        "caption_count": len(successes),
        "skipped_count": len(skipped),
        "failed_count": len(failures),
        "target_dir": str(target_dir),
        "data_dir": str(data_dir),
        "trigger": args.trigger,
        "threshold": args.threshold,
        "device": str(device),
        "model_dir": str(model_dir),
    }
    (report_dir / "joytag_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
