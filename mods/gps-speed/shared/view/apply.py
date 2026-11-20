import json
import re
from decimal import Decimal
from pathlib import Path
from shutil import copyfile


GPS_MAP_IMAGE = re.compile(rb'<img\b(?=[^>]*\ssrc=/material/ui/dashboard/bare_map\.mat(?=\s|>))[^>]*>')
VERTICAL_BOUND = re.compile(rb'\b(bottom|top)=([0-9]+(?:\.[0-9]+)?)')


def stage_layout_variants(source, variants, visible_map_ranges):
    for variant in variants:
        layout = source / "ui" / variant["layout"]
        variant_layout = layout.with_stem(f"{layout.stem}_{variant['suffix']}")
        copyfile(layout, variant_layout)
        visible_map_ranges[variant_layout.relative_to(source / "ui").as_posix()] = variant["visible_range"]
        original_path = f'"/{layout.relative_to(source).as_posix()}"'.encode()
        variant_path = f'"/{variant_layout.relative_to(source).as_posix()}"'.encode()

        for pattern in variant["interiors"]:
            interiors = sorted(source.glob(pattern))
            if not interiors:
                raise ValueError(f"No interior matched {pattern} for {variant_layout.name}.")
            for interior in interiors:
                contents = interior.read_bytes()
                if contents.count(original_path) != 1:
                    raise ValueError(f"Expected one reference to {layout.name} in {interior}.")
                interior.write_bytes(contents.replace(original_path, variant_path))


def set_gps_marker_height(source, marker_height, visible_map_ranges):
    def shift_crop(match):
        image = match[0]
        bounds = VERTICAL_BOUND.findall(image)
        values = {name: Decimal(value.decode("ascii")) for name, value in bounds}
        if len(bounds) != 2 or len(values) != 2:
            raise ValueError(f"Expected a top and bottom edge in {layout}.")
        height = values[b"top"] - values[b"bottom"]
        # The rendered marker is centered at v=0.5. Preserve the sampled height.
        bottom = Decimal("0.5") - height * texture_marker_height
        top = bottom + height
        if not 0 <= bottom < top <= 1:
            raise ValueError(f"Adjusted map crop does not fit in {layout}.")
        adjusted = {b"bottom": bottom, b"top": top}
        return VERTICAL_BOUND.sub(
            lambda edge: edge[1] + b"=" + format(adjusted[edge[1]].normalize(), "f").encode("ascii"),
            image,
        )

    found_map = False
    ui_directory = source / "ui"
    unused_ranges = set(visible_map_ranges)
    for layout in ui_directory.rglob("*.sii"):
        relative_path = layout.relative_to(ui_directory).as_posix()
        visible_bottom, visible_top = visible_map_ranges.get(relative_path, (0, 1))
        if not 0 <= visible_bottom < visible_top <= 1:
            raise ValueError(f"Invalid visible map range for {relative_path}.")
        # Some dashboard models display only a vertical band of the GPS UI texture.
        texture_marker_height = visible_bottom + marker_height * (visible_top - visible_bottom)
        contents = layout.read_bytes()
        adjusted, count = GPS_MAP_IMAGE.subn(shift_crop, contents)
        if count:
            layout.write_bytes(adjusted)
            found_map = True
            unused_ranges.discard(relative_path)
    if not found_map:
        raise ValueError(f"No dashboard GPS map images found in {source}.")
    if unused_ranges:
        raise ValueError(f"Missing GPS map images for {', '.join(sorted(unused_ranges))}.")


def apply_gps_view(source):
    view_directory = Path(__file__).resolve().parent
    settings_path = view_directory / "gps-view.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"), parse_float=Decimal)
    marker_height = settings["marker_height"]
    if type(marker_height) not in (int, Decimal) or not 0 <= marker_height <= 1:
        raise ValueError(f"{settings_path}: marker_height must be between 0 and 1.")
    visible_map_ranges = settings["visible_map_ranges"]
    stage_layout_variants(source, settings["layout_variants"], visible_map_ranges)

    map_data = source / "def" / "map_data.sii"
    map_data.parent.mkdir(parents=True, exist_ok=True)
    copyfile(view_directory / map_data.name, map_data)
    set_gps_marker_height(source, marker_height, visible_map_ranges)
