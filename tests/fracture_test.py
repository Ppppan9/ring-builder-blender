"""Run with the combined extension and Cell Fracture installed in a test profile."""

from pathlib import Path

import addon_utils
import bpy

from bl_ext.user_default.ua_game_kit.core import builder

EXTENSION = "bl_ext.user_default.ua_game_kit"
CELL_FRACTURE = "bl_ext.blender_org.cell_fracture"
FIXTURE = Path(__file__).with_name("ring_level.json")


def fracture_level(name, *, with_floor, explode=False, previous=()):
    context = bpy.context
    scene = bpy.data.scenes.new(name)
    context.window.scene = scene
    scene.rp_settings.stage = with_floor
    assert bpy.ops.ringpuzzle.import_json(filepath=str(FIXTURE)) == {"FINISHED"}
    if builder.is_upright(builder.level_collection(scene)):
        # The generic Cell Fracture path is exercised on the plain flat level.
        assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    scene.frame_end = 12
    scene.uastudio.fracture_count = 8
    scene.uastudio.fracture_noise = 0.0
    scene.uastudio.fracture_explode = explode

    original = set(scene.objects)
    assert not original.intersection(previous)
    ground = [obj for obj in original if obj.type == "MESH" and obj.get("rp_kind") == "stage"]
    assert len(ground) == int(with_floor)
    assert all(not obj.name.startswith("UA_Stage_") for obj in original)
    ring = next(obj for obj in original if obj.get("rp_id") == "r1")
    bpy.ops.object.select_all(action="DESELECT")
    ring.select_set(True)
    context.view_layer.objects.active = ring
    assert bpy.ops.ua.fracture() == {"FINISHED"}

    generated = set(scene.objects) - original
    assert not generated.intersection(previous), "Fragments leaked in from another scene"
    pieces = {obj for obj in generated if obj.type == "MESH"}
    assert len(pieces) > 1, "Cell Fracture did not split the imported ring"
    assert all(obj.rigid_body and obj.rigid_body.type == "ACTIVE" for obj in pieces)
    fields = generated - pieces
    assert len(fields) == int(explode)
    if fields:
        field = fields.pop().field
        assert field.type == "FORCE" and field.strength > 0
    assert bpy.data.objects.get(ring.name) == ring
    assert scene.rigidbody_world.point_cache.is_baked
    if ground:
        assert ground[0].rigid_body.type == "PASSIVE"
        assert ground[0].rigid_body.collision_shape == "BOX"
    else:
        assert all(not obj.rigid_body for obj in original)
    print(f"[PASS] {scene.name}: {len(pieces)} active fragments, baked simulation")
    return generated


def main():
    assert addon_utils.enable(EXTENSION)
    assert addon_utils.enable(CELL_FRACTURE)
    first = fracture_level("FractureWithFloor", with_floor=True)
    fracture_level("FractureWithoutFloor", with_floor=False, explode=True, previous=first)


main()
