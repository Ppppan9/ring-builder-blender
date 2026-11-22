"""Manual, frame-driven breakup of a selected ring."""

import math
import random

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import ring_sand_visual


_VISIBILITY = ("hide_render", "hide_viewport")
_FADE = '["rp_alpha"]'
_FALL_SECONDS = 0.85
_SAND_SECONDS = 3.0


def _curves(obj):
    anim = obj.animation_data
    if anim is not None and anim.action is not None and anim.action_slot is not None:
        for layer in anim.action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(anim.action_slot)
                if bag is not None:
                    yield bag.fcurves


def _check_visibility(obj):
    anim = obj.animation_data
    if anim is not None and (any(not track.mute for track in anim.nla_tracks)
                             or any(f.data_path in (*_VISIBILITY, _FADE) for f in anim.drivers)):
        raise ValueError(f"{obj.name} 有 NLA 动作或显隐驱动，暂不能自动接管破碎显隐")


def _make_action_local(obj):
    anim = obj.animation_data
    if anim is not None and anim.action is not None and anim.action.users > 1:
        slot_id = anim.action_slot.identifier if anim.action_slot else None
        anim.action = anim.action.copy()
        if slot_id is not None:
            anim.action_slot = next(s for s in anim.action.slots if s.identifier == slot_id)


def _set_hidden(obj, frame, hidden):
    for path in _VISIBILITY:
        setattr(obj, path, hidden)
        obj.keyframe_insert(data_path=path, frame=frame)
    for curves in _curves(obj):
        for curve in curves:
            if curve.data_path in _VISIBILITY:
                for key in curve.keyframe_points:
                    key.interpolation = "CONSTANT"


def _replace_fade(obj, frame):
    _make_action_local(obj)
    for curves in _curves(obj):
        for curve in tuple(curves):
            if curve.data_path in (*_VISIBILITY, _FADE):
                curves.remove(curve)
    obj["rp_alpha"] = 1.0
    _set_hidden(obj, frame - 1, False)
    _set_hidden(obj, frame, True)


def _sample_pose(context, ring, frame):
    scene = context.scene
    hide_curves = [curve for curves in _curves(ring) for curve in curves
                   if curve.data_path == "hide_viewport"]
    muted = [curve.mute for curve in hide_curves]
    hidden = ring.hide_viewport
    try:
        for curve in hide_curves:
            curve.mute = True
        ring.hide_viewport = False
        poses = []
        for f in (frame - 1, frame):
            scene.frame_set(f)
            poses.append(ring.evaluated_get(context.evaluated_depsgraph_get()).matrix_world.copy())
        return tuple(poses)
    finally:
        for curve, mute in zip(hide_curves, muted):
            curve.mute = mute
        ring.hide_viewport = hidden


def _fracture_meshes(module, level, ring, count):
    api = module.rp_scene
    asset_id = ring["rp_asset"]
    asset = module.rp_core.asset(asset_id)
    theme = api.THEME_OF_SKIN.get(level.get("skin"), "default")
    if asset.get("gem"):
        raise ValueError("手动破碎目前只支持普通 C 环和整环")
    layout = module.rp_core.shard_layout({"asset": asset_id}, count, False)["shards"]
    radius = 151.0
    tube = api.tube_px(theme)
    seeds = []
    for i, shard in enumerate(layout):
        a0, a1 = shard["a0"], shard["a1"]
        if asset["shape"] == "gap":
            gap = asset["gapAngle"]
            a0 = max(a0, gap + api.GAP_3D_DEG / 2)
            a1 = min(a1, gap + 360 - api.GAP_3D_DEG / 2)
        angle = math.radians(-(a0 + a1) / 2)
        r = radius + 0.28 * tube * math.sin(i * 2.4)
        z = tube * (1 + 0.42 * math.cos(i * 1.8))
        seeds.append(Vector((r * math.cos(angle), r * math.sin(angle), z)) * api.PX)
    mats = []
    for slot in ring.material_slots:
        mat = slot.material
        if mat is not None and mat.get("rp_fade"):
            mat = bpy.data.materials.get(mat.get("rp_base", "")) or mat
        mats.append(mat)
    cut = api.get_mat(theme, asset.get("color", "blue"), "cut")
    if not mats:
        mats.append(cut)
    cells = api.fracture_cells(ring.data, seeds, cut_mat_index=len(mats))
    meshes = []
    try:
        if len(cells) != count:
            raise RuntimeError("没有生成完整的碎片，请减少碎片数量再试")
        for i in range(count):
            bm = cells[i]
            center = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
            mesh = bpy.data.meshes.new("UA_RingShard")
            meshes.append((mesh, center))
            for mat in (*mats, cut):
                mesh.materials.append(mat)
            bm.to_mesh(mesh)
            mesh.transform(Matrix.Translation(-center))
    except Exception:
        for mesh, _center in meshes:
            bpy.data.meshes.remove(mesh)
        raise
    finally:
        for bm in cells.values():
            bm.free()
    return meshes


def _release_velocity(center, pose, gravity, spread):
    radial = pose.to_3x3() @ Vector((center.x, center.y, 0.0))
    down = gravity.normalized()
    vertical = radial.dot(down)
    lateral = radial - down * vertical
    return spread * (4.0 * lateral + down * (1.5 * max(0.0, vertical + 0.25 * radial.length)))


def _animate_fragment(obj, center, pose, prev, frame, release, gravity, fps, i, spread):
    start = pose @ center
    rotation = pose.to_quaternion()
    obj.scale = pose.to_scale()
    obj.rotation_mode = "QUATERNION"
    velocity = _release_velocity(center, pose, gravity, spread)
    if release == frame:
        velocity += (start - prev @ center) * fps
    obj["ua_fall_gravity"] = tuple(gravity)
    obj["ua_fall_fps"] = fps
    axis = Vector((math.sin(i * 2.4), math.cos(i * 2.4), 0.3)).normalized()
    spin = 1.5 + 0.45 * (i % 5)
    last = release + max(1, round(_FALL_SECONDS * fps))
    _set_hidden(obj, frame - 1, True)
    _set_hidden(obj, frame, False)
    for f in range(release, last + 1):
        t = (f - release) / fps
        obj.location = start + velocity * t + gravity * (0.5 * t * t)
        obj.rotation_quaternion = Quaternion(axis, spin * t) @ rotation
        for path in ("location", "rotation_quaternion"):
            obj.keyframe_insert(data_path=path, frame=f)
    for curves in _curves(obj):
        for curve in curves:
            if curve.data_path in ("location", "rotation_quaternion"):
                for key in curve.keyframe_points:
                    key.interpolation = "LINEAR"
    return last


def _keyed_components(obj, path, size):
    channels = {f.array_index: f for curves in _curves(obj) for f in curves
                if f.data_path == path}
    if set(channels) != set(range(size)):
        return None
    keys = [list(channels[i].keyframe_points) for i in range(size)]
    frames = [k.co.x for k in keys[0]]
    if not frames or any([k.co.x for k in axis] != frames for axis in keys[1:]):
        return None
    return frames, keys, list(channels.values())


def remap_fragments(scene, coll, transform):
    """Move existing breakup poses while keeping the original world-space gravity."""
    changes = []
    turn = transform.to_quaternion()
    rotation = transform.to_3x3()
    for obj in coll.all_objects:
        if not obj.get("ua_manual_shatter"):
            continue
        if obj.parent is not None or obj.constraints or obj.rotation_mode != "QUATERNION":
            raise ValueError("已有碎片被手动绑定，请先撤销绑定后再切换姿态")
        _check_visibility(obj)
        location = _keyed_components(obj, "location", 3)
        orientation = _keyed_components(obj, "rotation_quaternion", 4)
        if location is None or orientation is None or location[0] != orientation[0]:
            raise ValueError("已有碎片轨迹经过编辑，请先重新生成破碎，再切换姿态")
        fps = obj.get("ua_fall_fps", scene.render.fps / scene.render.fps_base)
        gravity = Vector(obj.get("ua_fall_gravity", scene.gravity))
        correction = gravity - rotation @ gravity
        frames, positions, _ = location
        release = obj["ua_release_frame"]
        values = []
        for index, frame in enumerate(frames):
            t = max(0.0, (frame - release) / fps)
            point = Vector([keys[index].co.y for keys in positions])
            quat = Quaternion([keys[index].co.y for keys in orientation[1]])
            values.append((transform @ point + correction * (0.5 * t * t), turn @ quat))
        changes.append((obj, values))

    for obj, values in changes:
        _make_action_local(obj)
        for i, (path, size) in enumerate((("location", 3), ("rotation_quaternion", 4))):
            _, keys, channels = _keyed_components(obj, path, size)
            for axis, axis_keys in enumerate(keys):
                for k, value in zip(axis_keys, values):
                    offset = value[i][axis] - k.co.y
                    k.co.y += offset
                    k.handle_left.y += offset
                    k.handle_right.y += offset
            for channel in channels:
                channel.update()


def _attachment_release(pose, obj, frame, duration, progressive, reverse, lo, hi):
    """扣件跟随所在弧段：逐段模式下随该段一起消失，而不是起始帧全部隐形。"""
    if not progressive:
        return frame
    local = pose.inverted() @ obj.matrix_world.translation
    a = lo + (-math.degrees(math.atan2(local.y, local.x)) - lo) % 360
    if a > hi:
        a = lo if 360 - (a - lo) < a - hi else hi
    t = (a - lo) / max(hi - lo, 1e-9)
    if reverse:
        t = 1.0 - t
    return frame + round(duration * t)


def _set_rigid_keys(obj, release, start):
    """Hold a grain frozen until the release frame, then let the simulation take over."""
    body = obj.rigid_body
    body.kinematic = True
    obj.keyframe_insert(data_path="rigid_body.kinematic", frame=start)
    body.kinematic = False
    obj.keyframe_insert(data_path="rigid_body.kinematic", frame=release)
    for curves in _curves(obj):
        for curve in curves:
            if curve.data_path == "rigid_body.kinematic":
                for key in curve.keyframe_points:
                    key.interpolation = "CONSTANT"


def _ring_materials(module, level, ring):
    theme = module.rp_scene.THEME_OF_SKIN.get(level.get("skin"), "default")
    mats = []
    for slot in ring.material_slots:
        mat = slot.material
        if mat is not None and mat.get("rp_fade"):
            mat = bpy.data.materials.get(mat.get("rp_base", "")) or mat
        mats.append(mat)
    cut = module.rp_scene.get_mat(theme, module.rp_core.asset(ring["rp_asset"]).get("color", "blue"), "cut")
    if not mats:
        mats.append(cut)
    return mats


def _remove_piece(obj):
    data = obj.data
    action = obj.animation_data.action if obj.animation_data else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if data.users == 0:
        materials = tuple(mat for mat in data.materials if mat is not None
                          and (data.get("ua_sand_volume_mesh") or mat.get("ua_sand_material")))
        bpy.data.meshes.remove(data)
        for mat in materials:
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)
    if action is not None and action.users == 0:
        bpy.data.actions.remove(action)


def _generated_pieces(coll, rid):
    return [obj for obj in coll.all_objects if obj.get("rp_ring") == rid
            and obj.get("rp_kind") == "shard"]


def _sand_section(coll, ring, mesh, pose, start, release, index):
    obj = bpy.data.objects.new(f"{ring.name}·实体弧段 {index + 1:02d}", mesh)
    coll.objects.link(obj)
    obj.matrix_world = pose
    obj["rp_kind"] = "shard"
    obj["rp_ring"] = ring["rp_id"]
    obj["ua_sand_section"] = index
    obj["ua_release_frame"] = release
    _set_hidden(obj, start - 1, True)
    _set_hidden(obj, start, False)
    _set_hidden(obj, release, True)
    return obj


def _bake_sand_world(context):
    from . import physics_lib

    physics_lib.ensure_world(context.scene)
    cache = context.scene.rigidbody_world.point_cache
    with context.temp_override(point_cache=cache):
        if cache.is_baked:
            bpy.ops.ptcache.free_bake()
        result = bpy.ops.ptcache.bake(bake=True)
    if "FINISHED" not in result or not cache.is_baked:
        raise RuntimeError("沙粒刚体缓存烘焙失败")


def add_sand(module, context, coll, level, ring, *, progressive):
    """Physics breakup: fine grains fall from the chosen frame and pile on the floor."""
    from . import physics_lib

    scene = context.scene
    settings = scene.rp_settings
    frame = scene.frame_current
    subframe = scene.frame_subframe
    if frame < scene.frame_start:
        raise ValueError("破碎帧不能早于场景起始帧")
    asset = module.rp_core.asset(ring["rp_asset"])
    if asset.get("gem"):
        raise ValueError("沙粒破碎目前只支持普通 C 环和整环")
    duration = settings.shatter_frames
    if progressive and asset.get("shape") != "gap":
        raise ValueError("沿 C 口逐段破碎只适用于 C 形环，整环请用整体破碎")
    fps = scene.render.fps / scene.render.fps_base
    gravity = Vector(scene.gravity)
    if gravity.length_squared < 1e-8:
        raise ValueError("场景重力为零，请先设置下落方向和重力")
    api = module.rp_scene
    theme = api.THEME_OF_SKIN.get(level.get("skin"), "default")
    count = settings.sand_count
    # Size the scatter to the ring rather than the canvas.
    speed = settings.shatter_spread * (151 * api.PX) * max(ring.scale) * 4.0
    rid = ring["rp_id"]
    objects = list(coll.all_objects)
    attachments = [o for o in objects if o.get("rp_ring") == rid
                   and o.get("rp_kind") in {"clasp", "acorn"}]
    for obj in (ring, *attachments):
        _check_visibility(obj)
    selected = tuple(obj for obj in context.selected_objects if obj.get("rp_kind") != "shard")
    active = context.view_layer.objects.active
    if active is not None and active.get("rp_kind") == "shard":
        active = None
    # 沙粒靠碰撞堆积，先确认有可见的地面作固定碰撞体。
    physics_lib.set_stage_passive(context, required=True)
    old_pieces = _generated_pieces(coll, rid)
    tube = api.tube_px(theme) * api.PX
    grain_radius = 0.145 * tube
    grain_material = None
    grain_meshes = []
    sections = []
    margin = max(0.00015, grain_radius * 0.12)
    # C 口范围内不撒沙粒；角度均匀分布并少量抖动。
    if asset.get("shape") == "gap":
        lo = asset["gapAngle"] + api.GAP_3D_DEG / 2
        hi = asset["gapAngle"] + 360 - api.GAP_3D_DEG / 2
    else:
        lo, hi = 0.0, 360.0
    rng = random.Random(97 + count)
    created = []
    dust_objs = []
    releases = []
    last_release = frame
    try:
        _prev, pose = _sample_pose(context, ring, frame)
        center_world = pose.translation
        grain_material = ring_sand_visual.grain_material(f"{ring.name}·细沙材质",
                                                         _ring_materials(module, level, ring))
        for variant in range(3):
            grain_meshes.append(ring_sand_visual.grain_mesh(f"{ring.name}·沙粒", grain_material,
                                                           grain_radius, variant))
        if progressive:
            section_count = min(14, settings.shatter_count, duration + 1)
            sections = _fracture_meshes(module, level, ring, section_count)
        else:
            section_count = 1
        for index in range(section_count):
            order = section_count - 1 - index if settings.shatter_reverse else index
            release = frame + round(duration * order / (section_count - 1)) if progressive else frame
            last_release = max(last_release, release)
            if progressive:
                mesh, center = sections[index]
                section_pose = pose @ Matrix.Translation(center)
                dust_objs.append(_sand_section(coll, ring, mesh, section_pose, frame, release, index))
            else:
                mesh, section_pose = ring.data, pose
            n = count // section_count + (index < count % section_count)
            for local in ring_sand_visual.sample_centers(mesh, n, rng, grain_radius,
                                                        cut_faces=progressive):
                i = len(created)
                obj = bpy.data.objects.new(f"{ring.name}·细沙 {i + 1:03d}", grain_meshes[i % 3])
                created.append(obj)
                releases.append(release)
                obj["rp_kind"] = "shard"
                obj["rp_ring"] = rid
                obj["ua_sand_shatter"] = True
                obj["ua_sand_source_section"] = index
                obj["ua_release_frame"] = release
                coll.objects.link(obj)
                size = 0.65 + 0.60 * rng.random()
                obj.matrix_world = section_pose @ Matrix.Translation(local) @ Matrix.Scale(size, 4)
        scene.frame_end = max(scene.frame_end, last_release + round(_SAND_SECONDS * fps))
        # 刚体要在显隐关键帧之前加：当前帧不可见的物体会被 rigidbody 操作跳过。
        physics_lib.add_rigid(context, created, "ACTIVE")
        for i, (obj, release) in enumerate(zip(created, releases)):
            body = obj.rigid_body
            body.collision_shape = "CONVEX_HULL"
            body.friction = 0.8
            body.linear_damping = 0.15
            body.use_margin = True
            body.collision_margin = margin
            radial = obj.matrix_world.translation - center_world
            flat = Vector((radial.x, radial.y, 0.0))
            direction = (flat.normalized() if flat.length_squared > 1e-12
                         else Vector((math.cos(i), math.sin(i), 0.0)))
            jitter = Vector((math.sin(i * 1.7), math.cos(i * 2.3), 0.0))
            velocity = speed * (direction + 0.3 * jitter)
            rest = obj.matrix_world.translation.copy()
            # Use the hidden pre-roll for scatter, not a visible jump away from the section.
            obj.location = rest
            obj.keyframe_insert(data_path="location", frame=release)
            obj.location = rest - velocity / fps if release > scene.frame_start else rest
            obj.keyframe_insert(data_path="location", frame=release - 1)
            for curves in _curves(obj):
                for curve in curves:
                    if curve.data_path == "location":
                        for key in curve.keyframe_points:
                            key.interpolation = "LINEAR"
            _set_rigid_keys(obj, release, scene.frame_start)
        for obj, release in zip(created, releases):
            _set_hidden(obj, release - 1, True)
            _set_hidden(obj, release, False)
        if settings.sand_dust:
            ring_sand_visual.add_dust(coll, ring, created, dust_objs, fps=fps,
                                      radius=tube * min(pose.to_scale()) * 0.48,
                                      set_hidden=_set_hidden)
        for obj in old_pieces:
            _remove_piece(obj)
        _bake_sand_world(context)
        _replace_fade(ring, frame)
        for obj in attachments:
            _replace_fade(obj, _attachment_release(pose, obj, frame,
                                                   duration, progressive,
                                                   settings.shatter_reverse, lo, hi))
    except Exception:
        for obj in [*dust_objs, *created]:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in [*grain_meshes, *(m for m, _ in sections)]:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        if grain_material is not None and grain_material.users == 0:
            bpy.data.materials.remove(grain_material)
        raise
    finally:
        scene.frame_set(frame, subframe=subframe)
        bpy.ops.object.select_all(action="DESELECT")
        layer = context.view_layer
        for obj in selected:
            if obj.visible_get(view_layer=layer):
                obj.select_set(True)
        layer.objects.active = active if active is not None and active.select_get() else None
    mode = "逐段撒落" if progressive else "整体散落"
    return {"ok": True, "msg": f"第 {frame} 帧开始{mode}，共 {count} 粒沙粒"}


def remap_sand(coll, transform):
    """Move sand grains' keyed rest pose with the level; the pile is re-simulated afterwards."""
    changes = []
    dust_changes = []
    section_changes = []
    rotation = transform.to_3x3()
    for obj in coll.all_objects:
        if "ua_sand_section" in obj:
            section_changes.append((obj, transform @ obj.matrix_world))
            continue
        if obj.get("ua_sand_dust"):
            if obj.get("ua_dust_source") is not None:
                # The new volume follows the remapped rigid grain automatically.
                continue
            if obj.parent is not None or obj.constraints:
                raise ValueError("已有沙尘被手动绑定，请先清除该环的沙粒再切换姿态")
            location = _keyed_components(obj, "location", 3)
            if location is None:
                raise ValueError("已有沙尘轨迹经过编辑，请先清除该环的沙粒再切换姿态")
            dust_changes.append((obj, location))
            continue
        if not obj.get("ua_sand_shatter"):
            continue
        if obj.parent is not None or obj.constraints:
            raise ValueError("已有沙粒被手动绑定，请先清除该环的沙粒再切换姿态")
        location = _keyed_components(obj, "location", 3)
        if location is None or len(location[0]) != 2:
            raise ValueError("已有沙粒轨迹经过编辑，请先清除该环的沙粒再切换姿态")
        changes.append((obj, location))
    for obj, pose in section_changes:
        obj.matrix_world = pose
    for obj, (frames, keys, channels) in changes:
        values = [transform @ Vector([keys[axis][index].co.y for axis in range(3)])
                  for index in range(len(frames))]
        for axis, axis_keys in enumerate(keys):
            for key, value in zip(axis_keys, values):
                key.co.y = value[axis]
        for channel in channels:
            channel.update()
    for obj, (frames, keys, channels) in dust_changes:
        fps = obj.get("ua_fall_fps", 24.0)
        gravity = Vector(obj.get("ua_fall_gravity", (0.0, 0.0, -9.8)))
        correction = gravity - rotation @ gravity
        release = obj["ua_release_frame"]
        values = []
        for index, f in enumerate(frames):
            t = max(0.0, (f - release) / fps)
            point = Vector([keys[axis][index].co.y for axis in range(3)])
            values.append(transform @ point + correction * (0.5 * t * t))
        for axis, axis_keys in enumerate(keys):
            for key, value in zip(axis_keys, values):
                key.co.y = value[axis]
                key.handle_left.y = value[axis]
                key.handle_right.y = value[axis]
        for channel in channels:
            channel.update()


def rebake_sand(context, coll):
    grains = [obj for obj in coll.all_objects if obj.get("ua_sand_shatter")]
    if not grains:
        return
    from . import physics_lib

    physics_lib.set_stage_passive(context, required=False)
    scene = context.scene
    frame, subframe = scene.frame_current, scene.frame_subframe
    try:
        _bake_sand_world(context)
    finally:
        scene.frame_set(frame, subframe=subframe)


def add(module, context, coll, level, ring, *, progressive):
    scene = context.scene
    settings = scene.rp_settings
    frame = scene.frame_current
    subframe = scene.frame_subframe
    if frame < scene.frame_start:
        raise ValueError("破碎帧不能早于场景起始帧")
    if progressive and module.rp_core.asset(ring["rp_asset"]).get("shape") != "gap":
        raise ValueError("沿 C 口逐段破碎只适用于 C 形环，整环请用整体破碎")
    count = settings.shatter_count
    duration = settings.shatter_frames
    if progressive and duration < count - 1:
        raise ValueError(f"传播时长至少需要 {count - 1} 帧，才能逐块脱落")
    fps = scene.render.fps / scene.render.fps_base
    gravity = Vector(scene.gravity)
    if gravity.length_squared < 1e-8:
        raise ValueError("场景重力为零，请先设置下落方向和重力")
    rid = ring["rp_id"]
    objects = list(coll.all_objects)
    attachments = [o for o in objects if o.get("rp_ring") == rid
                   and o.get("rp_kind") in {"clasp", "acorn"}]
    for obj in (ring, *attachments):
        _check_visibility(obj)
    old_pieces = _generated_pieces(coll, rid)
    meshes = _fracture_meshes(module, level, ring, count)
    created = []
    try:
        prev, pose = _sample_pose(context, ring, frame)
        last = frame
        for i, (mesh, center) in enumerate(meshes):
            order = count - 1 - i if settings.shatter_reverse else i
            release = frame + round(duration * order / (count - 1)) if progressive else frame
            obj = bpy.data.objects.new(f"{ring.name}·碎片 {i + 1:02d}", mesh)
            created.append(obj)
            obj["rp_kind"] = "shard"
            obj["rp_ring"] = rid
            obj["ua_manual_shatter"] = True
            obj["ua_release_frame"] = release
            coll.objects.link(obj)
            last = max(last, _animate_fragment(obj, center, pose, prev, frame,
                                               release, gravity, fps, i, settings.shatter_spread))
        asset = module.rp_core.asset(ring["rp_asset"])
        if asset.get("shape") == "gap":
            arc_lo = asset["gapAngle"] + module.rp_scene.GAP_3D_DEG / 2
            arc_hi = asset["gapAngle"] + 360 - module.rp_scene.GAP_3D_DEG / 2
        else:
            arc_lo, arc_hi = 0.0, 360.0
        _replace_fade(ring, frame)
        for obj in attachments:
            _replace_fade(obj, _attachment_release(pose, obj, frame, duration,
                                                   progressive, settings.shatter_reverse,
                                                   arc_lo, arc_hi))
        for obj in old_pieces:
            _remove_piece(obj)
        scene.frame_end = max(scene.frame_end, last)
    except Exception:
        for obj in created:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh, _center in meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
    finally:
        scene.frame_set(frame, subframe=subframe)
    return {"ok": True, "msg": f"第 {frame} 帧开始破碎，共 {count} 块"}
