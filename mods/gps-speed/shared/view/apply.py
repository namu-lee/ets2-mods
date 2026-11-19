import json
import re
from decimal import Decimal
from pathlib import Path
from shutil import copyfile


GPS_MAP_IMAGE = re.compile(rb'<img\b(?=[^>]*\ssrc=/material/ui/dashboard/bare_map\.mat(?=\s|>))[^>]*>')
VERTICAL_BOUND = re.compile(rb'\b(bottom|top)=([0-9]+(?:\.[0-9]+)?)')


def set_gps_marker_height(source, marker_height):
    def shift_crop(match):
        image = match[0]
        bounds = VERTICAL_BOUND.findall(image)
        values = {name: Decimal(value.decode("ascii")) for name, value in bounds}
        if len(bounds) != 2 or len(values) != 2:
            raise ValueError(f"Expected a top and bottom edge in {layout}.")
        height = values[b"top"] - values[b"bottom"]
        # The rendered marker is centered at v=0.5. Preserve the sampled height.
        bottom = Decimal("0.5") - height * marker_height
        top = bottom + height
        if not 0 <= bottom < top <= 1:
            raise ValueError(f"Adjusted map crop does not fit in {layout}.")
        adjusted = {b"bottom": bottom, b"top": top}
        return VERTICAL_BOUND.sub(
            lambda edge: edge[1] + b"=" + format(adjusted[edge[1]].normalize(), "f").encode("ascii"),
            image,
        )

    found_map = False
    for layout in (source / "ui").rglob("*.sii"):
        contents = layout.read_bytes()
        adjusted, count = GPS_MAP_IMAGE.subn(shift_crop, contents)
        if count:
            layout.write_bytes(adjusted)
            found_map = True
    if not found_map:
        raise ValueError(f"No dashboard GPS map images found in {source}.")


def apply_gps_view(source):
    view_directory = Path(__file__).resolve().parent
    settings_path = view_directory / "gps-view.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict) or settings.keys() != {"marker_height"}:
        raise ValueError(f"{settings_path} must specify marker_height.")
    marker_height = settings["marker_height"]
    if type(marker_height) not in (int, float) or not 0 <= marker_height <= 1:
        raise ValueError(f"{settings_path}: marker_height must be between 0 and 1.")

    map_data = source / "def" / "map_data.sii"
    map_data.parent.mkdir(parents=True, exist_ok=True)
    copyfile(view_directory / map_data.name, map_data)
    set_gps_marker_height(source, Decimal(str(marker_height)))
