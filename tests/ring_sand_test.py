"""Verify the physics sand breakup against the bundled builder in Blender."""

from pathlib import Path

import addon_utils
import bpy

from bl_ext.user_default.ua_game_kit.core import builder

EXTENSION = "bl_ext.user_default.ua_game_kit"
FIXTURE = Path(__file__).with_name("ring_level.json")


def grains(coll, rid):
    return [obj for obj in coll.all_objects
            if obj.get("ua_sand_shatter") and obj.get("rp_ring") == rid]


def eval_pos(obj, frame):
    bpy.context.scene.frame_set(frame)
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation.copy()


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
    frame = 50
    scene.frame_set(frame)
    assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
    pieces = grains(coll, "r1")
    assert len(pieces) == 80 and all(obj["ua_release_frame"] == frame for obj in pieces)
    # 细小圆粒，不是弧形碎块：颗粒直径远小于环管粗细
    assert max(obj.dimensions.length for obj in pieces) < 0.02, \
        max(obj.dimensions.length for obj in pieces)
    floor = next(obj for obj in coll.all_objects if obj.get("ua_upright_part") == "floor")
    dust = [obj for obj in coll.all_objects if obj.get("ua_sand_dust")]
    assert len(dust) >= 24 and all(obj["ua_release_frame"] == frame for obj in dust)
    sample = dust[0]
    dust_end = sample["ua_dust_end"]
    source = sample["ua_dust_source"]
    assert source in pieces and sample.constraints[0].target == source
    scene.frame_set(frame - 1)
    assert sample.hide_render
    assert (eval_pos(sample, frame) - eval_pos(source, frame)).length < 1e-5
    assert not sample.hide_render
    assert (eval_pos(sample, frame + 5) - eval_pos(source, frame + 5)).length < 0.06
    scene.frame_set(dust_end - 1)
    assert not sample.hide_render
    scene.frame_set(dust_end)
    assert sample.hide_render
    assert floor.rigid_body and floor.rigid_body.type == "PASSIVE"
    assert scene.rigidbody_world.point_cache.is_baked
    scene.frame_set(frame - 1)
    assert not ring.hide_render and all(obj.hide_render for obj in pieces)
    scene.frame_set(frame)
    assert ring.hide_render and all(not obj.hide_render for obj in pieces)
    floor_z = floor.matrix_world.translation.z + max(v.co.z for v in floor.data.vertices)
    rest_width = 2 * max((p.x ** 2 + p.y ** 2) ** 0.5
                         for p in (eval_pos(obj, frame) for obj in pieces))
    assert eval_pos(pieces[0], frame + 8).z < eval_pos(pieces[0], frame).z
    late = [eval_pos(obj, frame + 80) for obj in pieces]
    bottom = min(p.z for p in late)
    assert floor_z - 0.02 < bottom < floor_z + 0.05, (bottom, floor_z)
    late_width = 2 * max((p.x ** 2 + p.y ** 2) ** 0.5 for p in late)
    assert late_width > 1.2 * rest_width, (late_width, rest_width)
    settled = [eval_pos(obj, frame + 86) for obj in pieces]
    assert all((a - b).length < 5e-3 for a, b in zip(late, settled))
    print(f"[PASS] sand falls from frame {frame}, spreads and piles on the upright floor")

    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    # 平铺后沙粒的世界轨迹经逆变换映射，位置不再对应地面范围；校验结构而非物理落点。
    assert len(grains(coll, "r1")) == 80
    assert all(obj["ua_release_frame"] == frame for obj in pieces)
    assert scene.rigidbody_world.point_cache.is_baked
    assert bpy.ops.ua.ring_pose() == {"FINISHED"}
    upright_bottom = min(eval_pos(obj, frame + 80).z for obj in pieces)
    assert floor_z - 0.02 < upright_bottom < floor_z + 0.05
    assert all(obj["ua_release_frame"] == frame for obj in pieces)
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
    scene.frame_set(40)
    assert bpy.ops.ua.ring_shatter() == {"FINISHED"}
    pieces = grains(coll, "r1")
    assert len(pieces) == 80
    releases = sorted(obj["ua_release_frame"] for obj in pieces)
    assert releases[0] == 40 and releases[-1] == 40 + 24
    sections = sorted((o for o in coll.all_objects if "ua_sand_section" in o),
                      key=lambda o: o["ua_sand_section"])
    assert len(sections) == len(set(releases)) == settings.shatter_count
    scene.frame_set(39)
    assert not ring.hide_render and all(o.hide_render for o in [*sections, *pieces])
    scene.frame_set(40)
    assert ring.hide_render
    assert sum(not o.hide_render for o in sections) == len(sections) - 1
    assert 0 < sum(not o.hide_render for o in pieces) < len(pieces) / 2
    for section in sections:
        batch = [o for o in pieces if o["ua_sand_source_section"] == section["ua_sand_section"]]
        assert batch
        release = section["ua_release_frame"]
        assert {o["ua_release_frame"] for o in batch} == {release}
        scene.frame_set(release - 1)
        assert all(o.hide_render for o in batch)
        if release > 40:
            assert not section.hide_render
        scene.frame_set(release)
        assert section.hide_render and all(not o.hide_render for o in batch)
    floor = next(obj for obj in coll.all_objects if obj.get("ua_upright_part") == "floor")
    floor_top = floor.matrix_world.translation.z + max(v.co.z for v in floor.data.vertices)
    late = min(eval_pos(obj, 40 + 24 + 60).z for obj in pieces)
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
    assert reverse[-1]["ua_release_frame"] == scene.frame_start
    assert reverse[0]["ua_release_frame"] == scene.frame_start + settings.shatter_frames
    assert reverse[-1].hide_render and not reverse[0].hide_render
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
