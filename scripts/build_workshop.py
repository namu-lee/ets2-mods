import argparse
from io import BytesIO
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps

from build import BUILD_DIRECTORY, SOURCE_DIRECTORY, write_archive


ICON = "mod_icon.jpg"
VERSIONS = """SiiNunit
{
    package_version_info : .universal
    {
        package_name: "universal"
    }
}
"""


def workshop_manifest(source):
    manifest = (source / "manifest.sii").read_text(encoding="utf-8-sig")
    lines = []
    description = ""
    for line in manifest.splitlines():
        field, _, value = line.partition(":")
        field = field.partition("[")[0].strip()
        if field in {"display_name", "icon", "compatible_versions"}:
            continue
        lines.append(line)
        if field == "description_file":
            description = value.strip().strip('"')
            lines.append(f'    icon: "{ICON}"')
    description_path = Path(description)
    if (
        description_path.name != description
        or description_path.suffix.lower() != ".txt"
        or not (source / description).is_file()
    ):
        raise ValueError("The source manifest must reference a .txt description beside the manifest.")
    return "\n".join(lines) + "\n"


def build_mod_icon(icon_path):
    with Image.open(icon_path) as source:
        preview = source.convert("RGB")
    icon = ImageOps.pad(
        preview,
        (276, 162),
        method=Image.Resampling.LANCZOS,
        color=preview.getpixel((0, 0)),
    )
    with BytesIO() as data:
        icon.save(data, format="JPEG", quality=95, subsampling=0)
        return data.getvalue()


def build_workshop(source, icon_path, output):
    if output.resolve().is_relative_to(source.resolve()):
        raise ValueError("Choose an output file outside the source directory.")

    manifest = workshop_manifest(source)
    icon = build_mod_icon(icon_path)

    with TemporaryDirectory() as workspace:
        staging = Path(workspace)
        workshop = staging / "workshop"
        content = workshop / "universal"
        copytree(source, content)
        (content / "manifest.sii").write_text(manifest, encoding="utf-8", newline="\n")
        (content / ICON).write_bytes(icon)
        (workshop / "versions.sii").write_text(VERSIONS, encoding="utf-8", newline="\n")
        write_archive(staging, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build an ETS2 Steam Workshop upload package.")
    parser.add_argument("mod_directory", type=Path)
    args = parser.parse_args()

    icon = args.mod_directory / "icon.jpg"
    if not icon.is_file():
        parser.error(f"Add the Workshop preview image at {icon}.")
    output = args.mod_directory / BUILD_DIRECTORY / "workshop-package.zip"
    build_workshop(args.mod_directory / SOURCE_DIRECTORY, icon, output)
    print(output.resolve())
