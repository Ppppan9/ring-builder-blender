"""Add a reversible standing pose without editing the builder's local animation."""

import math

import bpy
from mathutils import Matrix, Vector

from . import ring_shatter, ring_stage


_RIG = "ua_upright_rig"
_CAMERA = "ua_upright_camera"
_POSE = "UA_UprightPose"
_ACTORS = {"ring", "clasp", "prop", "acorn"}


def rig_for(coll):
    return next((obj for obj in coll.objects if obj.type == "EMPTY" and obj.get(_RIG)), None)


def _has_actor_parent(obj, actors):
    while obj.parent is not None:
        obj = obj.parent
        if obj in actors:
            return True
    return False


def fit_camera(scene, camera, width, top):
    aspect = (scene.render.resolution_x * scene.render.pixel_aspect_x
              / (scene.render.resolution_y * scene.render.pixel_aspect_y))
    camera.ortho_scale = max(top * 1.08, width * 1.1 / aspect) * max(1.0, aspect)


def _new_camera(scene, coll, width, top):
    camera = bpy.data.cameras.new("UA_UprightCamera")
    camera.type = "ORTHO"
    fit_camera(scene, camera, width, top)
    distance = max(3.0, top * 2)
    camera.clip_end = max(50.0, distance * 4)
    obj = bpy.data.objects.new("解环正视相机", camera)
    coll.objects.link(obj)
    tilt = math.radians(10)
    obj.location = (0.0, -distance, top / 2 + distance * math.tan(tilt))
    obj.rotation_euler.x = math.pi / 2 - tilt
    obj[_CAMERA] = True
    return obj


def require_single_scene(scene, coll):
    if any(s != scene and coll in s.collection.children_recursive for s in bpy.data.scenes):
        raise ValueError("这个关卡集合被多个场景共用，请先复制为独立关卡")


def remove_scenery(scene, coll, rig):
    ring_stage.restore(rig, coll)
    camera = rig.get("ua_camera")
    previous = rig.get("ua_previous_camera")
    if camera is not None and camera.get(_CAMERA) and camera in coll.objects[:]:
        if scene.camera == camera:
            scene.camera = previous if previous is not None and previous in scene.objects[:] else None
        data = camera.data
        bpy.data.objects.remove(camera, do_unlink=True)
        if data.users == 0:
            bpy.data.cameras.remove(data)


def toggle(context, coll, level, px):
    if context.mode != "OBJECT":
        raise ValueError("请切回物体模式，再调整关卡姿态")
    scene = context.scene
    require_single_scene(scene, coll)

    rig = rig_for(coll)
    if rig is not None:
        context.view_layer.update()
        inverse = rig.matrix_world.inverted()
        ring_shatter.remap_sand(coll, inverse)
        ring_shatter.remap_fragments(scene, coll, inverse)
        remove_scenery(scene, coll, rig)
        for obj in coll.all_objects:
            for constraint in tuple(obj.constraints):
                if constraint.type == "CHILD_OF" and constraint.target == rig and constraint.name.startswith(_POSE):
                    obj.constraints.remove(constraint)
        bpy.data.objects.remove(rig, do_unlink=True)
        context.view_layer.update()
        ring_shatter.rebake_sand(context, coll)
        return {"ok": True, "msg": "已恢复平铺关卡"}

    actors = {obj for obj in coll.all_objects if obj.get("rp_kind") in _ACTORS}
    if not any(obj.get("rp_kind") == "ring" for obj in actors):
        raise ValueError("当前关卡没有可立起的环")
    width, height = float(level["width"]) * px, float(level["height"]) * px
    floor = next((obj for obj in coll.all_objects if obj.type == "MESH"
                  and obj.get("rp_kind") == "stage"), None)
    context.view_layer.update()
    floor_z = floor.matrix_world.translation.z if floor is not None else 0.0
    lift = height / 2 + max(width, height) * 0.34
    matrix = Matrix.Translation(Vector((0.0, 0.0, floor_z + lift))) @ Matrix.Rotation(math.pi / 2, 4, "X")
    ring_shatter.remap_sand(coll, matrix)
    ring_shatter.remap_fragments(scene, coll, matrix)
    rig = bpy.data.objects.new("解环立式支架", None)
    coll.objects.link(rig)
    rig[_RIG] = True
    rig.matrix_world = matrix
    rig.empty_display_size = min(width, height) * 0.08
    for obj in actors:
        if _has_actor_parent(obj, actors):
            continue
        constraint = obj.constraints.new("CHILD_OF")
        constraint.name = _POSE
        constraint.target = rig
        constraint.inverse_matrix = Matrix.Identity(4)
        constraint.set_inverse_pending = False
        if obj.get("rp_kind") == "acorn":
            # Let the existing world-space Copy Location follow the rotated ring once.
            obj.constraints.move(len(obj.constraints) - 1, 0)

    if scene.camera is not None:
        rig["ua_previous_camera"] = scene.camera
    camera = _new_camera(scene, coll, width, lift + height / 2)
    camera.location.z += floor_z
    rig["ua_camera"] = camera
    rig["ua_upright_floor_z"] = floor_z
    scene.camera = camera
    ring_stage.refresh(context, coll, rig, width, height, floor_z)
    context.view_layer.update()
    ring_shatter.rebake_sand(context, coll)
    return {"ok": True, "msg": "已立起关卡并切换相机与布景，下方预留了下坠空间"}
