---
name: tag-sorter
description: Sort comma-separated image caption tags in .txt dataset directories using semantic priority rules, multi-subject segmentation, backups, and validation. Use when Codex needs to reorder Danbooru/LoRA-style caption tags in one or more txt files or a txt directory while preserving every original tag exactly once per occurrence.
---

# Tag Sorter

## Workflow

Use `scripts/sort_tags.py` for deterministic file handling, backup, sorting, and validation.

1. Inspect the target directory and confirm it contains `.txt` caption files.
2. Run an analysis first when the user asks whether the rules cover the dataset:

```bash
python <skill>/scripts/sort_tags.py <txt-dir> --analyze-only
```

3. Sort in place when requested:

```bash
python <skill>/scripts/sort_tags.py <txt-dir>
```

4. Report the changed file count, unchanged file count, backup directory, and validation status.

## Sorting Model

Keep tag text unchanged. Split captions on English commas, Chinese commas, or newlines, trim surrounding whitespace, discard empty tokens, and write tags back as `tag, tag, tag`. Do not treat escaped commas or commas inside parentheses as special syntax unless the dataset actually contains them and the user asks for that support.

Global trigger words come first. Default trigger is `atomsphere_style`; pass additional triggers with repeated `--trigger <tag>`.

For the remaining tags, build subject-centered segments:

- Subject tags are `1girl`, `1boy`, `<num>girls`, `<num>boys`, `multiple_girls`, and `multiple_boys`.
- The first subject tag starts the first subject segment.
- Each later subject tag starts a new segment, so multi-person captions retain subject grouping.
- Sort each segment independently, then concatenate the sorted segments.
- Keep any pre-subject tags as their own segment after triggers.

Within each segment, sort by these priority groups:

1. Subject and camera composition: subject-count tags, `solo`, `male_focus`, `portrait`, `cowboy_shot`, `upper_body`, `full_body`, etc.
2. Hair, bangs, headwear, and hair ornaments.
3. Face and facial features, including eyes, mouth, expression, ears, nose, teeth, tongue, blush.
4. Actions, pose, hand/arm/leg posture, gaze direction, and body state.
5. Clothes, accessories, jewelry, armor, bags, and wearable decorations.
6. Objects, props, animals, plants, food, weapons, vehicles, and other non-scene entities.
7. Scene, environment, background, weather, location, and time-of-day tags.
8. Lighting, color, palette, tone, and visual effects.
9. Copyright, series, character/source, artist, watermark, signature, logo, and text.
10. Unknown or unclassified tags.

Within the same priority group, sort by normalized tag text, then original index. This keeps exact duplicate tags adjacent if they exist before deduplication.

See `references/tag-priority.md` for classifier details and maintenance notes.

## Safety

Before writing, the script copies every target `.txt` file to a backup directory beside the input folder:

```text
<txt-dir-parent>/backup/<txt-dir-name>_tag_sort_backup_<timestamp>/
```

After sorting each file, the script validates that the before/after tag multiset is identical. Treat any validation failure as a blocking error and do not claim the dataset was sorted successfully.
