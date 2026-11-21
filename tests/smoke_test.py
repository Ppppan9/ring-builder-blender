"""UA Game Kit 冒烟测试（headless，/tmp 运行副本）。"""

import math
import os
import sys
import time

import addon_utils
import bpy

OUT_DIR = "/tmp/ua_render"
FAILS = []


def shot_lib_export():
    from bl_ext.user_default.ua_game_kit.core import shot_lib
    return shot_lib.export_sfx_list(bpy.context, "/tmp/ua_render/matrix")


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    line = f"[{tag}] {name}" + (f" | {detail}" if detail else "")
    print(line)
    if not cond:
        FAILS.append(name)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ok = addon_utils.enable("bl_ext.user_default.ua_game_kit")
    check("extension_enable", ok is not None)

    sc = bpy.context.scene

    bpy.ops.ua.new_project()
    names = ("UA_Camera", "UA_Light_Key", "UA_Stage_Podium", "UA_Backdrop")
    missing = [n for n in names if bpy.data.objects.get(n) is None]
    check("new_project_objects", not missing, f"missing={missing}")

    settings_ok = (
        sc.render.resolution_x == 1080
        and sc.render.resolution_y == 1920
        and sc.render.fps == 30
        and sc.frame_end == 450
    )
    check(
        "new_project_settings",
        settings_ok,
        f"res={sc.render.resolution_x}x{sc.render.resolution_y} "
        f"fps={sc.render.fps} end={sc.frame_end}",
    )

    engine_ok = sc.render.engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT")
    check("engine_eevee", engine_ok, sc.render.engine)
    check("camera_set", sc.camera is not None)

    bpy.ops.ua.set_background()
    bpy.ops.ua.set_stage()
    bpy.ops.ua.set_lighting()

    from bl_ext.user_default.ua_game_kit.core import deps

    deps.scan()
    ready, total, worst = deps.summary()
    print(f"[INFO] deps: {ready}/{total} ready, worst={deps.status_text(worst)}")
    check("deps_scan", total >= 9, f"total={total}")

    # ---- 资产 ----
    added = []
    for key in ("cube", "ball", "gem", "coin", "capsule", "star",
                "dice", "screw", "puzzle", "crate", "candy", "bomb"):
        try:
            bpy.ops.ua.add_shape(key=key)
            added.append(key)
        except Exception as exc:
            print(f"[WARN] shape {key}: {exc}")
    check("shapes_added", len(added) == 12, f"{len(added)}/12")
    names_now = {o.name for o in sc.objects}
    check("shape_objects", {"UA_Cube", "UA_Coin", "UA_Puzzle", "UA_Bomb"} <= names_now)

    # 排列：先删一堆，留一个球做散布
    for ob in list(sc.objects):
        if ob.name.startswith("UA_") and ob.name not in (
            "UA_Camera", "UA_Backdrop", "UA_Stage_Podium", "UA_Ball",
        ):
            bpy.data.objects.remove(ob, do_unlink=True)
    ball = bpy.data.objects["UA_Ball"]
    bpy.ops.object.select_all(action="DESELECT")
    ball.select_set(True)
    bpy.context.view_layer.objects.active = ball
    n = bpy.ops.ua.scatter()  # 默认 8 个
    check("scatter", n == {"FINISHED"}, str(n))

    # 文字
    bpy.ops.ua.text3d()
    check("text3d", bpy.data.objects.get("UA_Text") is not None)

    # ---- 材质 ----
    for ob in list(sc.objects):
        if ob.name.startswith("UA_Ball") or ob.name.startswith("UA_Ball."):
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
            break
    bpy.ops.ua.apply_material(key="gold")
    check("material_gold", "UA_gold" in {m.name for m in bpy.data.materials})
    sc.uastudio.mat_color = (0.2, 0.6, 1.0)
    bpy.ops.ua.apply_material(key="candy")
    check("material_candy", "UA_candy" in {m.name for m in bpy.data.materials})

    # ---- 动画与相机 ----
    bpy.ops.object.select_all(action="DESELECT")
    for ob in sc.objects:
        if ob.name.startswith("UA_Ball"):
            ob.select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["UA_Ball"]
    r = bpy.ops.ua.anim_entrance(mode="drop")
    check("entrance_drop", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.anim_loop(mode="float")
    check("loop_float", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.anim_easing(mode="elastic")
    check("easing_elastic", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.add_beat()
    check("add_beat", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.cam_move(mode="orbit")
    check("cam_orbit", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.cam_move(mode="push_in")
    check("cam_push_in", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.cam_move(mode="shake")
    cam = sc.camera
    check("cam_shake", cam.animation_data is not None)
    r = bpy.ops.ua.safety_frame()
    check("safety_frame", bpy.data.objects.get("UA_SafeFrame") is not None)

    # ---- 物理 ----
    r = bpy.ops.ua.drop_pile()
    check("drop_pile", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.impact()
    check("impact", r == {"FINISHED"}, str(r))

    bpy.ops.ua.add_shape(key="cube")
    cube = bpy.context.view_layer.objects.active
    bpy.ops.object.select_all(action="DESELECT")
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    r = bpy.ops.ua.fracture()
    check("fracture", r == {"FINISHED"}, str(r))
    pieces = [o for o in sc.objects
              if o.type == "MESH" and o.name.startswith("UA_Cube")]
    check("fracture_pieces", len(pieces) >= 10,
          "pieces=" + str(len(pieces)))

    r = bpy.ops.ua.fx_particle(kind="coins")
    check("fx_coins", r == {"FINISHED"}, str(r))
    emitters = [o for o in sc.objects if o.name.startswith("UA_FX_")]
    check("fx_emitters", len(emitters) >= 1)

    r = bpy.ops.ua.physics_bake()
    check("physics_bake", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.physics_clear()
    check("physics_clear", r == {"FINISHED"}, str(r))

    r = bpy.ops.ua.flag()
    check("flag", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.tablecloth()
    check("tablecloth", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.jelly()
    check("jelly", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.rope()
    check("rope", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.fluid_splash()
    check("fluid_splash", r == {"FINISHED"}, str(r))

    sc.uastudio.fluid_resolution = 24
    r = bpy.ops.ua.physics_bake()
    check("physics_bake2", r == {"FINISHED"}, str(r))

    # ---- 渲染与结尾卡 ----
    sc.uastudio.out_format = "png_seq"
    r = bpy.ops.ua.endcard()
    check("endcard", r == {"FINISHED"}, str(r))
    ec_names = [o.name for o in sc.objects if o.name.startswith(("UA_Endcard", "UA_CTA"))]
    check("endcard_objects", len(ec_names) >= 3, str(ec_names[:4]))
    check("endcard_animated",
          bpy.data.objects.get("UA_EndcardBtn").animation_data is not None)

    # ---- 假玩法与投放输出 ----
    try:
        bpy.context.window.scene = sc
    except (AttributeError, RuntimeError):
        pass
    bpy.ops.ua.add_shape(key="ball")
    r = bpy.ops.ua.hand_tap()
    check("hand_tap", r == {"FINISHED"}, str(r))
    check("hand_object", bpy.data.objects.get("UA_Hand") is not None)
    r = bpy.ops.ua.fx_vanish(mode="corner")
    check("fx_collect", r == {"FINISHED"}, str(r))
    r = bpy.ops.ua.fx_score()
    check("fx_score", bpy.data.objects.get("UA_ScoreTxt") is not None)
    r = bpy.ops.ua.hud_score()
    check("hud_score", bpy.data.objects.get("UA_HUD_ScoreBG") is not None)
    hud = bpy.data.objects.get("UA_HUD_ScoreBG")
    check("hud_parented", hud is not None and hud.parent is not None
          and hud.parent.type == "CAMERA")
    r = bpy.ops.ua.hud_progress()
    check("hud_progress", bpy.data.objects.get("UA_HUD_BarFill") is not None)

    r = bpy.ops.ua.cleanup_project()
    check("cleanup", r == {"FINISHED"}, str(r))

    sc.uastudio.out_format = "mp4"
    sc.uastudio.out_dir = "/tmp/ua_render/matrix"
    sc.frame_end = 6
    sc.render.resolution_percentage = 25
    r = bpy.ops.ua.size_matrix()
    check("size_matrix", r == {"FINISHED"}, str(r))
    mats = [f for f in os.listdir("/tmp/ua_render/matrix") if f.endswith(".mp4")]
    check("matrix_files", len(mats) == 3, str(sorted(mats)))

    r = bpy.ops.ua.export_cover()
    cover = [f for f in os.listdir("/tmp/ua_render/matrix") if "cover" in f]
    check("export_cover", r == {"FINISHED"} and len(cover) >= 1, str(cover))

    # ---- 分镜 / 模板 / 贴纸 ----
    r = bpy.ops.ua.shot_setup()
    shots = sc.uastudio.shots
    check("shot_setup", r == {"FINISHED"} and len(shots) == 4,
          str([s.name for s in shots]))
    r = bpy.ops.ua.shot_goto(index=1)
    check("shot_goto", r == {"FINISHED"} and sc.frame_start == shots[1].start)
    r = bpy.ops.ua.add_sticker()
    check("add_sticker", bpy.data.objects.get("UA_Sticker_Base") is not None)
    try:
        path = shot_lib_export()
        check("sfx_list", os.path.exists(path))
    except Exception as exc:
        check("sfx_list", False, str(exc))

    # 模板构建（示例 + 解环）
    for tkey, min_obj in (("example", 6), ("ring_unlock", 12)):
        r = bpy.ops.ua.build_template(key=tkey)
        main = bpy.data.scenes["Scene"]
        end = bpy.data.scenes.get("Scene_Endcard")
        beats = len([m for m in main.timeline_markers
                     if m.name.startswith("beat")])
        check("tpl_" + tkey,
              r == {"FINISHED"} and len(main.objects) >= min_obj
              and main.frame_end == 450 and beats >= 4
              and len(main.uastudio.shots) == 4 and end is not None,
              "obj=" + str(len(main.objects)) + " beats=" + str(beats))

    main = bpy.data.scenes["Scene"]
    ring_objs = [o for o in main.objects if o.name.startswith("UA_Ring_")]
    slot_objs = [o for o in main.objects if o.name.startswith("UA_Slot_")]
    word_objs = [o for o in main.objects if o.name.startswith("UA_Word")]
    check("tpl_ring_scene", len(ring_objs) >= 5
          and bpy.data.objects.get("UA_Hub_Ring") is not None
          and len(slot_objs) >= 3 and len(word_objs) >= 6,
          f"rings={len(ring_objs)} slots={len(slot_objs)} words={len(word_objs)}")

    # ---- 解环玩法 ring_lib 单元 ----
    from bl_ext.user_default.ua_game_kit.core import ring_lib

    ring = ring_lib.make_c_ring(bpy.context, color="green", radius=0.34)
    check("ring_mesh", ring is not None and len(ring.data.polygons) >= 200
          and ring.material_slots[0].material is not None,
          "polys=" + str(len(ring.data.polygons)))
    check("ring_props", ring.get("rp_kind") == "ring"
          and ring.get("ua_color") == "green")
    clasp = ring_lib.make_clasp(bpy.context)
    check("clasp", clasp is not None and len(clasp.data.polygons) > 0)
    hub = ring_lib.make_hub(bpy.context, style="ring")
    check("hub_ring", hub is not None and hub.get("rp_kind") == "prop")
    hub2 = ring_lib.make_hub(bpy.context, style="cube")
    check("hub_cube", hub2 is not None and hub2.name == "UA_Hub_Cube")
    slots = ring_lib.make_slot_row(bpy.context, colors=("green", "blue", "purple"))
    check("slots", len(slots) == 3 and all(
        s["obj"] is not None and s["fill"] is not None for s in slots))
    scan = ring_lib.scan_rings(bpy.context)
    check("scan_rings", len(scan) >= 1 and scan[0]["color"] == "green",
          "n=" + str(len(scan)))
    ef = ring_lib.ring_pull(bpy.context, ring, slot=slots[0], start=100)
    check("ring_pull", ring.animation_data is not None and ef >= 138, str(ef))
    wef = ring_lib.ring_wiggle(bpy.context, [ring], start=140)
    check("ring_wiggle", wef == 156, str(wef))
    word = ring_lib.word_pop(bpy.context, "Nice!", "green", frame=150)
    check("word_pop", word is not None and word.data.body == "Nice!"
          and bpy.data.objects.get("UA_WordOutline") is not None)
    bpy.ops.object.select_all(action="DESELECT")
    ring.select_set(True)
    bpy.context.view_layer.objects.active = ring
    press = ring_lib.ring_tap(bpy.context, ring, 1.5, n=9)
    hand9 = bpy.data.objects.get("UA_Hand_9")
    check("ring_tap", press == 19 and hand9 is not None
          and hand9.animation_data is not None
          and bpy.data.objects.get("UA_TapRing_9") is not None,
          "press=" + str(press))
    ring_lib.slot_fill(bpy.context, slots[1], frame=160)
    fill = bpy.data.objects.get("UA_SlotFill_blue")
    check("slot_fill", fill is not None and fill.animation_data is not None)
    cluster = ring_lib.build_demo_cluster(bpy.context)
    check("cluster", len(cluster["rings"]) == 5 and len(cluster["clasps"]) == 5
          and cluster["hub"] is not None)
    scan2 = ring_lib.scan_rings(bpy.context)
    # 场景里可能残留之前模板构建的环，只统计本次演示簇成员
    in_cluster = sum(1 for r in scan2 if r["obj"] in cluster["rings"])
    check("scan_cluster", in_cluster == 5 and len(scan2) >= 6,
          f"cluster={in_cluster} total={len(scan2)}")
    check("level_coll_none",
          ring_lib.find_level_coll(bpy.context.scene) is None)

    # ---- 画质与风格 ----
    sc.uastudio.quality_level = "film"
    r = bpy.ops.ua.apply_quality()
    check("quality_film", r == {"FINISHED"}
          and sc.render.engine == "CYCLES", sc.render.engine)
    sc.uastudio.quality_level = "standard"
    bpy.ops.ua.apply_quality()
    check("quality_standard", sc.render.engine in ("BLENDER_EEVEE",
                                                   "BLENDER_EEVEE_NEXT"))
    r = bpy.ops.ua.color_style()
    check("color_style", r == {"FINISHED"})
    r = bpy.ops.ua.motion_blur(on=True)
    check("motion_blur", sc.render.use_motion_blur)
    bpy.ops.object.select_all(action="DESELECT")
    cam = sc.camera
    cam.select_set(True)
    bpy.context.view_layer.objects.active = cam
    r = bpy.ops.ua.dof_focus(disable=False)
    check("dof", r == {"FINISHED"} and cam.data.dof.use_dof)
    bpy.ops.ua.dof_focus(disable=True)
    sc.uastudio.bloom_on = True
    sc.uastudio.vignette_on = True
    r = bpy.ops.ua.setup_compositor()
    ng = sc.compositing_node_group
    check("compositor_group", r == {"FINISHED"} and ng is not None
          and len(ng.nodes) >= 2)
    sc.uastudio.bloom_on = False
    sc.uastudio.vignette_on = False
    sc.compositing_node_group = None  # 恢复无合成（渲染求值有崩溃风险）

    r = bpy.ops.ua.fx_particle(kind="dust")
    check("dust", any(o.name.startswith("UA_FX_dust")
                      for o in sc.objects))

    r = bpy.ops.ua.white_flash()
    check("white_flash", bpy.data.objects.get("UA_Flash") is not None)
    r = bpy.ops.ua.bubble()
    check("bubble", any(o.name.startswith("UA_Sticker")
                        for o in sc.objects))

    # ---- 优化：文案刷新 / 结尾卡单渲染兜底 / 依赖缓存 ----
    sc.uastudio.app_name = "新名字"
    r = bpy.ops.ua.template_refresh()
    end = bpy.data.scenes.get("Scene_Endcard")
    check("template_refresh", r == {"FINISHED"} and end is not None
          and any(o.name == "UA_CTAAppName" for o in end.objects))
    main.uastudio.out_dir = "/tmp/ua_render/m11_ec"
    main.uastudio.out_format = "png_seq"
    main.frame_end = 4
    from bl_ext.user_default.ua_game_kit.core import render_lib as _rl
    out = _rl.render_current(bpy.context, still=False, scene=end)
    check("endcard_fallback", "/m11_ec/" in out, out)
    from bl_ext.user_default.ua_game_kit.core import deps as _deps
    t0 = time.monotonic()
    for _i in range(50):
        _deps.scan()
    dt = time.monotonic() - t0
    check("deps_cache_fast", dt < 0.5, "50 scans " + str(round(dt, 3)) + "s")

    # ---- 节拍检测 / 换主色 / 交付包 ----
    import wave as _wave
    import struct as _struct
    _sr = 44100
    _frames = []
    for i in range(_sr * 2):
        t = i / _sr
        phase = t % 0.5
        v = (0.9 * math.sin(2 * math.pi * 220 * t) if phase < 0.1
             else 0.02 * math.sin(2 * math.pi * 220 * t))
        _frames.append(_struct.pack("<h", int(v * 32767)))
    w = _wave.open("/tmp/ua_render/test_beats.wav", "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(_sr)
    w.writeframes(b"".join(_frames))
    w.close()
    sc.uastudio.bgm_path = "/tmp/ua_render/test_beats.wav"
    r = bpy.ops.ua.bgm_beats(filepath=sc.uastudio.bgm_path)
    n_beats = len([m for m in sc.timeline_markers
                   if m.name.startswith("beat")])
    check("bgm_beats", r == {"FINISHED"} and n_beats >= 3,
          "beats=" + str(n_beats))
    sc.uastudio.mat_color = (0.1, 0.9, 0.4)
    bpy.ops.ua.add_shape(key="ball")
    bpy.ops.ua.apply_material(key="candy")
    r = bpy.ops.ua.template_recolor()
    mat = bpy.data.materials.get("UA_candy")
    col = next((n for n in mat.node_tree.nodes
                if n.bl_idname == "ShaderNodeBsdfPrincipled"), None)
    c_ok = col is not None and abs(col.inputs["Base Color"]
                                   .default_value[1] - 0.9) < 0.05
    check("template_recolor", r == {"FINISHED"} and c_ok)
    main.uastudio.out_dir = "/tmp/ua_render/m12_deliv"
    main.uastudio.out_format = "mp4"
    main.frame_end = 4
    end = bpy.data.scenes.get("Scene_Endcard")
    if end is not None:
        end.uastudio.out_dir = "/tmp/ua_render/m12_deliv"
        end.uastudio.out_format = "mp4"
    r = bpy.ops.ua.delivery_package()
    zips = []
    for d in ("/tmp/ua_render/m12_deliv", "/tmp/ua_render/m11_ec"):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if not f.endswith(".zip"):
                    continue
                if f in (".", "..") or "/" in f or "\\" in f or ".." in f:
                    continue
                zips.append(os.path.join(d, f))
    check("delivery_package", r == {"FINISHED"} and len(zips) >= 1,
          str(zips))

    print("=" * 50)
    if FAILS:
        print(f"SMOKE RESULT: {len(FAILS)} FAILED -> {FAILS}")
        sys.exit(1)
    print("SMOKE RESULT: ALL PASS")


main()
