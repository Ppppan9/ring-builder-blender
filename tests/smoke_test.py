"""Run in Blender with the combined extension installed in an isolated profile."""

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import addon_utils
import bpy

EXT = "bl_ext.user_default.ua_game_kit"
FIXTURE = Path(__file__).with_name("ring_level.json")


def check_panel_icons(module):
    path = Path(module.__file__).with_name("ui") / "panels.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = bpy.types.UILayout.bl_rna.functions
    invalid = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        function = functions.get(node.func.attr)
        if function is None or "icon" not in function.parameters:
            continue
        icons = function.parameters["icon"].enum_items
        for kw in node.keywords:
            if kw.arg == "icon" and isinstance(kw.value, ast.Constant) and kw.value.value not in icons:
                invalid.append(f"{path.name}:{node.lineno}: {kw.value.value}")
    assert not invalid, "Unsupported Blender panel icons: " + ", ".join(invalid)
    print("[PASS] panel icons supported by Blender UILayout")


def main():
    module = addon_utils.enable(EXT)
    assert module and addon_utils.check(EXT)[1], "Combined extension failed to load"
    from bl_ext.user_default.ua_game_kit.core import builder, deliver_lib

    check_panel_icons(module)
    context = bpy.context
    scene = context.scene
    assert bpy.ops.ua.build_template() == {"CANCELLED"}
    assert bpy.ops.ua.ring_clear() == {"CANCELLED"}
    for removed in ("hand_tap", "endcard", "shot_setup", "bgm_beats", "add_shape",
                    "apply_material", "candy_scene", "new_project"):
        assert removed not in dir(bpy.ops.ua), removed
    assert not bpy.ops.ua.cam_from_view.poll()
    assert bpy.types.UA_PT_array.bl_category == "解环工坊"
    assert bpy.types.UA_PT_materials.bl_category == "解环工坊"

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    assert bpy.ops.ringpuzzle.import_json(filepath=str(FIXTURE)) == {"FINISHED"}
    coll = builder.level_collection(scene)
    rings = {ob["rp_id"]: ob for ob in coll.all_objects if ob.get("rp_kind") == "ring"}
    assert len(rings) == 5 and sum(ob.get("rp_kind") == "clasp" for ob in coll.all_objects) == 4
    assert context.scene.rp_settings.fx_shatter is False
    mesh_ids = {rid: (ob.as_pointer(), ob.data.as_pointer()) for rid, ob in rings.items()}
    rest = {rid: (ob.location.copy(), ob.rotation_euler.copy()) for rid, ob in rings.items()}
    existing = set(scene.objects)
    cam = scene.camera
    camera_matrix = cam.matrix_world.copy()
    width, height, fps = scene.render.resolution_x, scene.render.resolution_y, scene.render.fps
    assert (width, height, fps) == (1080, 1920, 30)
    print("[PASS] installed package and real builder import")

    bpy.ops.object.select_all(action="DESELECT")
    rings["r1"].select_set(True)
    context.view_layer.objects.active = rings["r1"]
    assert bpy.ops.ua.ring_unlock() == {"FINISHED"}
    assert rings["r1"].get("rp_freed") and rings["r1"].animation_data.action
    assert bpy.ops.ua.ring_clear() == {"FINISHED"}
    assert not any(ob.get("rp_freed") for ob in rings.values())
    for rid, ob in rings.items():
        assert not ob.animation_data
        assert (ob.location - rest[rid][0]).length < 1e-6
        assert tuple(ob.rotation_euler) == tuple(rest[rid][1])
    assert bpy.ops.ua.ring_bake() == {"FINISHED"}
    assert coll.get("rp_baked") == len(rings)
    print("[PASS] single unlock, clear, and full bake")

    # Reject a stale level before the builder clears already-authored animation.
    data = coll["rp_level"]
    level = json.loads(data)
    level["rings"].append(dict(level["rings"][0], id="missing", name="Missing"))
    action = rings["r1"].animation_data.action
    coll["rp_level"] = json.dumps(level)
    assert bpy.ops.ua.build_template() == {"CANCELLED"}
    assert rings["r1"].animation_data.action == action
    coll["rp_level"] = data

    assert bpy.ops.ua.build_template() == {"FINISHED"}
    assert set(scene.objects) == existing
    assert {rid: (ob.as_pointer(), ob.data.as_pointer()) for rid, ob in rings.items()} == mesh_ids
    assert scene.camera == cam and cam.matrix_world == camera_matrix
    assert (scene.render.resolution_x, scene.render.resolution_y, scene.render.fps) == (width, height, fps)
    assert scene.frame_end == builder.animation_end_frame(scene) and scene.frame_end > scene.frame_start
    assert scene.frame_current == scene.frame_start and not scene.timeline_markers
    assert bpy.data.scenes.get("Scene_Endcard") is None
    assert not any(ob.get("rp_kind") == "shard" for ob in coll.all_objects)
    print("[PASS] template preserves models, stage and camera, no post-production content")

    with TemporaryDirectory() as tmp:
        scene.uastudio.out_format = "png_seq"
        scene.uastudio.out_dir = tmp
        scene.render.resolution_x, scene.render.resolution_y = 64, 96
        scene.frame_end = scene.frame_start + 1
        archive_path = deliver_lib.export_delivery_package(context)
        with ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            assert archive.testzip() is None
            assert "project.blend" in names and len([p for p in names if p.endswith(".png")]) == 3
            assert not any("sfx" in p or "Endcard" in p for p in names)
        assert scene.uastudio.out_dir == tmp
    print("[PASS] actual PNG render and current-level delivery archive")

    addon_utils.disable(EXT)
    assert not hasattr(bpy.types.Scene, "rp_settings")
    assert addon_utils.enable(EXT) is not None
    print("[PASS] reload")

    # Exercise the same main-thread handler used by the browser's Send button.
    from bl_ext.user_default.ua_game_kit import ring_level_builder

    assert (Path(ring_level_builder.rp_server.WEB_DIR) / "index.html").is_file()
    result = ring_level_builder.handle_job(
        "level", {"level": json.loads(FIXTURE.read_text(encoding="utf-8")), "bake": {}})
    assert result["ok"] and result["data"].get("baked") == 5
    assert not any(ob.get("rp_kind") == "shard" for ob in builder.level_collection(scene).all_objects)
    print("[PASS] bundled browser assets and Send-to-Blender handler")
    print("SMOKE RESULT: ALL PASS")


main()
