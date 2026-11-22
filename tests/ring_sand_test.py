"""Verify the physics sand breakup against the bundled builder in Blender."""

from pathlib import Path

import addon_utils
import bpy
from mathutils import Vector

from bl_ext.user_default.ua_game_kit.core import builder, ring_shatter

EXTENSION = "bl_ext.user_default.ua_game_kit"
FIXTURE = Path(__file__).with_name("ring_level.json")


def grains(coll, rid):
    return [obj for obj in coll.all_objects
            if obj.get("ua_sand_shatter") and obj.get("rp_ring") == rid]


def eval_matrix(obj, frame):
    bpy.context.scene.frame_set(frame)
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.copy()


def eval_pos(obj, frame):
    return eval_matrix(obj, frame).translation


def carriers(coll):
    return sorted((o for o in coll.all_objects if o.get("ua_sand_carrier")),
                  key=lambda o: o["ua_sand_section"])


def assert_crumble(scene, section, grains):
    detach = section["ua_release_frame"]
    start, end = section["ua_sand_crumble"], section["ua_sand_end"]
    assert detach + 2 < start < end - 2
    batch = [o for o in grains if o["ua_sand_source"] == section]
    assert len(batch) > 1
    assert min(o["ua_release_frame"] for o in batch) == start
    assert max(o["ua_release_frame"] for o in batch) == end - 1
    before = eval_matrix(section, detach)
    falling = eval_matrix(section, start - 1)
    assert not section.hide_render and section.visible_get()
    assert all(o.hide_render and not o.visible_get() for o in batch)
    assert before.translation.z - falling.translation.z > 0.005
    assert before.to_quaternion().rotation_difference(falling.to_quaternion()).angle > 0.05
    assert (falling.to_scale() - before.to_scale()).length < 1e-5
    for obj in batch:
        release = obj["ua_release_frame"]
        scene.frame_set(release - 1)
        assert obj.hide_render
        source_pose = eval_matrix(section, release)
        point = source_pose @ Vector(obj["ua_sand_local_birth"])
        keyed_birth = Vector([keys[-1].co.y for keys in ring_shatter._keyed_components(obj, "location", 3)[1]])
        assert (keyed_birth - point).length < 1e-5
        assert not obj.hide_render and obj.visible_get() and not section.hide_render
    assert eval_matrix(section, end - 1).to_scale().length < 0.12 * before.to_scale().length
    scene.frame_set(end)
    assert section.hide_render and all(not o.hide_render for o in batch)


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
    ring = rings["r1"]
    settings = scene.rp_settings
    settings.sand_count = 80
    settings.shatter_effect = "sand"
    settings.shatter_timing = "all"
    select(ring)
    trigger = 50
    detach = trigger + 1
    scene.frame_set(trigger)
    assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
    pieces = grains(coll, "r1")
    sections = carriers(coll)
    assert scene.frame_current == trigger
    assert not ring.hide_render and ring.visible_get()
    assert all(o.hide_render and not o.visible_get() for o in [*pieces, *sections])
    assert len(pieces) == 80 and len(sections) > 1
    assert {o["ua_release_frame"] for o in sections} == {detach}
    scene.frame_set(detach)
    assert ring.hide_render and all(o.visible_get() for o in sections)
    assert all(o.hide_render for o in pieces)
    assert_crumble(scene, sections[0], pieces)
    frame = min(o["ua_release_frame"] for o in pieces)
    assert len({o["ua_release_frame"] for o in pieces}) > 2
    # 细小圆粒，不是弧形碎块：颗粒直径远小于环管粗细
    assert max(obj.dimensions.length for obj in pieces) < 0.02, \
        max(obj.dimensions.length for obj in pieces)
    floor = next(obj for obj in coll.all_objects if obj.get("ua_upright_part") == "floor")
    dust = [obj for obj in coll.all_objects if obj.get("ua_sand_dust")]
    assert len(dust) >= 24
    sample = dust[0]
    dust_end = sample["ua_dust_end"]
    source = sample["ua_dust_source"]
    release = source["ua_release_frame"]
    assert source in pieces and sample.constraints[0].target == source
    assert sample["ua_release_frame"] == release
    scene.frame_set(release - 1)
    assert sample.hide_render
    assert (eval_pos(sample, release) - eval_pos(source, release)).length < 1e-5
    assert not sample.hide_render
    assert (eval_pos(sample, release + 5) - eval_pos(source, release + 5)).length < 0.06
    scene.frame_set(dust_end - 1)
    assert not sample.hide_render
    scene.frame_set(dust_end)
    assert sample.hide_render
    assert floor.rigid_body and floor.rigid_body.type == "PASSIVE"
    assert scene.rigidbody_world.point_cache.is_baked
    scene.frame_set(frame - 1)
    assert ring.hide_render and all(obj.hide_render for obj in pieces)
    assert all(o.visible_get() for o in sections)
    scene.frame_set(frame)
    assert 0 < sum(not o.hide_render for o in pieces) < len(pieces)
    floor_z = max((floor.matrix_world @ v.co).z for v in floor.data.vertices)
    releases = {o.name: o["ua_release_frame"] for o in pieces}
    assert eval_pos(source, release + 8).z < eval_pos(source, release).z
    late = [eval_pos(obj, frame + 80) for obj in pieces]
    bottom = min(p.z for p in late)
    assert floor_z - 0.02 < bottom < floor_z + 0.05, (bottom, floor_z)
    assert max(p.z for p in late) < floor_z + 0.08, "All grains should settle close to the floor"
    settled = [eval_pos(obj, frame + 86) for obj in pieces]
    assert all((a - b).length < 5e-3 for a, b in zip(late, settled))
    print("[PASS] overall mode shows falling solid pieces before the grains appear and land")

    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    # 平铺后沙粒的世界轨迹经逆变换映射，位置不再对应地面范围；校验结构而非物理落点。
    assert len(grains(coll, "r1")) == 80
    assert {o.name: o["ua_release_frame"] for o in pieces} == releases
    assert scene.rigidbody_world.point_cache.is_baked
    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    upright_bottom = min(eval_pos(obj, frame + 80).z for obj in pieces)
    assert floor_z - 0.02 < upright_bottom < floor_z + 0.05
    assert {o.name: o["ua_release_frame"] for o in pieces} == releases
    print("[PASS] pose switches move the rest pose and re-simulate on the matching floor")

    settings.shatter_count = 6
    settings.shatter_target = ring
    scene.frame_set(20)
    settings.shatter_effect = "chunks"
    settings.shatter_timing = "all"
    assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
    manual_names = {obj.name for obj in coll.all_objects if obj.get("ua_manual_shatter")}
    assert manual_names
    scene.frame_set(30)
    settings.shatter_effect = "sand"
    settings.shatter_timing = "all"
    assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
    assert not (manual_names & {obj.name for obj in coll.all_objects})
    assert len(grains(coll, "r1")) == 80
    print("[PASS] sand replaces an existing manual breakup for the same ring")

    assert bpy.ops.ua.ring_clear() == {"FINISHED"}
    assert not grains(coll, "r1")
    assert not any(obj.get("ua_sand_dust") for obj in coll.all_objects)
    assert not ring.hide_render
    print("[PASS] clear removes sand grains, dust and restores the ring")

    # Progressive sand: grains pour one after another along the C opening.
    settings.shatter_effect = "sand"
    settings.shatter_timing = "sweep"
    settings.shatter_frames = 24
    trigger = 40
    handoff = trigger + 1
    scene.frame_set(trigger)
    assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
    pieces = grains(coll, "r1")
    assert len(pieces) == 80
    sections = carriers(coll)
    detach_frames = [o["ua_release_frame"] for o in sections]
    assert detach_frames == sorted(set(detach_frames))
    assert detach_frames[0] == handoff and detach_frames[-1] == handoff + 24
    assert len(sections) == settings.shatter_count
    assert scene.frame_current == trigger
    assert not ring.hide_render and ring.visible_get()
    assert all(o.hide_render and not o.visible_get() for o in [*sections, *pieces])
    scene.frame_set(handoff)
    assert ring.hide_render and not ring.visible_get()
    assert all(not o.hide_render and o.visible_get() for o in sections)
    assert all(o.hide_render for o in pieces)
    assert (eval_matrix(sections[-1], handoff) - eval_matrix(sections[-1], detach_frames[-1]))[0].length < 1e-5
    for section in sections:
        assert_crumble(scene, section, pieces)
    floor = next(obj for obj in coll.all_objects if obj.get("ua_upright_part") == "floor")
    floor_top = max((floor.matrix_world @ v.co).z for v in floor.data.vertices)
    late_frame = max(o["ua_release_frame"] for o in pieces) + 60
    late = min(eval_pos(obj, late_frame).z for obj in pieces)
    assert floor_top - 0.02 < late < floor_top + 0.05, (late, floor_top)
    dust = [o for o in coll.all_objects if o.get("ua_sand_dust")]
    assert all(o["ua_dust_source"] in pieces and o["ua_release_frame"]
               == o["ua_dust_source"]["ua_release_frame"] for o in dust)
    assert len({o.data for o in pieces}) == 3 and not any(o.rigid_body for o in sections + dust)
    print("[PASS] progressive sand replaces one solid section at a time, with dust sourced from grains")

    # Regenerate the same ring on the first timeline frame, with the opposite tip leading.
    settings.shatter_reverse = True
    settings.sand_dust = False
    scene.frame_set(scene.frame_start)
    assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
    reverse = sorted((o for o in coll.all_objects if "ua_sand_section" in o),
                     key=lambda o: o["ua_sand_section"])
    assert len(reverse) == len(sections) and len(grains(coll, "r1")) == 80
    assert not ring.hide_render and ring.visible_get()
    assert all(o.hide_render and not o.visible_get() for o in [*reverse, *grains(coll, "r1")])
    handoff = scene.frame_start + 1
    assert reverse[-1]["ua_release_frame"] == handoff
    assert reverse[0]["ua_release_frame"] == handoff + settings.shatter_frames
    scene.frame_set(handoff)
    assert all(o.visible_get() for o in reverse)
    assert all(o.hide_render for o in grains(coll, "r1"))
    assert_crumble(scene, reverse[-1], grains(coll, "r1"))
    assert reverse[0].visible_get()
    scene.frame_set(scene.frame_start)
    assert not ring.hide_render and ring.visible_get()
    assert not any(o.get("ua_sand_dust") for o in coll.all_objects)
    print("[PASS] reverse sweep starts on the opposite tip, replaces old pieces and respects dust off")

    sand_scene = bpy.data.scenes.new("SandWithoutFloor")
    context.window.scene = sand_scene
    sand_scene.rp_settings.stage = False
    sand_scene.rp_settings.shatter_effect = "sand"
    sand_scene.rp_settings.shatter_timing = "all"
    assert bpy.ops.ringpuzzle.import_json(filepath=str(FIXTURE)) == {"FINISHED"}
    bare = builder.level_collection(sand_scene)
    ring2 = next(obj for obj in bare.all_objects if obj.get("rp_id") == "r1")
    select(ring2)
    sand_scene.frame_set(10)
    assert bpy.ops.ua.ring_shatter() == {"CANCELLED"}
    assert not grains(bare, "r1")
    print("[PASS] sand requires a visible floor to pile on")


main()
