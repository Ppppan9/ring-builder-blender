"""Package the current shot for editing, without touching existing exports."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import bpy

from . import render_lib


def export_delivery_package(context):
    scene = context.scene
    props = scene.uastudio
    root = Path(bpy.path.abspath(props.out_dir)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    name = render_lib._safe_name(scene.name)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive_path = root / f"delivery_{name}_{stamp}.zip"
    saved = (props.out_dir, scene.render.filepath, scene.render.resolution_percentage,
             scene.render.image_settings.file_format, scene.render.image_settings.color_mode,
             scene.render.film_transparent)
    with TemporaryDirectory() as tmp:
        stage = Path(tmp).resolve()
        try:
            props.out_dir = str(stage)
            movie = Path(render_lib.render_current(context))
            cover = Path(render_lib.export_cover(context, props.cover_frame))
        finally:
            (props.out_dir, scene.render.filepath, scene.render.resolution_percentage,
             scene.render.image_settings.file_format, scene.render.image_settings.color_mode,
             scene.render.film_transparent) = saved
        media = [movie] if movie.suffix == ".mp4" else sorted(stage.glob(f"{movie.name}*.png"))
        if not media or not all(p.is_file() for p in [*media, cover]):
            raise RuntimeError("未找到当前关卡的渲染结果或封面")
        project = stage / "project.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(project), copy=True)
        with ZipFile(archive_path, "x", compression=ZIP_DEFLATED) as archive:
            for path in [project, cover, *media]:
                archive.write(path, path.name)
    return str(archive_path)
