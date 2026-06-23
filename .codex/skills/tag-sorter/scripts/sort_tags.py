#!/usr/bin/env python3
"""Sort comma-separated dataset caption tags with backups and validation."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path


SUBJECT_RE = re.compile(r"^(?:[1-9]\d*(?:girls?|boys?)|multiple_(?:girls|boys))$")
DEFAULT_TRIGGERS = {"atomsphere_style"}


EXACT_GROUPS: dict[str, int] = {
    # subject and composition
    "solo": 10,
    "duo": 10,
    "group": 10,
    "male_focus": 10,
    "female_focus": 10,
    "portrait": 10,
    "cowboy_shot": 10,
    "upper_body": 10,
    "lower_body": 10,
    "full_body": 10,
    "close-up": 10,
    "wide_shot": 10,
    "profile": 10,
    "from_side": 10,
    "from_behind": 10,
    "from_above": 10,
    "from_below": 10,
    "pov": 10,
    # face
    "looking_at_viewer": 30,
    "looking_to_the_side": 30,
    "looking_back": 30,
    "closed_mouth": 30,
    "open_mouth": 30,
    "smile": 30,
    "frown": 30,
    "parted_lips": 30,
    "blush": 30,
    # actions and pose
    "standing": 40,
    "sitting": 40,
    "kneeling": 40,
    "lying": 40,
    "walking": 40,
    "running": 40,
    "jumping": 40,
    "holding": 40,
    "reaching": 40,
    "waving": 40,
    "hands_up": 40,
    "arms_up": 40,
    "arms_crossed": 40,
    "hand_on_hip": 40,
}


GROUP_RULES: list[tuple[int, tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = [
    (
        20,
        (
            "hair",
            "bangs",
            "ahoge",
            "braid",
            "twintails",
            "ponytail",
            "sidelocks",
            "hair_ornament",
            "hairclip",
            "hairband",
            "hair_bow",
            "hat",
            "cap",
            "hood",
            "crown",
            "horns",
            "headwear",
            "headdress",
        ),
        ("hair_",),
        ("_hair", "_bangs", "_hat", "_cap", "_hood", "_horns"),
    ),
    (
        30,
        (
            "eye",
            "eyes",
            "mouth",
            "face",
            "expression",
            "smile",
            "teeth",
            "tongue",
            "nose",
            "ear",
            "ears",
            "eyebrow",
            "eyelash",
            "blush",
            "tears",
            "makeup",
            "lipstick",
        ),
        ("eye_", "mouth_"),
        ("_eyes", "_eye", "_mouth", "_face", "_ears", "_ear", "_smile"),
    ),
    (
        40,
        (
            "pose",
            "sitting",
            "standing",
            "kneeling",
            "lying",
            "walking",
            "running",
            "jumping",
            "holding",
            "looking",
            "gaze",
            "hand",
            "hands",
            "arm",
            "arms",
            "leg",
            "legs",
            "feet",
            "finger",
            "fingers",
            "leaning",
            "spread",
            "crossed",
            "raised",
        ),
        ("hand_", "arm_", "leg_", "looking_"),
        ("_pose", "_hand", "_hands", "_arm", "_arms", "_leg", "_legs"),
    ),
    (
        50,
        (
            "dress",
            "shirt",
            "skirt",
            "pants",
            "shorts",
            "jacket",
            "coat",
            "sweater",
            "hoodie",
            "uniform",
            "kimono",
            "robe",
            "sleeves",
            "gloves",
            "boots",
            "shoes",
            "socks",
            "thighhighs",
            "belt",
            "collar",
            "necktie",
            "bow",
            "ribbon",
            "jewelry",
            "earrings",
            "necklace",
            "bracelet",
            "ring",
            "armor",
            "bag",
            "cape",
            "scarf",
        ),
        ("dress_", "shirt_", "skirt_", "pants_", "jacket_", "coat_"),
        (
            "_dress",
            "_shirt",
            "_skirt",
            "_pants",
            "_shorts",
            "_jacket",
            "_coat",
            "_sleeves",
            "_gloves",
            "_boots",
            "_shoes",
            "_socks",
            "_bow",
            "_ribbon",
        ),
    ),
    (
        60,
        (
            "weapon",
            "sword",
            "gun",
            "knife",
            "staff",
            "book",
            "phone",
            "umbrella",
            "flower",
            "rose",
            "plant",
            "animal",
            "cat",
            "dog",
            "bird",
            "food",
            "cup",
            "glass",
            "vehicle",
            "car",
            "bike",
            "instrument",
            "heart",
            "star",
        ),
        ("holding_",),
        ("_weapon", "_sword", "_gun", "_flower", "_animal"),
    ),
    (
        70,
        (
            "background",
            "indoors",
            "outdoors",
            "room",
            "bedroom",
            "street",
            "city",
            "building",
            "window",
            "door",
            "wall",
            "floor",
            "sky",
            "cloud",
            "water",
            "sea",
            "ocean",
            "river",
            "forest",
            "tree",
            "grass",
            "snow",
            "rain",
            "night",
            "day",
            "sunset",
            "landscape",
        ),
        ("background_",),
        ("_background", "_room", "_sky", "_clouds"),
    ),
    (
        80,
        (
            "light",
            "lighting",
            "shadow",
            "glow",
            "color",
            "colour",
            "palette",
            "monochrome",
            "greyscale",
            "gradient",
            "sparkle",
            "shiny",
            "transparent",
            "silhouette",
            "backlighting",
            "rim_light",
        ),
        ("light_", "color_"),
        ("_light", "_lighting", "_shadow", "_glow", "_theme"),
    ),
    (
        90,
        (
            "copyright",
            "series",
            "character",
            "artist",
            "watermark",
            "signature",
            "logo",
            "text",
            "username",
            "commentary",
        ),
        ("copyright_", "artist_"),
        ("_copyright", "_watermark", "_signature", "_logo"),
    ),
]


COLOR_WORDS = {
    "black",
    "blue",
    "brown",
    "green",
    "grey",
    "gray",
    "orange",
    "pink",
    "purple",
    "red",
    "white",
    "yellow",
    "gold",
    "silver",
    "blonde",
    "aqua",
    "multicolored",
}


def parse_tags(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，\n]+", text) if part.strip()]


def is_subject(tag: str) -> bool:
    return bool(SUBJECT_RE.match(tag))


def priority(tag: str, index: int) -> tuple[int, int, str]:
    norm = tag.lower()
    tokens = set(norm.split("_"))
    if is_subject(norm):
        return (10, index, norm)
    if norm in EXACT_GROUPS:
        return (EXACT_GROUPS[norm], index, norm)
    for group, contains, prefixes, suffixes in GROUP_RULES:
        if (
            any(word in tokens for word in contains)
            or any(norm.startswith(prefix) for prefix in prefixes)
            or any(norm.endswith(suffix) for suffix in suffixes)
        ):
            return (group, index, norm)
    if any(word in tokens for word in COLOR_WORDS):
        return (80, index, norm)
    return (100, index, norm)


def split_segments(tags: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for tag in tags:
        if is_subject(tag.lower()):
            current_has_subject = any(is_subject(item.lower()) for item in current)
            if current_has_subject:
                segments.append(current)
                current = [tag]
            elif current:
                current = [tag, *current]
            else:
                current = [tag]
        else:
            current.append(tag)
    if current:
        segments.append(current)
    return segments


def sort_tags(tags: list[str], triggers: set[str]) -> list[str]:
    trigger_tags: list[str] = []
    remaining: list[str] = []
    for tag in tags:
        if tag.lower() in triggers:
            trigger_tags.append(tag)
        else:
            remaining.append(tag)

    sorted_tags = trigger_tags
    for segment in split_segments(remaining):
        indexed = list(enumerate(segment))
        sorted_tags.extend(tag for _, tag in sorted(indexed, key=lambda item: priority(item[1], item[0])))
    return sorted_tags


def backup_files(files: list[Path], source_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = source_dir.parent / "backup" / f"{source_dir.name}_tag_sort_backup_{timestamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    for path in files:
        shutil.copy2(path, backup_root / path.name)
    return backup_root


def process_file(path: Path, triggers: set[str], write: bool) -> dict[str, object]:
    before_text = path.read_text(encoding="utf-8", errors="replace")
    before_tags = parse_tags(before_text)
    after_tags = sort_tags(before_tags, triggers)
    valid = Counter(before_tags) == Counter(after_tags)
    if not valid:
        raise RuntimeError(f"validation failed for {path}")
    after_text = ", ".join(after_tags)
    changed = after_text != ", ".join(before_tags)
    if write and changed:
        path.write_text(after_text + "\n", encoding="utf-8")
    return {
        "file": str(path),
        "tag_count": len(before_tags),
        "unique_tag_count": len(set(before_tags)),
        "changed": changed,
        "valid": valid,
    }


def collect_stats(files: list[Path]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for path in files:
        counter.update(parse_tags(path.read_text(encoding="utf-8", errors="replace")))
    return counter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("txt_dir", type=Path, help="Directory containing caption .txt files")
    parser.add_argument("--trigger", action="append", default=[], help="Additional trigger tag to force first")
    parser.add_argument("--analyze-only", action="store_true", help="Only print tag statistics; do not backup or write")
    parser.add_argument("--dry-run", action="store_true", help="Sort and validate without writing")
    args = parser.parse_args()

    txt_dir = args.txt_dir.resolve()
    if not txt_dir.is_dir():
        raise SystemExit(f"not a directory: {txt_dir}")

    files = sorted(txt_dir.glob("*.txt"))
    if not files:
        raise SystemExit(f"no .txt files found in: {txt_dir}")

    stats = collect_stats(files)
    triggers = {tag.lower() for tag in DEFAULT_TRIGGERS}
    triggers.update(tag.lower() for tag in args.trigger)

    if args.analyze_only:
        print(json.dumps({
            "directory": str(txt_dir),
            "file_count": len(files),
            "unique_tag_count": len(stats),
            "total_tag_count": sum(stats.values()),
            "top_tags": stats.most_common(50),
        }, ensure_ascii=False, indent=2))
        return 0

    backup_dir = None if args.dry_run else backup_files(files, txt_dir)
    results = [process_file(path, triggers, write=not args.dry_run) for path in files]
    changed = sum(1 for item in results if item["changed"])
    print(json.dumps({
        "directory": str(txt_dir),
        "file_count": len(files),
        "changed_file_count": changed,
        "unchanged_file_count": len(files) - changed,
        "unique_tag_count": len(stats),
        "total_tag_count": sum(stats.values()),
        "backup_dir": None if backup_dir is None else str(backup_dir),
        "dry_run": args.dry_run,
        "validated": all(item["valid"] for item in results),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
