"""Schedule releases for opted-in variants whose packaged files changed."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from build import VERSION_FIELD


MOD_NAME = r"[a-z0-9]+(?:-[a-z0-9]+)*"
VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"
COMPARED_DIRECTORIES = ("def/", "ui/", "material/")
SOURCE_TAG_FIELD = "Source-Release"


def run(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, text=True, encoding="utf-8").stdout.strip()


def version_tuple(value):
    if not re.fullmatch(VERSION, value):
        raise ValueError(f"Invalid release version: {value}")
    return tuple(map(int, value.split(".")))


def release_tags(mod, names):
    pattern = re.compile(rf"{mod}/v({VERSION})")
    return {name: version_tuple(match[1]) for name in names if (match := pattern.fullmatch(name))}


def tag_message(tag):
    ref = f"refs/tags/{tag}"
    kind, message, signature = run(
        "git", "for-each-ref", "--format=%(objecttype)%00%(contents)%00%(contents:signature)", ref,
    ).split("\0")
    return message.rstrip().removesuffix(signature.rstrip()).rstrip() if kind == "tag" else ""


def packaged_files(package):
    with ZipFile(package) as archive:
        files = [
            item for item in archive.infolist()
            if not item.is_dir() and item.filename.startswith(COMPARED_DIRECTORIES)
        ]
        contents = {item.filename: archive.read(item) for item in files}
    if not contents or len(files) != len(contents):
        raise ValueError(f"{package} must contain files in def/, ui/, or material/ with unique paths.")
    return contents


def next_variant_version(source, base_versions, current_version):
    previous = max((version for version in base_versions if version < source), default=None)
    index = 2
    if previous is not None:
        index = next(i for i, (before, after) in enumerate(zip(previous, source)) if before != after)
    new_version = list(current_version)
    new_version[index] += 1
    new_version[index + 1:] = [0] * (2 - index)
    return ".".join(map(str, new_version))


def plan_release(base_tag, commit, repository, variant_directory, published_tags):
    base_mod, base_number = base_tag.rsplit("/v", 1)
    base_version = version_tuple(base_number)
    variant = variant_directory.name
    variant_tags = release_tags(variant, run("git", "tag", "--list", f"{variant}/v*").splitlines())
    published = release_tags(variant, published_tags)
    last_release = max(published, key=published.get, default=None)

    source_tags = {}
    for variant_tag in variant_tags:
        matches = re.findall(rf"(?m)^{SOURCE_TAG_FIELD}: ({base_mod}/v{VERSION})$", tag_message(variant_tag))
        if matches:
            (source_tag,) = matches
            source_tags[variant_tag] = source_tag
    reserved = [tag for tag, source in source_tags.items() if source == base_tag]
    if reserved:
        (variant_tag,) = reserved
        if run("git", "rev-parse", f"refs/tags/{variant_tag}^{{commit}}") != commit:
            raise ValueError(f"The reserved tag {variant_tag} points to a different commit.")
        if last_release and published[last_release] >= variant_tags[variant_tag]:
            print(f"{variant_tag} has already been published or superseded by {last_release}.")
            return None
        return variant_tag

    if any(version > base_version for version in release_tags(base_mod, source_tags.values()).values()):
        print(f"{variant} already has a release reserved for a newer {base_mod} tag. Skipping {base_tag}.")
        return None

    candidate = Path(run(sys.executable, "scripts/build.py", str(variant_directory)))
    current = packaged_files(candidate)
    if last_release:
        with TemporaryDirectory() as directory:
            previous = Path(directory) / "published.scs"
            run("gh", "release", "download", last_release, "--repo", repository, "--pattern", "*.scs",
                "--output", str(previous))
            if current == packaged_files(previous):
                print(f"The packaged {variant} files match {last_release}.")
                return None

    manifest = (variant_directory / "src" / "manifest.sii").read_text(encoding="utf-8-sig")
    (version_field,) = VERSION_FIELD.finditer(manifest)
    seed = version_tuple(version_field[2])
    current_version = max((*variant_tags.values(), *published.values()), default=seed)
    base_tags = release_tags(base_mod, run("git", "tag", "--list", f"{base_mod}/v*").splitlines())
    version = next_variant_version(base_version, base_tags.values(), current_version)
    variant_tag = f"{variant}/v{version}"
    notes = tag_message(base_tag)
    message = f"{SOURCE_TAG_FIELD}: {base_tag}"
    if notes:
        message = f"{notes}\n\n{message}"
    run("git", "-c", "user.name=github-actions[bot]", "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com", "tag", "-a", variant_tag, commit,
        "-m", message)
    run("git", "push", "origin", f"refs/tags/{variant_tag}")
    return variant_tag


def plan_releases(base_tag, commit, repository, variants):
    if not re.fullmatch(rf"{MOD_NAME}/v{VERSION}", base_tag):
        raise ValueError(f"Invalid source release tag: {base_tag}")
    if run("git", "rev-parse", f"refs/tags/{base_tag}^{{commit}}") != commit:
        raise ValueError(f"{base_tag} no longer points to {commit}.")
    base_mod = base_tag.rsplit("/v", 1)[0]
    source_config = json.loads((Path("mods") / base_mod / "mod.json").read_text(encoding="utf-8"))
    source_item_id = source_config.get("workshop_item_id")
    workshop_items = {int(source_item_id)} if source_item_id else set()
    configs = {}
    for variant in variants:
        if not re.fullmatch(MOD_NAME, variant) or variant == base_mod:
            raise ValueError(f"Invalid variant directory name: {variant}")
        directory = Path("mods") / variant
        config = json.loads((directory / "mod.json").read_text(encoding="utf-8"))
        if config.get("source_mod") != base_mod or config.get("release_with_source") is not True:
            raise ValueError(f"{directory} does not opt in to automatic releases with {base_mod}.")
        raw_id = config.get("workshop_item_id")
        item_id = str(raw_id) if raw_id is not None else ""
        if item_id and (not re.fullmatch(r"[0-9]+", item_id) or not 0 < int(item_id) < 2**64):
            raise ValueError(f"The Workshop item ID for {variant} must identify an existing item.")
        if item_id:
            if int(item_id) in workshop_items:
                raise ValueError(f"The Workshop item ID for {variant} is shared with another release in this run.")
            workshop_items.add(int(item_id))
        configs[directory] = item_id

    published_tags = run(
        "gh", "api", "--paginate", f"repos/{repository}/releases?per_page=100", "--jq",
        ".[] | select(.draft == false and .prerelease == false) | .tag_name",
    ).splitlines()
    releases = []
    for directory, item_id in configs.items():
        tag = plan_release(base_tag, commit, repository, directory, published_tags)
        if tag:
            print(f"Release {tag} from {base_tag}.")
            releases.append({
                "mod": directory.name,
                "tag": tag,
                "version": tag.rsplit("/v", 1)[1],
                "workshop_item_id": item_id,
            })
    return releases


if __name__ == "__main__":
    releases = plan_releases(
        os.environ["GITHUB_REF_NAME"], os.environ["GITHUB_SHA"], os.environ["GITHUB_REPOSITORY"],
        json.loads(os.environ["RELEASE_VARIANTS"]),
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8", newline="\n") as outputs:
        outputs.write(f"releases={json.dumps(releases, separators=(',', ':'))}\n")
