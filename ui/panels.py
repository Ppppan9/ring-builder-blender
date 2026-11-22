"""N 面板：依赖状态条 + 分页（按工作流排列）。"""

from __future__ import annotations

import bpy

from ..core import builder, deps


class _UABase:
    bl_category = "解环工坊"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"


class UA_PT_deps(_UABase, bpy.types.Panel):
    """按需查看原有物理依赖。"""

    bl_label = "前置插件"
    bl_order = 9
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        deps.scan()
        ready, total, worst = deps.summary()
        row = layout.row(align=True)
        row.label(text=f"依赖就绪 {ready}/{total}")
        row.separator()
        if worst != deps.S_READY:
            row.operator("ua.deps_fix_all", text="一键修复", icon="TOOL_SETTINGS")
        else:
            row.label(icon="CHECKMARK")

        for dep in deps.DEPS:
            st = deps.get_status(dep.key)
            box = layout.box()
            head = box.row(align=True)
            icon = deps.status_icon(st)
            head.label(text=dep.name, icon=icon)
            sub = head.row(align=True)
            sub.alignment = "RIGHT"
            sub.label(
                text=deps.status_text(st),
            )
            body = box.row(align=True)
            body.scale_y = 0.9
            body.label(text=f"{dep.purpose}", text_ctxt="买量工坊")
            act = body.row(align=True)
            act.alignment = "RIGHT"
            if st == deps.S_READY:
                pass
            elif st == deps.S_DISABLED:
                act.operator(
                    "ua.deps_install_one", text="启用", icon="PLUGIN"
                ).key = dep.key
            else:
                act.operator(
                    "ua.deps_install_one", text="安装", icon="DOWNARROW_HLT"
                ).key = dep.key

            if st == deps.S_UNAVAILABLE and deps.get_note(dep.key):
                box.label(text=deps.get_note(dep.key), icon="INFO")


class UA_PT_scene(_UABase, bpy.types.Panel):
    """① 工程：新建工程 + 尺寸/背景/舞台/灯光。"""

    bl_label = "① 工程"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        props = context.scene.uastudio

        level = builder.level_collection(context.scene)
        row = layout.row(align=True)
        row.operator("ringpuzzle.open_browser", icon="URL")
        if builder.connection_active():
            row.operator("ringpuzzle.stop", text="", icon="PAUSE")
        row = layout.row()
        row.operator_context = "INVOKE_DEFAULT"
        row.operator("ringpuzzle.import_json", icon="IMPORT")
        layout.prop(context.scene.rp_settings, "stage")

        row = layout.row()
        row.enabled = level is not None and context.scene.camera is not None
        row.operator_context = "INVOKE_DEFAULT"
        row.operator("ua.build_template", icon="SEQUENCE")
        if level is None:
            layout.label(text="当前未导入关卡", icon="INFO")
        elif context.scene.camera is None:
            layout.label(text="当前场景缺少相机", icon="INFO")

        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(props, "aspect")
        col.prop(props, "fps")
        col.prop(props, "duration")
        col.prop(props, "engine")
        col.operator("ua.apply_size", icon="RESTRICT_COLOR_ON")

        head = layout.row()
        head.label(text="背景", icon="WORLD")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(props, "bg_mode")
        if props.bg_mode == "gradient":
            col.prop(props, "bg_top")
        if props.bg_mode in {"gradient", "flat"}:
            col.prop(props, "bg_bottom", text="颜色" if props.bg_mode == "flat" else "底部色")
        col.operator("ua.set_background", icon="FILE_REFRESH")

        head = layout.row()
        upright = builder.is_upright(level)
        head.label(text="水平地面" if upright else "舞台", icon="MESH_CYLINDER")
        col = layout.column(align=True)
        if upright:
            col.operator("ua.set_stage", text="重建水平地面", icon="FILE_REFRESH")
        else:
            col.prop(props, "stage")
            col.operator("ua.set_stage", icon="FILE_REFRESH")

        head = layout.row()
        head.label(text="灯光", icon="LIGHT")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(props, "light_mode")
        col.prop(props, "light_strength")
        col.operator("ua.set_lighting", icon="FILE_REFRESH")


class UA_PT_array(_UABase, bpy.types.Panel):
    """② 阵列：功能规划中（占位）。"""

    bl_label = "② 阵列"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        layout.label(text="暂未开放", icon="TIME")


class UA_PT_materials(_UABase, bpy.types.Panel):
    """③ 材质：功能规划中（占位）。"""

    bl_label = "③ 材质"
    bl_order = 3

    def draw(self, context):
        layout = self.layout
        layout.label(text="暂未开放", icon="TIME")


class UA_PT_animation(_UABase, bpy.types.Panel):
    """④ 解环动画：桥接解环搭建器的三个动画功能。"""

    bl_label = "④ 解环动画"
    bl_order = 4

    def draw(self, context):
        layout = self.layout

        level = builder.level_collection(context.scene)
        has_level = level is not None
        settings = context.scene.rp_settings
        row = layout.row()
        row.enabled = has_level
        row.operator("ua.ring_pose", text="恢复平铺" if builder.is_upright(level) else "立起关卡",
                     icon="AXIS_FRONT")
        col = layout.column(align=True)
        col.enabled = has_level
        col.prop(settings, "deps", expand=True)
        col.prop(settings, "direction")
        col.prop(settings, "sec_per_step")
        row = col.row(align=True)
        row.prop(settings, "fx_move", toggle=True)
        row.prop(settings, "fx_fade", toggle=True)
        col.operator("ua.ring_unlock", icon="UNLOCKED")
        col.operator("ua.ring_bake", icon="RENDER_ANIMATION")
        col.operator("ua.ring_clear", icon="X")
        box = layout.box()
        box.enabled = has_level
        box.label(text=f"破碎起始帧：{context.scene.frame_current}", icon="MOD_EXPLODE")
        box.prop(settings, "shatter_target")
        box.prop(settings, "shatter_effect", expand=True)
        box.prop(settings, "shatter_timing", expand=True)
        box.prop(settings, "shatter_spread")
        if settings.shatter_effect == "chunks":
            box.prop(settings, "shatter_count")
        else:
            box.prop(settings, "sand_count")
            box.prop(settings, "sand_dust")
            if settings.shatter_timing == "sweep":
                box.prop(settings, "shatter_count", text="弧段数")
        if settings.shatter_timing == "sweep":
            box.prop(settings, "shatter_frames")
            box.prop(settings, "shatter_reverse")
        row = box.row()
        row.scale_y = 1.2
        row.operator("ua.ring_shatter", text="执行破碎", icon="MOD_EXPLODE")
        if not has_level:
            layout.label(text="当前未导入关卡", icon="INFO")


class UA_PT_camera(_UABase, bpy.types.Panel):
    """⑥ 相机：运镜 / 构图安全区。"""

    bl_label = "⑥ 相机"
    bl_order = 7

    def draw(self, context):
        layout = self.layout
        props = context.scene.uastudio

        head = layout.row()
        head.label(text="运镜", icon="CAMERA_DATA")
        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("ua.cam_move", text="推近").mode = "push_in"
        col.operator("ua.cam_move", text="环绕").mode = "orbit"
        col.operator("ua.cam_move", text="震屏(贴卡点)").mode = "shake"
        col.operator("ua.cam_from_view", text="当前视角设为相机新视角",
                     icon="VIEW_CAMERA")
        col.prop(props, "cam_seconds")

        head = layout.row()
        head.label(text="构图", icon="VIEW_CAMERA")
        col = layout.column(align=True)
        col.operator("ua.safety_frame", icon="MESH_GRID")


class UA_PT_physics(_UABase, bpy.types.Panel):
    """⑤ 物理：刚体 / 破碎 / 粒子（布料/软体/流体）。"""

    bl_label = "⑤ 物理"
    bl_order = 6

    def draw(self, context):
        layout = self.layout
        props = context.scene.uastudio

        head = layout.row()
        head.label(text="刚体碰撞", icon="RIGID_BODY")
        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("ua.drop_pile", text="掉落堆叠")
        col.operator("ua.impact", text="冲击撞飞")
        col.operator("ua.rigid_passive", text="设为固定碰撞体")

        head = layout.row()
        head.label(text="破碎（Cell Fracture）", icon="MOD_EXPLODE")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(props, "fracture_count")
        col.prop(props, "fracture_noise")
        col.prop(props, "fracture_explode")
        if props.fracture_explode:
            col.prop(props, "explode_strength")
        col.operator("ua.fracture", text="一键破碎", icon="MOD_EXPLODE")

        head = layout.row()
        head.label(text="粒子特效", icon="PARTICLES")
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        grid.operator("ua.fx_particle", text="金币喷泉").kind = "coins"
        grid.operator("ua.fx_particle", text="彩带庆祝").kind = "confetti"
        grid.operator("ua.fx_particle", text="星尘飘落").kind = "stardust"
        grid.operator("ua.fx_particle", text="爆炸碎屑").kind = "boom"
        col = layout.column(align=True)
        col.prop(props, "fx_count")

        head = layout.row()
        head.label(text="布料·软体·绳索·流体", icon="MOD_CLOTH")
        grid = layout.grid_flow(row_major=True, columns=2, even_columns=True)
        grid.operator("ua.flag", text="旗帜飘动")
        grid.operator("ua.tablecloth", text="桌布铺开")
        grid.operator("ua.jelly", text="果冻 Q 弹")
        grid.operator("ua.rope", text="绳索摆挂")
        grid.operator("ua.cloth_selected", text="选中变布料")
        grid.operator("ua.fluid_splash", text="流体泼溅")
        col = layout.column(align=True)
        col.prop(props, "fluid_resolution")

        head = layout.row()
        head.label(text="总控", icon="FILE_REFRESH")
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("ua.physics_bake", text="烘焙全部物理", icon="REC")
        row.operator("ua.physics_clear", text="清缓存")


class UA_PT_render(_UABase, bpy.types.Panel):
    """⑦ 渲染：输出预设 / 一键出片 / 矩阵 / 封面 / 批量。"""

    bl_label = "⑦ 渲染"
    bl_order = 8

    def draw(self, context):
        layout = self.layout
        props = context.scene.uastudio

        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(props, "out_format")
        col.prop(props, "out_dir")
        col.prop(props, "transparent")

        col = layout.column(align=True)
        col.scale_y = 1.4
        col.operator("ua.render_current", text="一键渲染当前片", icon="RENDER_ANIMATION")
        row = col.row(align=True)
        row.operator("ua.render_current", text="试渲染当前帧").still = True
        row.operator("ua.batch_render", text="批量渲染", icon="RENDERLAYERS")

        head = layout.row()
        head.label(text="画质与风格", icon="SETTINGS")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(props, "quality_level")
        col.operator("ua.apply_quality", icon="MOD_SUBSURF")
        col.prop(props, "color_style")
        col.operator("ua.color_style", icon="COLOR")
        col.prop(props, "dof_fstop")
        row = col.row(align=True)
        row.operator("ua.dof_focus", text="景深聚焦选中", icon="VIEW_CAMERA")
        row.operator("ua.dof_focus", text="关景深").disable = True
        row = col.row(align=True)
        row.operator("ua.motion_blur", text="开运动模糊").on = True
        row.operator("ua.motion_blur", text="关").on = False

        sub = layout.box()
        sub.label(text="实验性（本构建有崩溃风险）", icon="ERROR")
        sub.prop(props, "bloom_on")
        if props.bloom_on:
            sub.prop(props, "bloom_strength")
        sub.prop(props, "vignette_on")
        sub.operator("ua.setup_compositor", text="应用合成链(实验)",
                     icon="NODE_COMPOSITING")

        head = layout.row()
        head.label(text="投放输出", icon="SEQUENCE")
        col = layout.column(align=True)
        col.prop(props, "cover_frame")
        row = col.row(align=True)
        row.scale_y = 1.2
        row.operator("ua.size_matrix", text="多尺寸矩阵 3 画幅", icon="MOD_SOLIDIFY")
        col.operator("ua.export_cover", text="导出封面图", icon="FILE_IMAGE")

        head = layout.row()
        head.label(text="交付", icon="PACKAGE")
        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("ua.delivery_package", text="一键交付包", icon="PACKAGE")

        head = layout.row()
        head.label(text="工程", icon="FILE_REFRESH")
        col = layout.column(align=True)
        col.operator("ua.cleanup_project", text="清理孤儿数据", icon="BRUSH_DATA")


classes = (
    UA_PT_deps, UA_PT_scene, UA_PT_array, UA_PT_materials,
    UA_PT_animation, UA_PT_physics, UA_PT_camera, UA_PT_render,
)