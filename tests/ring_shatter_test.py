"""Verify manual shatter timing against the bundled builder in Blender."""

from pathlib import Path

import addon_utils
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

from bl_ext.user_default.ua_game_kit.core import builder, ring_pose, ring_shatter

EXTENSION = "bl_ext.user_default.ua_game_kit"
FIXTURE = Path(__file__).with_name("ring_level.json")


def fragments(coll, rid):
    return sorted((obj for obj in coll.all_objects
                   if obj.get("ua_manual_shatter") and obj.get("rp_ring") == rid),
                  key=lambda obj: obj.name)


def motion_keys(obj):
    return { (fc.data_path, fc.array_index): tuple(tuple(key.co) for key in fc.keyframe_points)
             for curves in ring_shatter._curves(obj) for fc in curves
             if fc.data_path in {"location", "rotation_euler", "scale"} }


def eval_matrix(obj, frame):
    bpy.context.scene.frame_set(frame)
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.copy()


def eval_pos(obj, frame):
    return eval_matrix(obj, frame).translation


def mesh_bounds(mesh_poses):
    points = [pose @ vertex.co for mesh, pose in mesh_poses for vertex in mesh.vertices]
    return tuple(bound(point[axis] for point in points)
                 for bound in (min, max) for axis in range(3))


def assert_matrix(actual, expected):
    assert max(abs(a - b) for ra, rb in zip(actual, expected) for a, b in zip(ra, rb)) < 1e-5


def select(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def main():
    assert addon_utils.enable(EXTENSION)
    context = bpy.context
    scene = context.scene
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    assert bpy.ops.ringpuzzle.import_json(filepath=str(FIXTURE)) == {"FINISHED"}
    coll = builder.level_collection(scene)
    rings = {obj["rp_id"]: obj for obj in coll.all_objects if obj.get("rp_kind") == "ring"}
    ring, other = rings["r1"], rings["r2"]
    assert ring_pose.rig_for(coll) is not None and scene.camera.get("ua_upright_camera")
    settings = scene.rp_settings
    settings.shatter_effect = "chunks"
    for timing in ("all", "sweep"):
        settings.shatter_timing = timing
        select(ring)
        scene.frame_set(8)
        assert not ring.get("rp_freed") and not ring.animation_data
        assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
        releases = {obj["ua_release_frame"] for obj in fragments(coll, "r1")}
        assert min(releases) == 8 and scene.frame_current == 8
        assert len(releases) == (settings.shatter_count if timing == "sweep" else 1)
        assert not ring.get("rp_freed") and not motion_keys(ring)
        assert bpy.ops.ua.ring_clear() == {"FINISHED"}
    print("[PASS] both timings break an unopened ring on the chosen frame")

    select(ring)
    scene.frame_set(1)
    assert bpy.ops.ua.ring_unlock() == {"FINISHED"}
    expected = motion_keys(ring)
    pose = eval_matrix(ring, 2)
    assert pose != eval_matrix(ring, 1)
    expected_bounds = mesh_bounds([(ring.data, pose)])
    settings.shatter_target = ring
    for timing in ("all", "sweep"):
        settings.shatter_timing = timing
        scene.frame_set(2)
        assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
        pieces = fragments(coll, "r1")
        assert min(obj["ua_release_frame"] for obj in pieces) == 2
        assert motion_keys(ring) == expected
        actual = mesh_bounds([(obj.data, eval_matrix(obj, 2)) for obj in pieces])
        assert max(abs(a - b) for a, b in zip(actual, expected_bounds)) < 1e-4
    assert bpy.ops.ua.ring_clear() == {"FINISHED"}
    select(ring)
    scene.frame_set(1)
    assert bpy.ops.ua.ring_unlock() == {"FINISHED"}
    print("[PASS] both modes preserve transform keys when breaking during the unlock")

    # The import stands the level up; go back to flat for the pose round trip.
    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    assert ring_pose.rig_for(coll) is None
    ground = next(obj for obj in coll.all_objects if obj.get("rp_kind") == "stage" and obj.type == "MESH")
    clasp = next(obj for obj in coll.all_objects if obj.get("rp_kind") == "clasp")
    original_camera = scene.camera
    original_camera_matrix = eval_matrix(original_camera, 1)
    ground_matrix = eval_matrix(ground, 1)
    ring_matrix = eval_matrix(other, 1)
    clasp_matrix = eval_matrix(clasp, 1)
    expected = motion_keys(ring)
    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    rig = ring_pose.rig_for(coll)
    upright_camera = scene.camera
    assert rig is not None and upright_camera != original_camera
    upright = eval_matrix(rig, 1)
    assert_matrix(eval_matrix(other, 1), upright @ ring_matrix)
    assert_matrix(eval_matrix(clasp, 1), upright @ clasp_matrix)
    assert_matrix(eval_matrix(ground, 1), ground_matrix)
    assert_matrix(eval_matrix(original_camera, 1), original_camera_matrix)
    for obj in rings.values():
        matrix = eval_matrix(obj, 1)
        for vertex in obj.bound_box:
            view = world_to_camera_view(scene, upright_camera, matrix @ Vector(vertex))
            assert 0 < view.x < 1 and 0 < view.y < 1 and view.z > 0, view
    assert motion_keys(ring) == expected
    print("[PASS] upright rings and clasps, front-camera framing, original floor and animation preserved")

    settings = scene.rp_settings
    settings.shatter_target = ring
    settings.shatter_effect = "chunks"
    settings.shatter_timing = "all"
    settings.shatter_count = 8
    frame = 50
    scene.frame_set(frame)
    assert ring.hide_render, "The default unlock fade must already have hidden the original"
    original_mesh = ring.data
    other_action = other.animation_data
    assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
    assert scene.frame_current == frame
    pieces = fragments(coll, "r1")
    assert len(pieces) == 8 and {obj["ua_release_frame"] for obj in pieces} == {frame}
    assert other.animation_data == other_action and not other.hide_render
    assert motion_keys(ring) == expected and ring.data == original_mesh
    scene.frame_set(frame - 1)
    assert not ring.hide_render and all(obj.hide_render for obj in pieces)
    scene.frame_set(frame)
    assert ring.hide_render and all(not obj.hide_render for obj in pieces)
    initial = [eval_pos(obj, frame) for obj in pieces]
    later = [eval_pos(obj, frame + 6) for obj in pieces]
    assert all(p.z > ground_matrix.translation.z for p in initial), initial
    initial_width = max(p.x for p in initial) - min(p.x for p in initial)
    later_width = max(p.x for p in later) - min(p.x for p in later)
    assert later_width > 1.5 * initial_width, (initial_width, later_width)
    for obj, start, mid in zip(pieces, initial, later):
        assert mid.z < start.z
        acceleration = eval_pos(obj, frame + 12) - 2 * mid + start
        assert (acceleration - Vector(scene.gravity) * (6 / 30) ** 2).length < 1e-4
    print(f"[PASS] simultaneous release: lateral span {initial_width:.3f} to {later_width:.3f}; gravity unchanged")

    settings.shatter_count = 12
    settings.shatter_frames = 18
    settings.shatter_timing = "sweep"
    for reverse in (False, True):
        settings.shatter_reverse = reverse
        scene.frame_set(frame)
        assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
        assert scene.frame_current == frame
        pieces = fragments(coll, "r1")
        assert len(pieces) == 12, "Replacing a mode must not duplicate fragments"
        ordered = sorted(obj["ua_release_frame"] for obj in pieces)
        assert len(set(ordered)) == 12 and ordered[0] == frame and ordered[-1] == frame + 18, ordered
        assert pieces[-1 if reverse else 0]["ua_release_frame"] == frame
        for obj in pieces:
            release = obj["ua_release_frame"]
            p0 = eval_pos(obj, frame)
            assert (eval_pos(obj, release) - p0).length < 1e-6
            assert eval_pos(obj, release + 3).z < p0.z
        assert motion_keys(ring) == expected
    print("[PASS] progressive timing and reverse order; unreleased pieces stay in place")

    fragment = pieces[-1]
    samples = [eval_pos(fragment, frame + offset) for offset in (0, 6, 12)]
    release_frames = {obj.name: obj["ua_release_frame"] for obj in pieces}
    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    assert ring_pose.rig_for(coll) is None and scene.camera == original_camera
    assert_matrix(eval_matrix(other, 1), ring_matrix)
    assert_matrix(eval_matrix(clasp, 1), clasp_matrix)
    restored = [eval_pos(fragment, frame + offset) for offset in (0, 6, 12)]
    assert (restored[0] - upright.inverted() @ samples[0]).length < 1e-5
    assert (restored[2] - 2 * restored[1] + restored[0] - Vector(scene.gravity) * 0.04).length < 1e-4
    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    for offset, expected_pos in zip((0, 6, 12), samples):
        assert (eval_pos(fragment, frame + offset) - expected_pos).length < 1e-5
    assert {obj.name: obj["ua_release_frame"] for obj in pieces} == release_frames
    assert motion_keys(ring) == expected
    print("[PASS] standing pose round trip preserves release timing, fall direction and original camera")

    assert bpy.ops.ua.ring_clear() == {"FINISHED"}
    assert not fragments(coll, "r1") and not ring.hide_render and ring.data == original_mesh
    print("[PASS] clear animation removes generated fragments and restores the original")


main()
