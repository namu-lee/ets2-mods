import argparse
import json
import os
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


SOURCE_DIRECTORY = Path("src")
BUILD_DIRECTORY = Path("build")


def package_filename(value):
    if (
        not value.lower().endswith(".scs")
        or not value[:-4].strip(" .")
        or any(character in '<>:"/\\|?*' or ord(character) < 32 for character in value)
        or PureWindowsPath(value).is_reserved()
    ):
        raise argparse.ArgumentTypeError("Expected a Windows-compatible .scs filename without a path.")
    return value


def write_archive(source, output):
    output = output.resolve()
    if output.is_relative_to(source.resolve()):
        raise ValueError("Choose an output file outside the source directory.")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as workspace:
        staged = Path(workspace) / output.name
        with ZipFile(staged, "w", ZIP_DEFLATED, compresslevel=9) as archive:
            for file in sorted(source.rglob("*")):
                if file.is_file():
                    member = ZipInfo(file.relative_to(source).as_posix())
                    archive.writestr(member, file.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
        with ZipFile(staged) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise ValueError(f"Corrupt archive member: {corrupt}")
        os.replace(staged, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build an ETS2 mod archive.")
    parser.add_argument("mod_directory", type=Path)
    args = parser.parse_args()

    source = args.mod_directory / SOURCE_DIRECTORY
    manifest = source / "manifest.sii"
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    config = json.loads((args.mod_directory / "mod.json").read_text(encoding="utf-8"))
    filename = config.get("package_filename") if isinstance(config, dict) else None
    if not isinstance(filename, str):
        parser.error(f"Set package_filename in {args.mod_directory / 'mod.json'}.")
    try:
        filename = package_filename(filename)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))
    output = args.mod_directory / BUILD_DIRECTORY / filename
    write_archive(source, output)
    print(output.resolve())
