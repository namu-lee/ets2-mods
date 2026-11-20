import argparse
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from shutil import copytree
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pypandoc


SOURCE_DIRECTORY = Path("src")
BUILD_DIRECTORY = Path(__file__).resolve().parents[1] / "build"
DESCRIPTION_FIELD = re.compile(r'^[ \t]*description_file[ \t]*:[ \t]*"([^"\r\n]+)"[ \t]*(?:#.*)?$', re.MULTILINE)
VERSION_FIELD = re.compile(r'(^[ \t]*package_version[ \t]*:[ \t]*")([^"\r\n]+)("[ \t]*(?:#.*)?$)', re.MULTILINE)


def package_version(value):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise argparse.ArgumentTypeError("Expected a package version in X.Y.Z format.")
    return value


def run_apply_features(mod_directory, staging, *, base=None):
    script_path = (base or mod_directory) / "shared" / "apply_features.py"
    if not script_path.is_file():
        raise FileNotFoundError(script_path)
    # Release automation reads the package path from the build command's stdout.
    subprocess.run(
        [sys.executable, str(script_path), str(staging)],
        cwd=mod_directory,
        stdout=sys.stderr,
        check=True,
    )


@contextmanager
def stage_source(mod_directory, config, *, version=None):
    mod_directory = mod_directory.resolve()
    source = mod_directory / SOURCE_DIRECTORY
    if not (source / "manifest.sii").is_file():
        raise FileNotFoundError(source / "manifest.sii")
    base_mod = config.get("source_mod")
    features = config.get("features", [])
    if not isinstance(features, list):
        raise ValueError(f"Set features to a list in {mod_directory / 'mod.json'}.")
    if base_mod is None and not features and version is None:
        yield source
        return

    with TemporaryDirectory() as workspace:
        staging = Path(workspace) / SOURCE_DIRECTORY
        base = None
        if base_mod is not None:
            if (
                not isinstance(base_mod, str)
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", base_mod)
                or base_mod == mod_directory.name
            ):
                raise ValueError(f"Set source_mod to another mod directory in {mod_directory / 'mod.json'}.")
            base = (mod_directory.parent / base_mod).resolve()
            base_config = json.loads((base / "mod.json").read_text(encoding="utf-8"))
            if base_config.get("source_mod") is not None:
                raise ValueError(f"source_mod {base_mod} must provide its own source directory.")
            copytree(base / SOURCE_DIRECTORY, staging)
        copytree(source, staging, dirs_exist_ok=True)
        if features:
            run_apply_features(mod_directory, staging, base=base)
        if version is not None:
            manifest = staging / "manifest.sii"
            original = manifest.read_text(encoding="utf-8-sig")
            updated, count = VERSION_FIELD.subn(lambda match: match[1] + version + match[3], original)
            if count != 1:
                raise ValueError(f"{manifest} must declare exactly one package_version.")
            manifest.write_text(updated, encoding="utf-8", newline="\n")
        yield staging


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
    parser.add_argument("--version", type=package_version, help="Package version to write into the built manifest")
    args = parser.parse_args()

    config = json.loads((args.mod_directory / "mod.json").read_text(encoding="utf-8"))
    filename = config.get("package_filename") if isinstance(config, dict) else None
    if not isinstance(filename, str):
        parser.error(f"Set package_filename in {args.mod_directory / 'mod.json'}.")
    try:
        filename = package_filename(filename)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))
    output = BUILD_DIRECTORY / args.mod_directory.resolve().name / filename
    description = render_description(args.mod_directory / "description.md")
    with stage_source(args.mod_directory, config, version=args.version) as source:
        manifest = source / "manifest.sii"
        write_archive(source, output, generated_files={description_filename(manifest): description.encode("utf-8")})
    print(output.resolve())
