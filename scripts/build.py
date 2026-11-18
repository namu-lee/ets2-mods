import argparse
import json
import os
import re
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pypandoc


SOURCE_DIRECTORY = Path("src")
BUILD_DIRECTORY = Path("build")
DESCRIPTION_FIELD = re.compile(r'^[ \t]*description_file[ \t]*:[ \t]*"([^"\r\n]+)"[ \t]*(?:#.*)?$', re.MULTILINE)


def description_filename(manifest):
    values = DESCRIPTION_FIELD.findall(manifest.read_text(encoding="utf-8-sig"))
    if len(values) == 1:
        path = PureWindowsPath(values[0])
        if path.name == values[0] and path.suffix.lower() == ".txt":
            return path.name
    raise ValueError(f"{manifest} must name one .txt description beside the manifest.")


def render_description(source, *, to="plain"):
    text = source.read_text(encoding="utf-8-sig")
    if not text.strip() or "\0" in text:
        raise ValueError(f"{source} must contain a nonempty text description.")

    # Use the pinned wheel's Pandoc even if a newer executable is on PATH.
    executable = "pandoc.exe" if os.name == "nt" else "pandoc"
    bundled_pandoc = Path(pypandoc.__file__).parent / "files" / executable
    os.environ.setdefault("PYPANDOC_PANDOC", str(bundled_pandoc))
    description = pypandoc.convert_text(
        text,
        to,
        format="gfm+hard_line_breaks",
        extra_args=["--wrap=none", "--eol=lf"],
    )
    if not description.strip():
        raise ValueError(f"{source} produced an empty {to} description.")
    return description


def package_filename(value):
    if (
        not value.lower().endswith(".scs")
        or not value[:-4].strip(" .")
        or any(character in '<>:"/\\|?*' or ord(character) < 32 for character in value)
        or PureWindowsPath(value).is_reserved()
    ):
        raise argparse.ArgumentTypeError("Expected a Windows-compatible .scs filename without a path.")
    return value


def write_archive(source, output, *, generated_files):
    output = output.resolve()
    if output.is_relative_to(source.resolve()):
        raise ValueError("Choose an output file outside the source directory.")

    source_files = {file.relative_to(source).as_posix(): file for file in source.rglob("*") if file.is_file()}
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as workspace:
        staged = Path(workspace) / output.name
        with ZipFile(staged, "w", ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(source_files.keys() | generated_files.keys()):
                contents = generated_files[name] if name in generated_files else source_files[name].read_bytes()
                archive.writestr(ZipInfo(name), contents, compress_type=ZIP_DEFLATED, compresslevel=9)
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
    description = render_description(args.mod_directory / "description.md")
    write_archive(source, output, generated_files={description_filename(manifest): description.encode("utf-8")})
    print(output.resolve())
