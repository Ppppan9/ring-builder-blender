"""⑥ 相机 Operator：运镜与安全区。"""

from __future__ import annotations

import bpy

from ..core import anim_lib


class UA_OT_cam_move(bpy.types.Operator):
    """相机运镜预设"""

    bl_idname = "ua.cam_move"
    bl_label = "相机运镜"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(
        name="运镜",
        items=[
            ("push_in", "推近", "沿视线推进 15%"),
            ("orbit", "环绕", "挂枢轴环绕一周"),
            ("shake", "震屏", "0.4 秒高频抖动"),
        ],
    )

    def execute(self, context):
        try:
            anim_lib.camera_move(
                context, self.mode, context.scene.uastudio.cam_seconds
            )
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "运镜已加到广告相机")
        return {"FINISHED"}


class UA_OT_safety_frame(bpy.types.Operator):
    """创建构图安全区参考线（不渲染）"""

    bl_idname = "ua.safety_frame"
    bl_label = "构图安全区参考线"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        anim_lib.safety_frame(context)
        self.report({"INFO"}, "顶部UI区/底部CTA区参考线已创建")
        return {"FINISHED"}


class UA_OT_cam_from_view(bpy.types.Operator):
    """将活动相机对齐到按钮所在的 3D 视口"""

    bl_idname = "ua.cam_from_view"
    bl_label = "当前视角设为相机新视角"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (not bpy.app.background and context.area is not None
                and context.area.type == "VIEW_3D" and context.scene.camera is not None)

    def execute(self, context):
        region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
        if region is not None:
            with context.temp_override(region=region):
                if bpy.ops.view3d.camera_to_view.poll():
                    return bpy.ops.view3d.camera_to_view()
        self.report({"WARNING"}, "请退出相机视图后再对齐")
        return {"CANCELLED"}


classes = (UA_OT_cam_move, UA_OT_safety_frame, UA_OT_cam_from_view)
