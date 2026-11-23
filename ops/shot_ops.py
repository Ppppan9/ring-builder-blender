"""Prepare and package the current ring level for rendering."""

import bpy

from ..core import deliver_lib, template_lib


class UA_OT_build_template(bpy.types.Operator):
    """按真实解谜顺序烘焙当前关卡，保留机位、模型和画幅"""

    bl_idname = "ua.build_template"
    bl_label = "一键广告模板"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = template_lib.build(context)
        except (ValueError, RuntimeError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, result["msg"])
        return {"FINISHED"}


class UA_OT_delivery_package(bpy.types.Operator):
    """打包当前关卡的渲染结果、封面和工程副本"""

    bl_idname = "ua.delivery_package"
    bl_label = "一键交付包"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            path = deliver_lib.export_delivery_package(context)
        except (RuntimeError, ValueError, OSError) as exc:
            self.report({"ERROR"}, "交付失败: " + str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "交付包已输出 " + path)
        return {"FINISHED"}


classes = (UA_OT_build_template, UA_OT_delivery_package)
