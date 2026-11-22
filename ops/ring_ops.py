"""Expose the builder's existing animation operations in the combined panel."""

import bpy

from ..core import builder


def _run(operator, action, *args):
    try:
        result = action(*args)
    except (ValueError, RuntimeError) as exc:
        operator.report({"WARNING"}, str(exc))
        return {"CANCELLED"}
    message = result.get("msg") or result.get("error")
    if not result["ok"]:
        operator.report({"WARNING"}, message or "解环操作未完成")
        return {"CANCELLED"}
    operator.report({"INFO"}, message or "已清除解环动画")
    return {"FINISHED"}


class UA_OT_ring_unlock(bpy.types.Operator):
    """从当前帧开始解开选中的环或卡扣所属的环"""

    bl_idname = "ua.ring_unlock"
    bl_label = "解开选中环"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return _run(self, builder.unlock_selected, context)


class UA_OT_ring_bake(bpy.types.Operator):
    """替换本关卡已有解环动画，按真实解谜顺序烘焙全关"""

    bl_idname = "ua.ring_bake"
    bl_label = "烘焙解谜动画"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return _run(self, builder.bake, context.scene)


class UA_OT_ring_clear(bpy.types.Operator):
    """清除搭建器关卡的解环动画，恢复环的初始状态"""

    bl_idname = "ua.ring_clear"
    bl_label = "清除解环动画"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return _run(self, builder.clear, context.scene)


class UA_OT_ring_shatter(bpy.types.Operator):
    """按所选效果与时序从当前帧破碎选中环，无需先解开"""

    bl_idname = "ua.ring_shatter"
    bl_label = "执行破碎"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return _run(self, builder.shatter, context)


class UA_OT_ring_pose(bpy.types.Operator):
    """在平铺和立式之间切换，保留解环动作和原有相机"""

    bl_idname = "ua.ring_pose"
    bl_label = "切换关卡姿态"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return _run(self, builder.toggle_pose, context)


classes = (UA_OT_ring_unlock, UA_OT_ring_bake, UA_OT_ring_clear,
           UA_OT_ring_shatter, UA_OT_ring_pose)
