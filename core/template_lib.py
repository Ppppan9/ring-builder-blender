"""Prepare a shot from the current ring-builder level, without adding assets."""

from . import builder


def build(context):
    scene = context.scene
    if builder.level_collection(scene) is None:
        raise ValueError("请先从搭建器发送关卡，或导入关卡 JSON")
    if scene.camera is None:
        raise ValueError("当前场景没有活动相机，请先设置相机")

    result = builder.bake(scene)
    if not result["ok"]:
        raise ValueError(result["error"])
    scene.frame_end = max(scene.frame_start, builder.animation_end_frame(scene))
    scene.frame_set(scene.frame_start)
    return result
