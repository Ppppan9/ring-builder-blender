"""Managed scenery for upright levels; the flat scenery is preserved in place."""

import bpy
from mathutils import Vector

from . import util


_COLLECTION = "ua_upright_stage"
_PART = "ua_upright_part"
_HIDDEN = "ua_flat_visibility"
_FLAT_MESHES = {"UA_Stage_Podium", "UA_Stage_Desk", "UA_Stage_Floor", "UA_Backdrop"}


def _hide_flat_objects(scene, level, rig):
    members = set(level.all_objects)
    flat_lights = bpy.data.collections.get("UA_Lights")
    hidden = rig.get(_HIDDEN, {})
    recorded = {state.get("object") for state in hidden.values()}
    entries = {key: dict(state.items()) for key, state in hidden.items()}
    for obj in scene.objects:
        if obj in recorded or obj.get(_PART) or len(obj.users_scene) != 1 or not obj.is_editable:
            continue
        from_builder = (obj in members and obj.get("rp_kind") == "stage"
                        and obj.type in {"MESH", "LIGHT"})
        from_workshop = (obj.name in _FLAT_MESHES and obj.type == "MESH"
                         or obj.type == "LIGHT" and obj.name.startswith("UA_Light_")
                         and flat_lights in obj.users_collection[:])
        if not (from_builder or from_workshop) or obj.animation_data is not None:
            continue
        entries[str(len(entries))] = {"object": obj, "render": obj.hide_render,
                                     "viewport": obj.hide_viewport}
    rig[_HIDDEN] = entries
    for state in rig[_HIDDEN].values():
        obj = state.get("object")
        if obj is not None:
            obj.hide_render = obj.hide_viewport = True


def _remove_parts(collection, kind=None):
    for obj in list(collection.objects):
        part = obj.get(_PART)
        if not part or (kind is not None and part != kind):
            continue
        data = obj.data
        materials = list(data.materials) if obj.type == "MESH" else []
        datablocks = bpy.data.meshes if obj.type == "MESH" else bpy.data.lights
        bpy.data.objects.remove(obj, do_unlink=True)
        if data.users == 0:
            datablocks.remove(data)
        for mat in materials:
            if mat is not None and mat.users == 0 and mat.get(_PART):
                bpy.data.materials.remove(mat)


def restore(rig, level):
    for state in rig.get(_HIDDEN, {}).values():
        obj = state.get("object")
        if obj is not None:
            obj.hide_render = bool(state["render"])
            obj.hide_viewport = bool(state["viewport"])
    collection = rig.get(_COLLECTION)
    if collection is not None and collection in level.children[:]:
        _remove_parts(collection)
        if not collection.objects and not collection.children:
            bpy.data.collections.remove(collection)


def _panel(collection, name, props, vertices, kind, faces=((0, 1, 2, 3),)):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], list(faces))
    obj = bpy.data.objects.new(name, mesh)
    obj[_PART] = kind
    collection.objects.link(obj)
    mat = bpy.data.materials.new(name)
    mat[_PART] = kind
    mat.use_nodes = True
    mesh.materials.append(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    if kind == "floor":
        # 显式搭建，不按名字找节点：中文界面下新建材质的节点名会被翻译。
        nodes.clear()
        color = (0.19, 0.23, 0.30, 1.0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        output = nodes.new("ShaderNodeOutputMaterial")
        links.new(bsdf.outputs[0], output.inputs["Surface"])
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.8
        mat.diffuse_color = color
        obj["rp_kind"] = "stage"
        return obj

    nodes.clear()
    surface = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    links.new(emission.outputs[0], surface.inputs["Surface"])
    bottom, top = props.bg_bottom, props.bg_top
    if props.bg_mode == "studio":
        bottom, top = (0.24, 0.26, 0.30), (0.055, 0.065, 0.085)
    if props.bg_mode == "flat":
        emission.inputs["Color"].default_value = (*bottom, 1.0)
    else:
        tex = nodes.new("ShaderNodeTexCoord")
        axis = nodes.new("ShaderNodeSeparateXYZ")
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*bottom, 1.0)
        ramp.color_ramp.elements[1].color = (*top, 1.0)
        links.new(tex.outputs["Generated"], axis.inputs[0])
        links.new(axis.outputs["Z"], ramp.inputs[0])
        links.new(ramp.outputs["Color"], emission.inputs["Color"])
    obj.visible_shadow = False
    obj.visible_diffuse = False


def _lights(context, collection, span, center, props):
    if props.light_mode == "none":
        return
    wide = 1.6 if props.light_mode == "softbox" else 1.0
    if props.light_mode == "sky":
        # Use a broad overhead source without changing the authored world.
        lights = (("立式天空柔光", (-0.25, -0.55, 1.05), 34, 2.2, (0.88, 0.94, 1.0)),)
    else:
        lights = (
            ("立式主光", (-0.65, -0.95, 0.85), 22, 0.8, (1.0, 0.94, 0.90)),
            ("立式补光", (0.75, -0.65, 0.25), 9, 1.0, (0.88, 0.94, 1.0)),
            ("立式轮廓光", (0.40, 0.55, 0.85), 14, 0.7, (1.0, 1.0, 1.0)),
        )
    for name, offset, power, size, color in lights:
        light = util.add_light(context, name, "AREA", Vector(center) + span * Vector(offset),
                               energy=power * span ** 2 * props.light_strength,
                               size=size * span * wide, target=center, color=color, coll=collection)
        light[_PART] = "light"


def refresh(context, level, rig, width, height, floor_z, *, kind=None):
    scene = context.scene
    props = scene.uastudio
    collection = rig.get(_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new("解环立式布景")
        level.children.link(collection)
        rig[_COLLECTION] = collection
        kind = None
    _hide_flat_objects(scene, level, rig)
    _remove_parts(collection, kind)
    span = max(width, height)
    aspect = (scene.render.resolution_x * scene.render.pixel_aspect_x
              / (scene.render.resolution_y * scene.render.pixel_aspect_y))
    # Cover all workshop output presets without rebuilding an existing floor collider.
    half_width = span * max(2.5, aspect * 1.3)
    back = span * 0.85
    if kind in (None, "floor"):
        # 实心底座：碰撞盒有厚度，快速碎片不会隧穿；底座在相机视野外，不影响画面。
        # Blender 的 BOX 碰撞体以物体原点为中心，网格必须以原点对称、再用位移就位。
        thickness = max(0.25, 0.2 * span)
        top = [(-half_width, -3 * span, thickness / 2), (half_width, -3 * span, thickness / 2),
               (half_width, back, thickness / 2), (-half_width, back, thickness / 2)]
        bottom_row = [(x, y, -thickness / 2) for x, y, _z in top]
        slab = _panel(collection, "解环立式地面", props, top + bottom_row, "floor",
                      faces=((0, 1, 2, 3), (3, 2, 6, 7), (1, 0, 4, 5),
                             (2, 1, 5, 6), (0, 3, 7, 4), (4, 7, 6, 5)))
        slab.location.z = floor_z - thickness / 2
    if kind in (None, "background"):
        _panel(collection, "解环立式背景板", props,
               [(-half_width, back, floor_z - span), (half_width, back, floor_z - span),
                (half_width, back, floor_z + 2.4 * span), (-half_width, back, floor_z + 2.4 * span)],
               "background")
    if kind in (None, "light"):
        _lights(context, collection, span, (0.0, 0.0, floor_z + height / 2 + span * 0.34), props)
    context.view_layer.update()
