#!/usr/bin/env python3

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--tile", type=int, default=220)
    parser.add_argument("--recursive", action="store_true", help="Search subdirectories recursively")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    pattern = "**/*.png" if args.recursive else "*.png"
    paths = sorted(input_dir.glob(pattern))
    if not paths:
        raise SystemExit("No PNG files found")
    rows = (len(paths) + args.columns - 1) // args.columns
    margin = 8
    label_height = 30
    cell_width = args.tile + margin * 2
    cell_height = args.tile + label_height + margin * 2
    sheet = Image.new("RGB", (cell_width * args.columns, cell_height * rows), "black")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=22)

    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGBA")
        image.thumbnail((args.tile, args.tile), Image.Resampling.LANCZOS)
        background = Image.new("RGBA", (args.tile, args.tile), "black")
        x = (args.tile - image.width) // 2
        y = (args.tile - image.height) // 2
        background.alpha_composite(image, (x, y))
        col = index % args.columns
        row = index // args.columns
        left = col * cell_width + margin
        top = row * cell_height + margin + label_height
        sheet.paste(background.convert("RGB"), (left, top))
        rel_name = f"{path.parent.name}/{path.stem.split('_000')[0]}" if args.recursive else path.stem
        draw.text((left, row * cell_height + margin), rel_name, fill="white", font=font)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)


if __name__ == "__main__":
    main()
