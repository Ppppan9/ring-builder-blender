"""🎯 解环玩法库：C 环生成 / 花心与立方体基座 / 顶部颜色槽 / 拔环表演动作。

双层设计，两种来源通吃：
1. 免搭建器快速出片 —— build_demo_cluster() 一键生成「花心 C 环簇 + 卡扣 + 顶部颜色槽」；
2. 桥接 ring_level_builder 插件 —— 关卡搭建器发送到 Blender 的关卡对象
   （集合属性 rp_tag == "ring_level_builder"、对象自定义属性 rp_kind/rp_id/rp_asset）
   用 scan_rings() 扫出来后逐环调 ring_pull() 编排表演，模型零重建。

表演动作（买量表演层，模型层交给搭建器插件）：
- ring_pull(obj, slot)  拔出大回弹（外弹+挤压）→ 弧线飞向顶部颜色槽 → 缩入落槽
- ring_wiggle(objs)     邻环连锁轻晃（拔环前的预备动作）
- word_pop("Nice!")     感叹词戳（彩色描边弹入弹出）
- slot_fill(slot)       颜色槽填充闪光
- confetti()            彩带（转 physics_lib 粒子）

典型编排（15 秒）：
    cluster = ring_lib.build_demo_cluster(context)
    slots = ring_lib.make_slot_row(context, ("green", "blue", "purple"))
    scene.frame_set(95); util.select_only(context, [cluster["rings"][0]])
    game_fx_lib.hand_tap(context)
    ring_lib.ring_pull(context, cluster["rings"][0], slot=slots[0])
    ring_lib.word_pop(context, "Nice!", "green")
"""

from __future__ import annotations

import math
import re

import bmesh
import bpy
from mathutils import Vector

from . import anim_lib, candy_render, game_fx_lib, physics_lib, util

# ---------------------------------------------------------------------------
# 配色（与关卡搭建器 v1.7.0 素材色一致，sRGB hex）
# ---------------------------------------------------------------------------

RING_HEX = {
    "red": "dc3247",
    "orange": "ec8a23",
    "green": "24b24a",
    "blue": "3a6fde",
    "cyan": "33a9e0",
    "purple": "8c45dc",
    "silver": "c8ccd2",
}
CREAM_HEX = "f2eadd"          # 立方体基座奶油色

DEFAULT_GAP_DEG = 58.0        # C 环缺口角（搭建器 GAP_3D_DEG 同款）
COLL_NAME = "UA_解环"


def _lin(hexstr: str) -> tuple[float, float, float]:
    """sRGB hex → 线性 RGB。"""
    def f(x: float) -> float:
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return tuple(f(int(hexstr[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


_MAT_CACHE: dict[str, bpy.types.Material] = {}


def ring_material(color: str) -> bpy.types.Material:
    """环/槽/感叹词共用材质：糖果材质（kit 已验证的亮面配方），按色名缓存。"""
    mat = _MAT_CACHE.get(color)
    if mat is not None and mat.name in bpy.data.materials:
        return mat
    hexc = RING_HEX.get(color, CREAM_HEX)
    rgb = _lin(hexc)
    if color == "silver":
        mat = candy_render.make_candy_material("Ring_silver", rgb, roughness=0.15, sss=0.0)
    elif color == "cream":
        mat = candy_render.make_candy_material("Ring_cream", rgb, roughness=0.30, sss=0.05)
    else:
        mat = candy_render.make_candy_material("Ring_" + color, rgb)
    _MAT_CACHE[color] = mat
    return mat


def _flat_material(name: str, rgb, emission: float = 0.0) -> bpy.types.Material:
    """纯色材质（感叹词/槽洞用）。"""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (60, 0)
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.4
    emit = next((nm for nm in ("Emission Color", "Emission") if nm in bsdf.inputs), None)
    if emit:
        bsdf.inputs[emit].default_value = (*rgb, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission
    tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------------------
# C 环网格（圆管 + 半球圆头，缺口朝局部 +Y；原点 = 环心平面）
# ---------------------------------------------------------------------------

_RING_MESH_CACHE: dict[tuple, bpy.types.Mesh] = {}


def _c_ring_mesh(name: str, radius: float, tube: float, gap_deg: float) -> bpy.types.Mesh:
    key = (round(radius, 4), round(tube, 4), round(gap_deg, 2))
    me = _RING_MESH_CACHE.get(key)
    if me is not None:
        return me
    a0, arc = 90.0 + gap_deg / 2.0, 360.0 - gap_deg
    n = max(24, int(arc / 6))
    m, k = 20, 6
    bm = bmesh.new()

    def vert(co) -> "bmesh.types.BMVert":
        return bm.verts.new(co)

    rings = []
    for i in range(n + 1):
        u = math.radians(a0 + arc * i / n)
        loop = []
        for j in range(m):
            v = j / m * 2 * math.pi
            rad = radius + tube * math.cos(v)
            loop.append(vert((rad * math.cos(u), rad * math.sin(u), tube * math.sin(v))))
        rings.append(loop)
    for i in range(n):
        a, b = rings[i], rings[i + 1]
        for j in range(m):
            bm.faces.new((a[j], a[(j + 1) % m], b[(j + 1) % m], b[j]))

    def cap(loop, u, sign: int) -> None:
        """半球圆头：sign=-1 起始端 / +1 末端，沿切线方向鼓出。"""
        c = Vector((radius * math.cos(u), radius * math.sin(u), 0.0))
        rad_d = Vector((math.cos(u), math.sin(u), 0.0))
        tan_d = Vector((-math.sin(u), math.cos(u), 0.0)) * sign
        up = Vector((0, 0, 1))
        prev = loop
        for step in range(1, k):
            w = math.pi / 2 * step / k
            cur = []
            for j in range(m):
                v = j / m * 2 * math.pi
                d = (rad_d * math.cos(v) + up * math.sin(v)) * math.cos(w) + tan_d * math.sin(w)
                cur.append(vert(c + d * tube))
            for j in range(m):
                q = (prev[j], prev[(j + 1) % m], cur[(j + 1) % m], cur[j])
                bm.faces.new(q if sign > 0 else tuple(reversed(q)))
            prev = cur
        pole = vert(c + tan_d * tube)
        for j in range(m):
            t = (prev[j], prev[(j + 1) % m], pole)
            bm.faces.new(t if sign > 0 else tuple(reversed(t)))

    cap(rings[0], math.radians(a0), -1)
    cap(rings[-1], math.radians(a0 + arc), +1)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    _RING_MESH_CACHE[key] = me
    return me


def make_c_ring(context, color: str = "green", radius: float = 0.34,
                tube: float | None = None, gap_deg: float = DEFAULT_GAP_DEG,
                name: str = "UA_Ring") -> bpy.types.Object:
    """生成 C 环（缺口朝局部 +Y），糖果材质，自动放进「UA_解环」集合。"""
    tube = tube if tube is not None else radius * 0.17
    me = _c_ring_mesh("UA_RingMesh_%s_r%.2f" % (color, radius), radius, tube, gap_deg)
    obj = bpy.data.objects.new(name, me)
    util.ensure_collection(context, COLL_NAME).objects.link(obj)
    if not me.materials:
        me.materials.append(ring_material(color))
    obj.material_slots[0].link = "OBJECT"
    obj.material_slots[0].material = ring_material(color)
    obj.location = (0.0, 0.0, tube)
    obj["rp_kind"] = "ring"
    obj["ua_color"] = color
    return obj


def make_clasp(context, color: str = "silver", tube: float = 0.06,
               name: str = "UA_Clasp") -> bpy.types.Object:
    """卡扣箍：套在环管上的短圆柱（轴向 X = 环切线方向）。"""
    bpy.ops.mesh.primitive_cylinder_add(
        radius=tube * 1.24, depth=tube * 1.9, vertices=32,
        rotation=(0.0, math.radians(90.0), 0.0), location=(0.0, 0.0, tube))
    obj = context.active_object
    obj.name = name
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(ring_material(color))
    obj["rp_kind"] = "clasp"
    util.move_to_collection(obj, util.ensure_collection(context, COLL_NAME))
    return obj


def make_hub(context, style: str = "ring", color: str = "red",
             base_z: float = 0.0) -> bpy.types.Object:
    """基座：style="ring" = 花心大 C 环；"cube" = 奶油圆角立方体。base_z = 底座顶面高度。"""
    if style == "cube":
        size = 2.2
        bpy.ops.mesh.primitive_cube_add(size=size,
                                        location=(0.0, 0.0, base_z + size * 0.36))
        obj = context.active_object
        obj.name = "UA_Hub_Cube"
        bev = obj.modifiers.new("圆角", "BEVEL")
        bev.width = 0.13
        bev.segments = 5
        obj.data.materials.append(ring_material("cream"))
        obj["rp_kind"] = "prop"
        util.move_to_collection(obj, util.ensure_collection(context, COLL_NAME))
        return obj
    hub = make_c_ring(context, color=color, radius=0.5,
                      tube=0.5 * 0.17, name="UA_Hub_Ring")
    hub.location.z = base_z + 0.5 * 0.17
    hub["rp_kind"] = "prop"       # 花心不可拔
    return hub


def make_slot(context, color: str, location) -> dict:
    """顶部颜色槽：彩色环座 + 深色洞 + 可填充圆片。返回槽字典。"""
    x, y, z = location
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.13, minor_radius=0.05, location=(x, y, z))
    ring = context.active_object
    ring.name = "UA_Slot_" + color
    ring.data.materials.append(ring_material(color))
    for poly in ring.data.polygons:
        poly.use_smooth = True

    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.10, depth=0.012, location=(x, y, z - 0.02))
    hole = context.active_object
    hole.name = "UA_SlotHole_" + color
    hole.data.materials.append(_flat_material(
        "UA_SlotHole_dark", (0.06, 0.07, 0.08), emission=0.15))

    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.095, depth=0.02, location=(x, y, z - 0.01))
    fill = context.active_object
    fill.name = "UA_SlotFill_" + color
    fill.data.materials.append(ring_material(color))
    fill.scale = (0.01, 0.01, 0.01)       # 等待 slot_fill 弹出

    coll = util.ensure_collection(context, COLL_NAME)
    for ob in (ring, hole, fill):
        util.move_to_collection(ob, coll)
    return {"obj": ring, "hole": hole, "fill": fill, "color": color}


def make_slot_row(context, colors=("green", "blue", "purple"),
                  y: float = 1.30, spacing: float = 0.46,
                  z: float = 0.02) -> list[dict]:
    """一排顶部颜色槽（水平居中）。z = 底座顶面高度 + 0.02。"""
    n = len(colors)
    x0 = -(n - 1) * spacing / 2.0
    return [make_slot(context, c, (x0 + i * spacing, y, z))
            for i, c in enumerate(colors)]


# ---------------------------------------------------------------------------
# 免搭建器演示簇：花心 + 放射 C 环 + 卡扣
# ---------------------------------------------------------------------------


def build_demo_cluster(context, colors=("green", "blue", "purple", "orange", "cyan"),
                       ring_radius: float = 0.42,
                       base_z: float | None = None) -> dict:
    """一键解环画面：花心大 C 环 + N 个放射 C 环（缺口朝外）+ 银色卡扣。

    base_z 缺省自动取展台顶面高度（UA_Stage_Podium），环簇落在展台上。
    返回 {"hub", "rings", "clasps", "base_z"}。
    """
    if base_z is None:
        podium = bpy.data.objects.get("UA_Stage_Podium")
        base_z = (podium.location.z + podium.dimensions.z * 0.5) if podium else 0.0
    hub = make_hub(context, style="ring", base_z=base_z)
    tube_h = 0.5 * 0.17
    tube_r = ring_radius * 0.17
    rings, clasps = [], []
    n = len(colors)
    dist = 0.5 + ring_radius + 0.06
    for i, color in enumerate(colors):
        th = math.radians(90.0 + i * 360.0 / n)
        pos = Vector((dist * math.cos(th), dist * math.sin(th), 0.0))
        ring = make_c_ring(context, color=color, radius=ring_radius,
                           name="UA_Ring_%d_%s" % (i + 1, color))
        ring.location = (pos.x, pos.y, base_z + tube_r)   # 环心平面 = 管半径，底面贴座
        ring.rotation_euler = (0.0, 0.0, th - math.pi / 2)   # 缺口朝外
        rings.append(ring)
        clasp = make_clasp(context, name="UA_Clasp_%d" % (i + 1))
        clasp_dist = 0.5 + tube_h + 0.05
        clasp.location = (clasp_dist * math.cos(th),
                          clasp_dist * math.sin(th),
                          base_z + (tube_h + tube_r) * 0.5)
        clasp.rotation_euler = (0.0, 0.0, th + math.pi / 2)  # X 轴沿切线
        clasps.append(clasp)
    # 父级化前刷新依赖图，避免读到 stale matrix_world（新建对象的经典坑）
    context.view_layer.update()
    for ring, clasp in zip(rings, clasps):
        mw = clasp.matrix_world.copy()
        clasp.parent = ring
        clasp.matrix_parent_inverse = ring.matrix_world.inverted() @ mw
        clasp.matrix_world = mw
    return {"hub": hub, "rings": rings, "clasps": clasps, "base_z": base_z}


# ---------------------------------------------------------------------------
# 桥接关卡搭建器（ring_level_builder v1.7.0）
# ---------------------------------------------------------------------------

_COLOR_RE = re.compile(r"_(red|orange|green|blue|cyan|purple|silver)$")


def find_level_coll(scene=None) -> bpy.types.Collection | None:
    """找关卡搭建器生成的集合（rp_tag == "ring_level_builder"）。"""
    scene = scene or bpy.context.scene
    for coll in scene.collection.children_recursive:
        if coll.get("rp_tag") == "ring_level_builder":
            return coll
    return None


def _obj_color(obj) -> str:
    """对象颜色：优先 ua_color（本库生成），否则从 rp_asset 尾色解析（搭建器生成）。"""
    c = obj.get("ua_color")
    if c:
        return c
    m = _COLOR_RE.search(obj.get("rp_asset") or "")
    return m.group(1) if m else "blue"


def scan_rings(context) -> list[dict]:
    """扫描场景里全部解环对象（搭建器关卡 + 本库演示簇统一识别）。

    返回 [{"obj", "id", "name", "color"}]，按名称排序。
    """
    out = []
    for obj in context.scene.objects:
        if obj.get("rp_kind") != "ring":
            continue
        out.append({
            "obj": obj,
            "id": obj.get("rp_id") or obj.name,
            "name": obj.name,
            "color": _obj_color(obj),
        })
    out.sort(key=lambda r: r["name"])
    return out


def _cluster_center(context, exclude=None) -> Vector:
    """环簇中心（拔出方向的参考点）：全部环对象位置的均值。"""
    pts = [r["obj"].location for r in scan_rings(context)
           if r["obj"] is not exclude]
    if not pts:
        return Vector((0.0, 0.0, 0.0))
    return sum(pts, Vector()) / len(pts)


# ---------------------------------------------------------------------------
# 表演动作
# ---------------------------------------------------------------------------

_TAP_MAT = "UA_ClickRing"


def _tap_material() -> bpy.types.Material:
    """点击波纹共用自发光材质。"""
    mat = bpy.data.materials.get(_TAP_MAT)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(_TAP_MAT)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.location = (60, 0)
    emit.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emit.inputs["Strength"].default_value = 2.0
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def ring_tap(context, target, scale: float = 1.5, n: int = 1) -> int:
    """解环专用单次点击：独立手指对象（UA_Hand_n），多段点击互不覆盖关键帧。

    （game_fx_lib.hand_tap 复用同一 UA_Hand 且每次清空动画，只留最后一段。）
    手指飞入 → 按压（目标同步回弹）→ 停在目标上，带波纹；只在点击时段现身。
    调用前先 util.select_only() 选中目标。返回按压帧（拔环动画从这里起步）。
    """
    scene = context.scene
    fps = anim_lib._f()
    f0 = max(scene.frame_start, scene.frame_current)
    name = "UA_Hand_%d" % n
    old = util.find_object(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    hand = game_fx_lib.make_hand(context, scale)     # 依赖当前选中目标
    hand.name = name
    coll = util.ensure_collection(context, COLL_NAME)
    util.move_to_collection(hand, coll)

    top = Vector(target.location) + Vector(
        (0.0, 0.0, target.dimensions.z * 0.5 + 0.05))
    _cam_loc, fwd, right, up = game_fx_lib._cam_vectors(context)
    start = top + right * 1.2 + up * 0.5    # 远景机位下飞入起点压低，避免出画
    press_f = f0 + round(0.6 * fps)
    press = top + Vector((0.0, 0.0, -0.08))

    st = tuple(hand.location)
    anim_lib._kf(hand, "location",
                 [st, tuple(start), tuple(press), tuple(top)],
                 [f0, f0 + round(0.35 * fps), press_f,
                  f0 + round(0.8 * fps)], interp="SINE")
    for attr in ("hide_render", "hide_viewport"):
        setattr(hand, attr, True)
        hand.keyframe_insert(data_path=attr, frame=max(1, f0 - 1))
        setattr(hand, attr, False)
        hand.keyframe_insert(data_path=attr, frame=f0)
        setattr(hand, attr, True)
        hand.keyframe_insert(data_path=attr, frame=f0 + round(1.1 * fps))

    # 目标按压回弹
    ts = tuple(target.scale)
    target.scale = tuple(c * 0.85 for c in ts)
    target.keyframe_insert(data_path="scale", frame=press_f)
    target.scale = ts
    target.keyframe_insert(data_path="scale", frame=f0 + round(0.85 * fps))
    anim_lib._set_all_interp(target, "scale", "BACK")

    # 点击波纹（独立命名，不互相覆盖）
    ripple_name = "UA_TapRing_%d" % n
    old_ring = util.find_object(ripple_name)
    if old_ring is not None:
        bpy.data.objects.remove(old_ring, do_unlink=True)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.18, minor_radius=0.02,
        align="WORLD", location=top + fwd * 0.02)
    ripple = context.active_object
    ripple.name = ripple_name
    ripple.rotation_euler = target.rotation_euler
    ripple.data.materials.append(_tap_material())
    ripple.scale = (0.001, 0.001, 0.001)
    anim_lib._kf(ripple, "scale",
                 [(0.001,) * 3, (1.6, 1.6, 1.6), (0.001,) * 3],
                 [press_f, f0 + round(1.0 * fps), f0 + round(1.45 * fps)],
                 interp="SINE")
    for attr in ("hide_render", "hide_viewport"):
        setattr(ripple, attr, True)
        ripple.keyframe_insert(data_path=attr, frame=1)
        setattr(ripple, attr, False)
        ripple.keyframe_insert(data_path=attr, frame=press_f)
        setattr(ripple, attr, True)
        ripple.keyframe_insert(data_path=attr, frame=f0 + round(1.5 * fps))
    util.move_to_collection(ripple, coll)
    return press_f


def ring_pull(context, obj: bpy.types.Object, slot: dict | None = None,
              start: int | None = None) -> int:
    """拔环表演：外弹回缩（挤压感）→ 弧线飞向颜色槽（无槽则飞出画面）→ 缩入落槽。

    会清掉该环已有动画（避免与搭建器烘焙的解环关键帧叠加）。返回结束帧。
    """
    scene = context.scene
    fps = anim_lib._f()
    f0 = start if start is not None else max(scene.frame_start, scene.frame_current)
    loc0 = tuple(obj.location)
    rot0 = tuple(obj.rotation_euler)
    scale0 = tuple(obj.scale)
    obj.animation_data_clear()

    center = _cluster_center(context, exclude=obj)
    out = Vector((loc0[0] - center.x, loc0[1] - center.y, 0.0))
    if out.length < 1e-6:
        out = Vector((0.0, -1.0, 0.0))
    out.normalize()
    dim = max(obj.dimensions.x, obj.dimensions.y, 0.05)
    dist = max(0.08, dim * 0.45)

    fp = f0 + round(0.30 * fps)        # 拔出到最外
    fb = f0 + round(0.48 * fps)        # 回缩定位
    fm = f0 + round(0.80 * fps)        # 飞行弧顶
    fe = f0 + round(1.25 * fps)        # 落槽/出画

    loc_pop = Vector(loc0) + out * dist
    if slot is not None:
        dest = Vector(slot["obj"].location) + Vector((0.0, 0.0, 0.03))
        s_end = 0.22 / dim
    else:
        dest = loc_pop + out * dist * 2.2 + Vector((0.0, 0.0, 0.9))
        s_end = scale0[0] * 0.7
    mid = (Vector(loc_pop) + dest) * 0.5 + Vector((0.0, 0.0, 0.45))

    anim_lib._kf(obj, "location",
                 [loc0, tuple(loc_pop), tuple(loc_pop), tuple(mid), tuple(dest)],
                 [f0, fp, fb, fm, fe], interp="SINE")
    anim_lib._kf(obj, "scale",
                 [scale0, tuple(c * 1.15 for c in scale0), scale0,
                  tuple(c * 0.9 for c in scale0), (s_end, s_end, s_end)],
                 [f0, fp, fb, fm, fe], interp="BACK")
    rz0 = rot0[2]
    anim_lib._kf(obj, "rotation_euler",
                 [rot0, (rot0[0], rot0[1], rz0 + math.radians(14)),
                  (rot0[0], rot0[1], rz0 + math.radians(14)),
                  (rot0[0], rot0[1], rz0 + math.radians(80)),
                  (rot0[0], rot0[1], rz0 + math.radians(170))],
                 [f0, fp, fb, fm, fe], interp="SINE")
    return fe


def ring_wiggle(context, objs, start: int | None = None,
                amp_deg: float = 5.0) -> int:
    """邻环连锁轻晃（拔环前的预备动作），16 帧摆 3 次。返回结束帧。"""
    scene = context.scene
    f0 = start if start is not None else max(scene.frame_start, scene.frame_current)
    a = math.radians(amp_deg)
    for obj in objs:
        z0 = obj.rotation_euler[2]
        seq = [z0, z0 + a, z0 - a * 0.7, z0 + a * 0.4, z0]
        frames = [f0, f0 + 4, f0 + 8, f0 + 12, f0 + 16]
        for v, fr in zip(seq, frames):
            obj.rotation_euler = (obj.rotation_euler[0],
                                  obj.rotation_euler[1], v)
            obj.keyframe_insert(data_path="rotation_euler", frame=fr, index=2)
        anim_lib._set_all_interp(obj, "rotation_euler", "SINE")
    return f0 + 16


def _pop_keys(obj, f0: int, hold: int) -> None:
    """弹入 → 停留 → 缩出 的通用缩放关键帧。"""
    anim_lib._kf(obj, "scale",
                 [(0.01, 0.01, 0.01), (1.22, 1.22, 1.22), (1.0, 1.0, 1.0),
                  (1.0, 1.0, 1.0), (0.01, 0.01, 0.01)],
                 [f0, f0 + 5, f0 + 9, f0 + hold, f0 + hold + 5], interp="BACK")


def word_pop(context, text: str, color: str = "green", location=None,
             frame: int | None = None, size: float = 1.0) -> bpy.types.Object:
    """感叹词戳（Nice! / Great! / Excellent!）：彩色字身 + 白描边，弹入弹出。

    默认位置画面中上、朝向主相机。返回字身对象。
    """
    scene = context.scene
    fps = anim_lib._f()
    f0 = frame if frame is not None else max(scene.frame_start, scene.frame_current)
    loc = Vector(location) if location is not None else Vector((0.0, 0.35, 0.55))
    rgb = _lin(RING_HEX.get(color, RING_HEX["green"]))

    def _font(name: str, sz: float, mat) -> bpy.types.Object:
        cu = bpy.data.curves.new(name, type="FONT")
        cu.body = text
        cu.size = sz
        cu.extrude = 0.015
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        obj = bpy.data.objects.new(name, cu)
        obj.data.materials.append(mat)
        obj.rotation_euler = (math.radians(60.0), 0.0, 0.0)
        util.ensure_collection(context, COLL_NAME).objects.link(obj)
        return obj

    body = _font("UA_WordBody", 0.34 * size,
                 _flat_material("UA_Word_" + color, rgb, emission=0.5))
    outline = _font("UA_WordOutline", 0.38 * size,
                    _flat_material("UA_WordOutline", (0.97, 0.97, 0.95),
                                   emission=1.0))
    body.location = loc
    # 白描边沿相机视线向前垫底（低机位下 z 直移会漂出字面）
    cam = scene.camera
    if cam is not None:
        fwd = cam.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))
        outline.location = loc + fwd * 0.045
    else:
        outline.location = loc + Vector((0.0, 0.0, -0.03))
    hold = round(0.75 * fps)
    _pop_keys(body, f0, hold)
    _pop_keys(outline, f0, hold)
    return body


def slot_fill(context, slot: dict, frame: int | None = None) -> int:
    """颜色槽填充：圆片弹出 + 环座脉冲。返回结束帧。"""
    scene = context.scene
    f0 = frame if frame is not None else max(scene.frame_start, scene.frame_current)
    _pop_keys(slot["fill"], f0, round(0.75 * anim_lib._f()))
    anim_lib._kf(slot["obj"], "scale",
                 [(1.0, 1.0, 1.0), (1.18, 1.18, 1.18), (1.0, 1.0, 1.0)],
                 [f0, f0 + 4, f0 + 8], interp="SINE")
    return f0 + 9


def confetti(context, count: int = 70, start_frame: int | None = None) -> int:
    """彩带庆祝（转 physics_lib 粒子）。返回发射器数。"""
    return physics_lib.fx_particle(context, "confetti", count,
                                   start_frame=start_frame)
