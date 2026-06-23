# Tag Priority Reference

The sorter uses semantic heuristics rather than a closed tag dictionary. Maintain the classifier by adding exact tags, suffixes, prefixes, or keyword fragments to the relevant group in `scripts/sort_tags.py`.

Tag parsing splits on English comma, Chinese comma, and newline. It does not preserve escaped commas or commas inside parentheses as part of one tag unless that support is added later.

Priority order:

1. Trigger words are removed from all segments and written first.
2. Subject/composition tags identify people count and camera framing.
3. Hair/head tags include hair color/length/style, bangs, hair ornament, hat, hood, horns, crown, and headwear.
4. Face tags include eyes, mouth, expression, blush, ears, nose, teeth, tongue, tears, and makeup.
5. Action tags include pose, movement, holding, sitting, standing, looking, hand, arm, leg, and body posture.
6. Clothing/accessory tags include garments, footwear, gloves, jewelry, bows, ribbons, belts, bags, armor, and wearable decorations.
7. Object/entity tags include props, weapons, flowers, animals, food, instruments, books, phones, vehicles, and other concrete things.
8. Scene tags include background, rooms, architecture, landscape, water, sky, weather, and time.
9. Lighting/color tags include light, shadow, glow, palette, monochrome, colorful, gradient, and visual effects.
10. Copyright/source tags include copyright, series, character/source names when recognizable, artist, watermark, signature, logo, and visible text.
11. Unknown tags remain last but are preserved.

For multi-subject captions, a later subject-count tag starts a new segment. This handles captions such as:

```text
atomsphere_style, 1boy, white_hair, blue_eyes, heart, multiple_boys, black_hair, red_eyes
```

The first segment centers on `1boy`; the second centers on `multiple_boys`. Each segment is sorted independently.
