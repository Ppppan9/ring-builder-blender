"""Stage a self-contained Blender extension from the supplied builder release."""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
BUILDER_SHA256 = "e408d1ce8aae524230be0cc13c809989a073efd9b1cfa41b78c3ad5383d7bd6d"
VENDOR = "ring_level_builder"
LEGACY = {"beat_detect.py", "candy_ops.py", "candy_render.py", "endcard_lib.py",
          "game_fx_lib.py", "ring_lib.py", "shot_lib.py"}


def stage_extension(builder_zip, destination):
    if hashlib.sha256(builder_zip.read_bytes()).hexdigest() != BUILDER_SHA256:
        raise ValueError("需要用户提供的原始 ring_level_builder_blender_v1.7.0.zip")
    stage = destination.resolve()
    stage.mkdir()
    with ZipFile(builder_zip) as archive:
        for entry in archive.infolist():
            member = PurePosixPath(entry.filename)
            if (member.is_absolute() or ".." in member.parts or "\\" in entry.filename
                    or not member.parts or member.parts[0] != VENDOR
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError(f"Unexpected archive member: {entry.filename}")
            if entry.is_dir():
                continue
            path = stage.joinpath(*member.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, path.open("xb") as target:
                shutil.copyfileobj(source, target)
    for required in ("__init__.py", "rp_scene.py", "web/index.html"):
        if not (stage / VENDOR / required).is_file():
            raise ValueError(f"Missing builder component: {required}")
    for name in ("__init__.py", "blender_manifest.toml", "README.md"):
        shutil.copy2(ROOT / name, stage / name)
    for name in ("core", "ops", "ui"):
        shutil.copytree(ROOT / name, stage / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", *LEGACY))
    return stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("builder_zip", type=Path)
    parser.add_argument("destination", type=Path, help="A new directory for staged sources")
    args = parser.parse_args()
    print(stage_extension(args.builder_zip, args.destination))


if __name__ == "__main__":
    main()
