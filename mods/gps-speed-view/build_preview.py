"""Create the Workshop preview from full dashboard GPS crops."""

import argparse
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont, ImageOps


MOD_DIRECTORY = Path(__file__).resolve().parent
SCREENSHOTS = MOD_DIRECTORY / "screenshots"
PREVIEW = MOD_DIRECTORY / "preview.jpg"
PREVIEW_SIZE = (1920, 1080)
PREVIEW_BYTE_LIMIT = 1_000_000
BACKGROUND = "#10151d"
SCREENSHOT_SIZE = (2560, 1440)
CARD_WIDTH, IMAGE_HEIGHT, LABEL_HEIGHT = 258, 148, 52
SPACING, COLUMNS = 12, 7

# Filename, vehicle, trim, and the bounds (left, top, right, bottom) of its GPS display.
GPS_CAPTURES = (
    ("volvo-fh-2024.png", "Volvo FH 2024", "", (1420, 472, 1900, 798)),
    ("daf-xd.png", "DAF XD", "", (1465, 565, 1935, 842)),
    ("daf-xf.png", "DAF XF 105", "", (1405, 650, 1735, 886)),
    ("daf-xf-electric.png", "DAF XF Electric", "", (1465, 565, 1935, 842)),
    ("daf-xf-euro6.png", "DAF XF Euro 6", "", (1570, 660, 1850, 887)),
    ("daf-2021.png", "DAF XG+ 2021", "", (1465, 565, 1935, 842)),
    ("iveco-sway.png", "Iveco S-Way", "", (1625, 565, 2150, 886)),
    ("iveco-stralis.png", "Iveco Stralis", "", (1785, 310, 2125, 505)),
    ("iveco-hiway.png", "Iveco Stralis Hi-Way", "", (1775, 462, 2145, 699)),
    ("man-lions-24.png", "MAN Lion's Coach", "", (1470, 536, 1740, 715)),
    ("man-tgx.png", "MAN TGX", "", (1443, 764, 1733, 926)),
    ("man-tgx-2020.png", "MAN TGX 2020", "", (1410, 493, 1745, 695)),
    ("man-tgx-euro6-standard-xxl.png", "MAN TGX Euro 6", "Early XXL", (1340, 550, 1710, 760)),
    ("man-tgx-euro6.png", "MAN TGX Euro 6", "Later XXL", (1385, 556, 1655, 733)),
    ("mercedes-actros2014.png", "Mercedes-Benz New Actros", "", (1525, 456, 1870, 672)),
    ("renault-etech-t.png", "Renault E-Tech T", "", (1395, 468, 1860, 776)),
    ("renault-t.png", "Renault T", "2024 GPS", (1394, 510, 1845, 816)),
    ("renault-t-2013.png", "Renault T", "2013", (1485, 610, 1865, 880)),
    ("renault-t-2019.png", "Renault T", "2019", (1470, 607, 1865, 888)),
    ("renault-t-evolution.png", "Renault T", "Evolution", (1490, 610, 1890, 887)),
    ("scania-r.png", "Scania R 2009", "", (1640, 627, 2005, 864)),
    ("scania-r-2016-legacy.png", "Scania R 2016", "Legacy GPS", (1555, 500, 2025, 755)),
    ("scania-r-2016-smartdash-10.png", "Scania R 2016", "Smart Dash 10.1″", (1548, 493, 2043, 826)),
    ("scania-r-2016.png", "Scania R 2016", "Smart Dash 12.9″", (1550, 476, 2240, 868)),
    ("scania-s-2016.png", "Scania S 2016", "Smart Dash 12.9″", (1550, 476, 2240, 868)),
    ("scania-s-2024e.png", "Scania S Electric", "", (1565, 520, 2010, 742)),
    ("scania-streamline.png", "Scania Streamline", "", (1625, 627, 2030, 856)),
    ("scania-touring-23.png", "Scania Touring", "", (1510, 635, 1870, 858)),
    ("volvo-9700-23.png", "Volvo 9700", "", (1431, 611, 1712, 790)),
    ("volvo-9700-23-mph.png", "Volvo 9700", "mph", (1431, 611, 1712, 790)),
    ("volvo-fh16.png", "Volvo FH 2009", "", (1440, 207, 1820, 452)),
    ("volvo-fh16-2012.png", "Volvo FH 2012", "", (1365, 410, 1617, 565)),
    ("volvo-fh-2021.png", "Volvo FH 2021", "", (1405, 471, 1890, 811)),
)

# This preset has an empty GPS mount in the captured interior.
CAPTURES_WITHOUT_GPS = {"renault-t-legacy.png"}


def crop_gps(image, filename, bounds):
    if image.size != SCREENSHOT_SIZE:
        raise ValueError(f"{filename} must be {SCREENSHOT_SIZE[0]}×{SCREENSHOT_SIZE[1]} pixels.")
    left, top, right, bottom = bounds
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError(f"The GPS crop for {filename} is outside the screenshot.")

    # Expand the crop to fill the card while keeping the entire GPS display in view.
    scale = max((right - left) / CARD_WIDTH, (bottom - top) / IMAGE_HEIGHT)
    width, height = CARD_WIDTH * scale, IMAGE_HEIGHT * scale
    crop_left = max(0, min(image.width - width, (left + right - width) / 2))
    crop_top = max(0, min(image.height - height, (top + bottom - height) / 2))
    return image.resize(
        (CARD_WIDTH, IMAGE_HEIGHT), Image.Resampling.LANCZOS,
        box=(crop_left, crop_top, crop_left + width, crop_top + height),
    )


def load_font(preferred, fallback, size):
    try:
        return ImageFont.truetype(preferred, size)
    except OSError:
        return ImageFont.truetype(fallback, size)


def build_preview(output):
    output = output.resolve()
    if output.suffix.lower() not in {".jpg", ".jpeg"}:
        raise ValueError("The preview output must be a JPEG file.")
    filenames = {filename for filename, _, _, _ in GPS_CAPTURES}
    originals = {path.name for path in SCREENSHOTS.glob("*.png")}
    if len(filenames) != len(GPS_CAPTURES) or filenames & CAPTURES_WITHOUT_GPS:
        raise ValueError("Each GPS screenshot must have exactly one crop.")
    missing = filenames - originals
    unlisted = originals - filenames - CAPTURES_WITHOUT_GPS
    if missing or unlisted:
        raise ValueError(f"Screenshot mismatch (missing: {sorted(missing)}, unlisted: {sorted(unlisted)}).")

    card_height = LABEL_HEIGHT + IMAGE_HEIGHT
    column_stride = CARD_WIDTH + SPACING
    preview = Image.new(
        "RGB",
        (
            SPACING + COLUMNS * column_stride,
            SPACING + ceil(len(GPS_CAPTURES) / COLUMNS) * (card_height + SPACING),
        ),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(preview)
    heading_font = load_font("segoeuib.ttf", "DejaVuSans-Bold.ttf", 17)
    trim_font = load_font("segoeui.ttf", "DejaVuSans.ttf", 15)

    for index, (filename, vehicle, trim, bounds) in enumerate(GPS_CAPTURES):
        row, column = divmod(index, COLUMNS)
        cards_in_row = min(COLUMNS, len(GPS_CAPTURES) - row * COLUMNS)
        row_offset = (COLUMNS - cards_in_row) * column_stride // 2
        x = SPACING + row_offset + column * column_stride
        y = SPACING + row * (card_height + SPACING)
        draw.rounded_rectangle(
            (x, y, x + CARD_WIDTH - 1, y + card_height - 1), radius=7, fill="#1b2430"
        )
        with Image.open(SCREENSHOTS / filename) as image:
            tile = crop_gps(image, filename, bounds).convert("RGB")
        preview.paste(tile, (x, y + LABEL_HEIGHT))
        draw.text((x + 10, y + 8), vehicle, font=heading_font, fill="#eef3fa")
        if trim:
            draw.text((x + 10, y + 28), trim, font=trim_font, fill="#b1c3da")

    preview = ImageOps.pad(preview, PREVIEW_SIZE, Image.Resampling.LANCZOS, color=BACKGROUND)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as workspace:
        staged = Path(workspace) / "preview.jpg"
        for quality in range(95, 49, -5):
            preview.save(staged, quality=quality, optimize=True)
            if staged.stat().st_size < PREVIEW_BYTE_LIMIT:
                staged.replace(output)
                return
    raise ValueError("The preview could not be compressed to under 1 MB.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PREVIEW, help="Generated JPEG path")
    options = parser.parse_args()
    try:
        build_preview(options.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(options.output.resolve())
