"""Use the bundled level builder without registering its separate sidebar."""

import math

import bpy

_module = None


def _with_stage_cleanup(api, clear_generated):
    def clear_generated_level(scene=None):
        from . import ring_pose

        scene = scene or bpy.context.scene
        coll = api.get_coll(False, scene)
        rig = ring_pose.rig_for(coll) if coll is not None else None
        if rig is not None:
            ring_pose.require_single_scene(scene, coll)
            ring_pose.remove_scenery(scene, coll, rig)
        return clear_generated(scene)

    return clear_generated_level


def _auto_upright(api, scene):
    from . import ring_pose

    coll, level = api.stored_level(scene)
    if coll is not None and ring_pose.rig_for(coll) is None:
        ring_pose.toggle(bpy.context, coll, level, api.PX)


def _with_auto_upright(api, build_level):
    def build_level_upright(L, opts=None, scene=None):
        result = build_level(L, opts, scene)
        scene = scene or bpy.context.scene
        try:
            if scene.rp_settings.stage and scene == bpy.context.scene:
                _auto_upright(api, scene)
        except Exception:
            import traceback
            traceback.print_exc()
        return result

    return build_level_upright


class UA_RingSettings(bpy.types.PropertyGroup):
    stage: bpy.props.BoolProperty(
        name="导入后自动立起", default=True,
        description="导入或发送关卡后自动切换立式，并生成正视相机、水平地面、背景板和灯光；取消则保持俯拍平铺",
    )
    deps: bpy.props.EnumProperty(name="模式", items=(
        ("ONE", "仅此环", "只解选中的环"),
        ("DEPS", "含依赖", "先解开挡住它的环"),
    ))
    direction: bpy.props.EnumProperty(name="方向", items=(
        ("auto", "自动", "沿可行的最短方向旋转"),
        ("cw", "顺时针", "从上往下看顺时针旋转"),
        ("ccw", "逆时针", "从上往下看逆时针旋转"),
    ))
    sec_per_step: bpy.props.FloatProperty(name="每步时长（秒）", default=0.6,
                                         min=0.05, max=10.0)
    fx_move: bpy.props.BoolProperty(name="移出", default=True)
    fx_fade: bpy.props.BoolProperty(name="淡出", default=True)
    shatter_effect: bpy.props.EnumProperty(
        name="效果", items=(
            ("chunks", "碎块", "切成弧形碎块，可逐帧编辑下落轨迹"),
            ("sand", "沙粒", "物理模拟的细沙圆粒，落地自然堆积"),
        ))
    shatter_timing: bpy.props.EnumProperty(
        name="时序", items=(
            ("all", "整体", "所有碎块或沙粒在同一帧释放"),
            ("sweep", "逐段", "沿 C 口从一端开始逐段释放"),
        ))
    shatter_target: bpy.props.PointerProperty(
        name="指定环", type=bpy.types.Object,
        description="选填，留空时使用当前选中的环；可用来选择已淡出的原环",
        poll=lambda _settings, obj: obj.get("rp_kind") == "ring",
    )
    shatter_count: bpy.props.IntProperty(name="碎片数", default=12, min=3, max=32)
    shatter_spread: bpy.props.FloatProperty(
        name="散开幅度", default=1.0, min=0.0, max=3.0,
        description="碎片释放时的分离速度倍率；之后仅按重力下落",
    )
    shatter_frames: bpy.props.IntProperty(name="传播帧数", default=18, min=2, max=240,
                                          description="从第一块脱落到最后一块脱落的帧数")
    sand_count: bpy.props.IntProperty(
        name="沙粒数量", default=240, min=40, max=800,
        description="细小沙粒的颗粒数；越多越细腻，模拟越慢",
    )
    sand_dust: bpy.props.BoolProperty(
        name="叠加沙尘", default=True,
        description="沙粒散落时叠加一层细小的沙尘烟雾粒子（纯视觉，不参与碰撞）",
    )
    shatter_reverse: bpy.props.BoolProperty(name="从另一端开始", default=False)

    @property
    def fx_shatter(self):
        # The bundled browser bridge also reads this flag.
        return False


def register():
    global _module
    if hasattr(bpy.types.Scene, "rp_settings"):
        raise RuntimeError("请先停用旧版「解环关卡搭建器」，再启用合并版")
    from .. import ring_level_builder

    classes = (
        UA_RingSettings,
        ring_level_builder.RP_OT_open,
        ring_level_builder.RP_OT_stop,
        ring_level_builder.RP_OT_import,
    )
    registered = []
    try:
        for cls in classes:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.types.Scene.rp_settings = bpy.props.PointerProperty(type=classes[0])
    except Exception:
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        raise
    api = ring_level_builder.rp_scene
    clear_generated = api.clear_generated
    build_level = api.build_level
    # JSON import and browser Send both go through the vendor's cleanup and build.
    api.clear_generated = _with_stage_cleanup(api, clear_generated)
    api.build_level = _with_auto_upright(api, build_level)
    _module = ring_level_builder, classes, clear_generated, build_level


def unregister():
    global _module
    module, classes, clear_generated, build_level = _module
    module.stop_server()
    module.rp_scene.clear_generated = clear_generated
    module.rp_scene.build_level = build_level
    del bpy.types.Scene.rp_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _module = None


def connection_active():
    return _module[0].rp_server.running()


def level_collection(scene):
    coll = _module[0].rp_scene.get_coll(False, scene)
    return coll if coll is not None and coll.get("rp_level") else None


def _level(scene):
    try:
        coll, level = _module[0].rp_scene.stored_level(scene)
    except ValueError as exc:
        raise ValueError("关卡数据无法读取，请重新导入") from exc
    if coll is None:
        raise ValueError("请先从搭建器发送关卡，或导入关卡 JSON")
    return coll, level


def _params(scene):
    params = _module[0].unlock_params(scene.rp_settings)
    params["shatter"] = False
    return params


def unlock_selected(context):
    _level(context.scene)
    api = _module[0].rp_scene
    ids = api.selected_ring_ids(context)
    if not ids:
        raise ValueError("请先选中关卡里的环或卡扣")
    return api.apply_unlock(context.scene, ids, _params(context.scene))


def bake(scene):
    module = _module[0]
    coll, level = _level(scene)
    params = _params(scene)
    fps = scene.render.fps / scene.render.fps_base
    plan = module.rp_core.bake_timeline(dict(level, fps=fps), params,
                                      start=scene.frame_start / fps)
    if not plan["ok"] or not plan["seq"]:
        raise ValueError(plan.get("error") or "关卡中没有可烘焙的环")
    # 原搭建器先清动画再求解；先验证关卡，避免失败时丢掉已有关键帧。
    if set(r["id"] for r in level["rings"]) - module.rp_scene.ring_objects(coll).keys():
        raise ValueError("场景中的环与关卡数据不一致，请重新导入")
    return module.rp_scene.bake_level(scene, params)


def clear(scene):
    coll, _level_data = _level(scene)
    result = _module[0].rp_scene.clear_unlock(scene)
    if result["ok"]:
        coll.pop("rp_baked", None)
        scene.frame_set(scene.frame_current)
    return result


def _shatter_target(context):
    module = _module[0]
    coll, level = _level(context.scene)
    if context.mode != "OBJECT":
        raise ValueError("请切回物体模式再添加破碎动画")
    rings = module.rp_scene.ring_objects(coll)
    target = context.scene.rp_settings.shatter_target
    if target is not None:
        if rings.get(target.get("rp_id")) != target:
            raise ValueError("指定环不属于当前关卡")
    else:
        ids = module.rp_scene.selected_ring_ids(context)
        if len(ids) != 1 or ids[0] not in rings:
            raise ValueError("请只选中一个关卡环，或使用「指定环」选择已淡出的原环")
        target = rings[ids[0]]
    return module, coll, level, target


def shatter(context):
    from . import ring_shatter

    module, coll, level, target = _shatter_target(context)
    settings = context.scene.rp_settings
    progressive = settings.shatter_timing == "sweep"
    if settings.shatter_effect == "sand":
        return ring_shatter.add_sand(module, context, coll, level, target,
                                     progressive=progressive)
    return ring_shatter.add(module, context, coll, level, target, progressive=progressive)


def toggle_pose(context):
    from . import ring_pose

    coll, level = _level(context.scene)
    return ring_pose.toggle(context, coll, level, _module[0].rp_scene.PX)


def is_upright(coll):
    from . import ring_pose

    return coll is not None and ring_pose.rig_for(coll) is not None


def refit_upright_camera(scene):
    from . import ring_pose

    coll = level_collection(scene)
    rig = ring_pose.rig_for(coll) if coll is not None else None
    if rig is None:
        return
    camera = rig.get("ua_camera")
    if (camera is None or camera != scene.camera or camera.data.type != "ORTHO"
            or camera.data.animation_data is not None):
        return
    _, level = _level(scene)
    px = _module[0].rp_scene.PX
    width, height = float(level["width"]) * px, float(level["height"]) * px
    ring_pose.fit_camera(scene, camera.data, width, height + max(width, height) * 0.34)


def refresh_upright_stage(context, kind):
    from . import ring_pose, ring_stage

    coll = level_collection(context.scene)
    rig = ring_pose.rig_for(coll) if coll is not None else None
    if rig is None:
        return False
    _, level = _level(context.scene)
    px = _module[0].rp_scene.PX
    width, height = float(level["width"]) * px, float(level["height"]) * px
    fallback_z = rig.location.z - height / 2 - max(width, height) * 0.34
    ring_stage.refresh(context, coll, rig, width, height,
                       rig.get("ua_upright_floor_z", fallback_z), kind=kind)
    return True


def animation_end_frame(scene):
    coll = level_collection(scene)
    if coll is None or not coll.get("rp_unlock_end"):
        return None
    return math.ceil(coll["rp_unlock_end"] * scene.render.fps / scene.render.fps_base)
