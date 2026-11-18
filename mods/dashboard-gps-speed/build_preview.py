"""Create the README's GPS contact sheet from the original ETS2 screenshots."""

import argparse
import re
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw, ImageFont


SCREENSHOTS = Path(__file__).resolve().parent / "screenshots"
PREVIEW = SCREENSHOTS / "gps-preview.png"
SCREENSHOT_SIZE = (2560, 1440)
SEARCH_ORIGIN = (1350, 695)
CROP_SIZE = (174, 100)
CARD_WIDTH, IMAGE_HEIGHT, LABEL_HEIGHT = 258, 148, 52
SPACING, COLUMNS = 12, 4

SAMPLE_ROW = re.compile(
    r"^\| ([^|]+?) \| ([^|]+?) \| [^|]+ \| [^|]+ "
    r"\| \[Original\]\(([^)]+\.png)\) \|$",
    re.MULTILINE,
)
NEIGHBORS = (
    (-1, -1), (0, -1), (1, -1), (-1, 0),
    (1, 0), (-1, 1), (0, 1), (1, 1),
)
# The route adviser starts just beyond this edge in these screenshots.
HUD_CROP_RIGHT = 2070
SAMPLES_WITH_HUD = {
    "iveco-hiway-lhd.png",
    "scania-r-lhd-2.png",
    "scania-r-2016-legacy-lhd.png",
    "scania-s-2016-legacy-lhd.png",
    "scania-s-2024e-lhd.png",
    "scania-streamline-lhd-2.png",
}


def sample_rows():
    rows = SAMPLE_ROW.findall((SCREENSHOTS / "README.md").read_text(encoding="utf-8-sig"))
    filenames = {filename for _, _, filename in rows}
    originals = {path.name for path in SCREENSHOTS.glob("*.png") if path != PREVIEW}
    if not rows or len(filenames) != len(rows):
        raise ValueError("The sample table must list each original screenshot once.")
    if filenames != originals:
        missing = ", ".join(sorted(filenames - originals)) or "none"
        unlisted = ", ".join(sorted(originals - filenames)) or "none"
        raise ValueError(f"Sample table mismatch (missing: {missing}, unlisted: {unlisted}).")
    return rows


def red_component_bounds(mask):
    rows, columns = np.nonzero(mask)
    remaining = set(zip(map(int, columns), map(int, rows)))
    while remaining:
        points = [remaining.pop()]
        for x, y in points:
            for dx, dy in NEIGHBORS:
                neighbor = (x + dx, y + dy)
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    points.append(neighbor)
        if len(points) >= 72:
            xs, ys = zip(*points)
            yield min(xs), min(ys), max(xs), max(ys)


def find_speed_limit(image, filename):
    if image.size != SCREENSHOT_SIZE:
        raise ValueError(f"{filename} must be a native 2560×1440 screenshot.")
    pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    start_x, start_y = SEARCH_ORIGIN
    red, green, blue = pixels[start_y:, start_x:].transpose(2, 0, 1)
    mask = (red > 112) & (red - green > 38) & (red - blue > 31)
    candidates = []
    for left, top, right, bottom in red_component_bounds(mask):
        left, right = left + start_x, right + start_x
        top, bottom = top + start_y, bottom + start_y
        width, height = right - left + 1, bottom - top + 1
        if left >= 2350 or not (10 <= width <= 150 and 9 <= height <= 150):
            continue
        if not 0.43 < width / height < 3:
            continue

        # Check the white sign face and dark digits inside the red ring.
        region = pixels[top:bottom + 1, left:right + 1]
        y, x = np.indices(region.shape[:2])
        center_x, center_y = (left + right) / 2, (top + bottom) / 2
        ellipse = (((x + left - center_x) / (width * .33)) ** 2
                   + ((y + top - center_y) / (height * .33)) ** 2 < 1)
        bright, dark = region.max(2), region.min(2)
        white = (dark > 133) & ((bright - dark) < 53) & ellipse
        black = (bright < 130) & ((bright - dark) < 43) & ellipse
        if white.sum() < ellipse.sum() * .34 or black.sum() < max(11, ellipse.sum() * .065):
            continue

        # The current-speed digit sits immediately below the sign.
        speed_left = int(max(left, center_x - width * .27))
        speed_right = int(min(right + 1, center_x + width * .27 + 1))
        speed_top = bottom + max(1, round(height * .10))
        speed_bottom = min(image.height, bottom + max(19, round(height * 1.16)))
        speed = pixels[speed_top:speed_bottom, speed_left:speed_right]
        white_text = (speed.min(2) > 151) & ((speed.max(2) - speed.min(2)) < 42)
        text_rows = np.flatnonzero(white_text.any(axis=1))
        runs = np.split(text_rows, np.flatnonzero(np.diff(text_rows) > 1) + 1)
        if not any(len(run) >= (4 if height < 22 else 7) for run in runs):
            continue
        score = white.sum() / ellipse.sum() + .08 * (1 - abs(height - width) / max(height, width))
        candidates.append((score, (left, top, right, bottom)))

    if not candidates:
        raise ValueError(f"No in-cab speed display found in {filename}.")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def crop_gps(image, filename):
    left, top, right, _ = find_speed_limit(image, filename)
    crop_width, crop_height = CROP_SIZE
    crop_left = max(0, min(image.width - crop_width, left - 32))
    if filename in SAMPLES_WITH_HUD and right < HUD_CROP_RIGHT:
        crop_left = min(crop_left, HUD_CROP_RIGHT - crop_width)
    crop_left = max(crop_left, right - crop_width + 1)
    crop_top = max(0, min(image.height - crop_height, top - 12))
    viewport = (crop_left, crop_top, crop_left + crop_width, crop_top + crop_height)
    return image.crop(viewport).resize((CARD_WIDTH, IMAGE_HEIGHT), Image.Resampling.LANCZOS)


def load_font(preferred, fallback, size):
    try:
        return ImageFont.truetype(preferred, size)
    except OSError:
        return ImageFont.truetype(fallback, size)


def build_preview(output):
    rows = sample_rows()
    output = output.resolve()
    if output.suffix.lower() != ".png":
        raise ValueError("The preview output must be a .png file.")
    if any(output == (SCREENSHOTS / filename).resolve() for _, _, filename in rows):
        raise ValueError("Choose a preview output separate from the original screenshots.")
    card_height = LABEL_HEIGHT + IMAGE_HEIGHT
    preview = Image.new(
        "RGB",
        (
            SPACING + COLUMNS * (CARD_WIDTH + SPACING),
            SPACING + ceil(len(rows) / COLUMNS) * (card_height + SPACING),
        ),
        "#10151d",
    )
    draw = ImageDraw.Draw(preview)
    heading_font = load_font("segoeuib.ttf", "DejaVuSans-Bold.ttf", 17)
    trim_font = load_font("segoeui.ttf", "DejaVuSans.ttf", 15)

    for index, (vehicle, trim, filename) in enumerate(rows):
        x = SPACING + index % COLUMNS * (CARD_WIDTH + SPACING)
        y = SPACING + index // COLUMNS * (card_height + SPACING)
        draw.rounded_rectangle(
            (x, y, x + CARD_WIDTH - 1, y + card_height - 1), radius=7, fill="#1b2430"
        )
        with Image.open(SCREENSHOTS / filename) as image:
            tile = crop_gps(image, filename).convert("RGB")
        preview.paste(tile, (x, y + LABEL_HEIGHT))
        draw.text((x + 10, y + 8), vehicle, font=heading_font, fill="#eef3fa")
        if trim != "—":
            draw.text((x + 10, y + 28), trim, font=trim_font, fill="#b1c3da")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as workspace:
        staged = Path(workspace) / "preview.png"
        preview.save(staged, optimize=True)
        staged.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PREVIEW, help="Generated PNG path")
    options = parser.parse_args()
    try:
        build_preview(options.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(options.output.resolve())
