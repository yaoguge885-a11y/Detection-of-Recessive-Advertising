#!/usr/bin/env python3
"""Create local contact sheets for visual triage of unseen privacy media."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def open_preview(path: Path) -> Image.Image:
    with Image.open(path) as source:
        try:
            source.seek(0)
        except EOFError:
            pass
        return ImageOps.exif_transpose(source.convert("RGB"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Make local privacy media contact sheets")
    parser.add_argument("--prefilter", required=True)
    parser.add_argument("--media-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--columns", type=int, default=8)
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--tile", type=int, default=220)
    args = parser.parse_args()

    prefilter_path = Path(args.prefilter)
    media_root = Path(args.media_root)
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite: {output_dir}")
    output_dir.mkdir(parents=True)

    payload = json.loads(prefilter_path.read_text(encoding="utf-8-sig"))
    unique: dict[str, dict] = {}
    for row in payload.get("items", []):
        for media in row.get("media", []):
            if media.get("prefilter") != "unseen_hash_needs_local_review":
                continue
            unique.setdefault(
                str(media["sha256"]),
                {
                    "sha256": str(media["sha256"]),
                    "ref": str(media["ref"]),
                    "post_ids": [],
                },
            )["post_ids"].append(str(row["post_id"]))

    entries = sorted(unique.values(), key=lambda item: item["sha256"])
    per_sheet = args.columns * args.rows
    font = ImageFont.load_default()
    sheets = []
    for sheet_number, offset in enumerate(range(0, len(entries), per_sheet), start=1):
        batch = entries[offset : offset + per_sheet]
        canvas = Image.new(
            "RGB",
            (args.columns * args.tile, args.rows * (args.tile + 22)),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        mapping = []
        for index, entry in enumerate(batch, start=1):
            row, column = divmod(index - 1, args.columns)
            x, y = column * args.tile, row * (args.tile + 22)
            path = media_root / entry["ref"]
            error = ""
            try:
                image = open_preview(path)
                image.thumbnail((args.tile - 8, args.tile - 8), Image.Resampling.LANCZOS)
                px = x + (args.tile - image.width) // 2
                py = y + (args.tile - image.height) // 2
                canvas.paste(image, (px, py))
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                draw.rectangle((x + 4, y + 4, x + args.tile - 4, y + args.tile - 4), fill="#fee2e2")
                draw.text((x + 10, y + 10), "OPEN ERROR", fill="#991b1b", font=font)
            label = f"{index:02d}  {Path(entry['ref']).suffix.lower()}"
            draw.rectangle((x, y + args.tile, x + args.tile, y + args.tile + 22), fill="#111827")
            draw.text((x + 5, y + args.tile + 5), label, fill="white", font=font)
            mapping.append(
                {
                    "tile": index,
                    "sha256": entry["sha256"],
                    "ref": entry["ref"],
                    "post_ids": sorted(set(entry["post_ids"])),
                    "open_error": error,
                }
            )
        name = f"sheet_{sheet_number:03d}.jpg"
        canvas.save(output_dir / name, quality=88, optimize=True)
        sheets.append({"sheet": name, "items": mapping})

    index = {
        "status": "local_visual_triage_only",
        "prefilter": str(prefilter_path),
        "unique_unseen_media": len(entries),
        "sheet_count": len(sheets),
        "columns": args.columns,
        "rows": args.rows,
        "tile_pixels": args.tile,
        "sheets": sheets,
    }
    (output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"unique_media": len(entries), "sheet_count": len(sheets)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
