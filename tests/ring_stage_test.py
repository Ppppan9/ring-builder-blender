"""Check the upright stage with the real builder and an actual camera render."""

import json
import sys
from pathlib import Path

import addon_utils
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

EXTENSION = "bl_ext.user_default.ua_game_kit"
FIXTURE = Path(__file__).with_name("ring_level.json")


def parts(coll, kind):
    return [obj for obj in coll.all_objects if obj.get("ua_upright_part") == kind]


def flags(obj):
    return obj.hide_render, bool(obj.hide_viewport)


def assert_framed(scene, coll):
    for ring in coll.objects:
        if ring.get("rp_kind") != "ring":
            continue
        for coord in ring.bound_box:
            point = world_to_camera_view(scene, scene.camera, ring.matrix_world @ Vector(coord))
            assert 0 < point.x < 1 and 0 < point.y < 1 and point.z > 0, point


def assert_geometry(scene, coll):
    floor, = parts(coll, "floor")
    backdrop, = parts(coll, "background")
    up = Vector((0, 0, 1))
    assert abs(floor.data.polygons[0].normal.dot(up)) > 0.999
    assert abs(backdrop.data.polygons[0].normal.dot(up)) < 1e-6
    assert all(vertex.co.y > 0 for vertex in backdrop.data.vertices)
    # The wall and floor meet inside the camera frame.
    far_y = max(v.co.y for v in floor.data.vertices)
    top_edge = max((v for v in floor.data.vertices if v.co.y == far_y),
                   key=lambda v: v.co.z).co
    seam = world_to_camera_view(scene, scene.camera,
                                floor.matrix_world @ Vector((0.0, top_edge.y, top_edge.z)))
    assert 0.06 < seam.y < 0.45, seam
    assert len(parts(coll, "light")) == 3
    for obj in parts(coll, "light"):
        aim = obj.matrix_world.to_quaternion() @ Vector((0, 0, -1))
        target = next(o for o in coll.objects if o.get("ua_upright_rig")).location
        assert aim.dot((target - obj.location).normalized()) > 0.999
    assert_framed(scene, coll)


def main():
    assert addon_utils.enable(EXTENSION)
    from bl_ext.user_default.ua_game_kit import ring_level_builder
    from bl_ext.user_default.ua_game_kit.core import builder, physics_lib, scene_lib

    out = Path(sys.argv[sys.argv.index("--") + 1])
    scene = bpy.context.scene
    props = scene.uastudio
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    assert bpy.ops.ringpuzzle.import_json(filepath=str(FIXTURE)) == {"FINISHED"}
    coll = builder.level_collection(scene)
    # Import stands the level up by itself.
    assert ring_pose_rig(coll) is not None and scene.camera.get("ua_upright_camera")
    assert bpy.ops.ua.set_lighting() == {"FINISHED"}
    assert_geometry(scene, coll)
    camera = scene.camera
    frame = scene.frame_current
    camera_matrix = camera.matrix_world.copy()
    original_scale = camera.data.ortho_scale
    scene.uastudio.aspect = "16:9"
    assert bpy.ops.ua.apply_size() == {"FINISHED"}
    assert camera == scene.camera and scene.frame_current == frame
    assert camera.matrix_world == camera_matrix and camera.data.ortho_scale > original_scale
    assert scene.objects.get("UA_Camera") is None
    assert_geometry(scene, coll)
    scene.uastudio.aspect = "9:16"
    assert bpy.ops.ua.apply_size() == {"FINISHED"}
    assert abs(camera.data.ortho_scale - original_scale) < 1e-6
    print("[PASS] import stands the level up; scenery and framing hold across formats")

    world = scene.world
    floor = parts(coll, "floor")[0]
    energies = {o.name: o.data.energy for o in parts(coll, "light")}
    props.light_strength = 2
    for _ in range(2):
        assert bpy.ops.ua.set_lighting() == {"FINISHED"}
        assert len(parts(coll, "light")) == 3
        assert all(abs(o.data.energy / energies[o.name] - 2) < 1e-5 for o in parts(coll, "light"))
    props.light_mode = "none"
    assert bpy.ops.ua.set_lighting() == {"FINISHED"} and not parts(coll, "light")
    props.light_mode = "sky"
    assert bpy.ops.ua.set_lighting() == {"FINISHED"} and len(parts(coll, "light")) == 1
    props.light_mode, props.light_strength = "three_point", 1.0
    assert bpy.ops.ua.set_lighting() == {"FINISHED"} and scene.world == world
    props.bg_mode = "flat"
    props.bg_bottom = (0.24, 0.18, 0.1)
    for _ in range(2):
        assert bpy.ops.ua.set_background() == {"FINISHED"}
        board, = parts(coll, "background")
        emission = next(n for n in board.data.materials[0].node_tree.nodes if n.type == "EMISSION")
        color = emission.inputs["Color"].default_value
        assert (Vector(color[:3]) - Vector(props.bg_bottom)).length < 1e-5
    assert parts(coll, "floor") == [floor] and scene.camera == camera
    props.bg_mode = "gradient"
    props.bg_bottom = (0.25, 0.55, 0.95)
    assert bpy.ops.ua.set_background() == {"FINISHED"}
    for _ in range(2):
        assert bpy.ops.ua.set_stage() == {"FINISHED"} and len(parts(coll, "floor")) == 1
    assert_geometry(scene, coll)
    print("[PASS] repeated stage controls produce one set of scenery without replacing the camera")

    scene.render.resolution_percentage = 25
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(out / "upright.png")
    assert bpy.ops.render.render(write_still=True) == {"FINISHED"}
    image = bpy.data.images.load(scene.render.filepath)
    width, height = image.size
    pixels = image.pixels[:]
    bpy.data.images.remove(image)

    def sample(x, y):
        offset = 4 * (int(y * height) * width + int(x * width))
        return Vector(pixels[offset:offset + 3])

    top, middle, floor_color = (sample(0.08, y) for y in (0.93, 0.53, 0.05))
    assert (middle - top).length > 0.06, (top, middle)
    assert (middle - floor_color).length > 0.1 and 0.05 < max(floor_color) < 0.9, floor_color
    print("[PASS] upright camera render includes a gradient backdrop and a non-clipped floor")

    assert physics_lib.set_stage_passive(bpy.context) == 1
    assert parts(coll, "floor")[0].rigid_body.type == "PASSIVE"
    print("[PASS] only the visible upright floor is selected as a collider")

    # Everything below starts from the flat state.
    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    assert ring_pose_rig(coll) is None
    scene_lib.set_lighting(bpy.context, props)
    authored = bpy.data.objects.new("Custom lighting", bpy.data.lights.new("Custom lighting", "POINT"))
    authored.hide_viewport = authored.hide_render = True
    scene.collection.objects.link(authored)
    workshop = bpy.data.collections["UA_Lights"].objects[:]
    workshop[0].hide_render = True
    flat = {obj.name: flags(obj) for obj in [*workshop, *coll.objects]
            if obj.type in {"LIGHT", "MESH"} and (obj in workshop or obj.get("rp_kind") == "stage")}
    top_camera = scene.camera
    top_camera_name = top_camera.name
    assert top_camera.get("ua_upright_camera") is None
    assert flags(authored) == (True, True)
    print("[PASS] restoring the flat pose brings back the flat scenery, flags and camera")

    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    saved = str(out / "stage-test.blend")
    assert bpy.ops.wm.save_as_mainfile(filepath=saved) == {"FINISHED"}
    assert bpy.ops.wm.open_mainfile(filepath=saved, load_ui=False) == {"FINISHED"}
    scene = bpy.context.scene
    coll = builder.level_collection(scene)
    assert ring_pose_rig(coll) is not None
    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    assert scene.camera == scene.objects.get(top_camera_name)
    assert not any(obj.get("ua_upright_part") for obj in coll.all_objects)
    assert all(flags(scene.objects[name]) == expected for name, expected in flat.items())
    print("[PASS] saving and reopening preserves the flat scenery and camera for restoration")

    names = [obj.name for obj in bpy.data.collections["UA_Lights"].objects]
    for replace, stands_up in (
        (lambda: bpy.ops.ringpuzzle.import_json(filepath=str(FIXTURE)) == {"FINISHED"}, True),
        (lambda: ring_level_builder.handle_job("level", json.loads(FIXTURE.read_text()))["ok"], True),
        (lambda: ring_level_builder.handle_job("clear", {})["ok"], False),
    ):
        assert bpy.ops.ua.ring_pose() == {"FINISHED"}
        assert replace()
        if stands_up:
            assert ring_pose_rig(builder.level_collection(scene)) is not None
            assert bpy.ops.ua.ring_pose() == {"FINISHED"}
        assert all(flags(scene.objects[name]) == flat[name] for name in names)
        assert flags(scene.objects["Custom lighting"]) == (True, True)
        assert not any(obj.get("ua_upright_part") or obj.get("ua_upright_rig") for obj in scene.objects)
        assert not any(mat.get("ua_upright_part") for mat in bpy.data.materials)
    print("[PASS] JSON import, browser Send and browser Clear leave no upright leftovers")


def ring_pose_rig(coll):
    from bl_ext.user_default.ua_game_kit.core import ring_pose

    return ring_pose.rig_for(coll)


main()
