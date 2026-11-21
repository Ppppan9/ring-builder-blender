"""🎬 模板库：你的游戏专属分镜在这里定义。

架构沿用 UA Studio：每个模板 = 一个 build_xxx(context) 函数，
在函数内调用 scene_lib/asset_lib/material_lib/game_fx_lib/physics_lib
快速搭建 3D 场景，最后调 _finish_template 收尾（结尾卡+卡点+分镜）。

## 添加新模板的步骤

1. 在 TEMPLATES 字典里注册 {"key": ("显示名", build_xxx)}
2. 实现 build_xxx(context) 函数：
   a. 调 scene_lib.new_project() 搭基础场景
   b. 调 asset_lib.add_shape() 或 import 添加元素
   c. 调 material_lib.apply_to_selection() 赋材质
   d. 调 game_fx_lib / anim_lib / physics_lib 编排动画和特效
   e. 调 game_fx_lib.make_hud_score() 等加 HUD
   f. 调 _finish_template(context, "your_key") 收尾
3. 在 ops/shot_ops.py 的 build_template 枚举里加对应条目

## 你可以用的基础设施

- scene_lib.new_project / apply_size     → 工程搭建
- asset_lib.add_shape / grid_array       → 几何/排列
- material_lib.apply_to_selection        → 一键材质（11 种）
- game_fx_lib.hand_tap / fx_vanish       → 假玩法动作
- game_fx_lib.make_hud_score             → HUD 层
- game_fx_lib.white_flash / add_sticker  → 转场/贴纸
- anim_lib.entrance / camera_move        → 入场动画/运镜
- physics_lib.add_rigid / fx_particle    → 物理/粒子
- render_lib.export_cover / batch_render → 封面/批量渲染
"""

from __future__ import annotations

import math

import bpy

from . import (
    anim_lib,
    asset_lib,
    endcard_lib,
    game_fx_lib,
    material_lib,
    physics_lib,
    ring_lib,
    scene_lib,
    shot_lib,
    util,
)

# 分镜编排节奏（帧）——按你的游戏片长调整
HOOK_END = 90
PLAY_MID = 210
PLAY_END = 300
REWARD_END = 390


def _common_setup(context, props) -> None:
    """模板公共前置：工程搭建 + 片长 + 默认分镜。覆盖/重写此函数可定制。"""
    scene_lib.new_project(context, props)
    props.duration = 15.0  # ← 改成你的片长
    scene_lib.apply_size(context, props)
    shot_lib.setup_default(context)


def _select(objects) -> None:
    util.select_only(bpy.context, list(objects))


def _apply_mat(objects, key: str, color=(1.0, 1.0, 1.0)) -> None:
    _select(objects)
    material_lib.apply_to_selection(bpy.context, key, color)


def _finish_template(context, template_key: str) -> None:
    """模板收尾：结尾卡 + 卡点标记 + 回到主场景。"""
    props = context.scene.uastudio
    props.endcard_template = "center"  # ← 改成你要的模板类型
    scene = context.scene  # make_endcard 会切活动场景，先抓主场景
    endcard_lib.make_endcard(
        context, props.endcard_template,
        props.logo_path, props.app_name, props.cta_text,
    )
    for fr in (HOOK_END, PLAY_MID, PLAY_END, REWARD_END):
        anim_lib.add_beat(scene, frame=fr)
    try:
        context.window.scene = scene
    except (AttributeError, RuntimeError):
        pass


# ---------------------------------------------------------------------------
# 示例模板：展示基本编排模式，替换为你的游戏内容
# ---------------------------------------------------------------------------


def build_example(context) -> int:
    """示例模板：方块入场 → 手指点击 → 收集飞入 → 飞分 → 彩带。

    这是一个最小可运行的示例，展示模板编排的标准模式。
    复制此函数并修改为你的游戏内容。
    """
    props = context.scene.uastudio
    props.engine = "eevee"
    props.stage = "podium"
    props.light_mode = "three_point"
    _common_setup(context, props)
    scene = context.scene

    # TODO: 替换为你的游戏元素
    # 例如：asset_lib.add_shape("gem")、或从外部导入模型
    coins = []
    for i in range(6):
        c = asset_lib.add_shape(context, "coin")
        c.location = (-1.5 + i * 0.6, -0.4 + (i % 2) * 0.8, 0.67)
        coins.append(c)
    _apply_mat(coins, "gold")

    # Hook（1-90）：入场 + 推近
    scene.frame_set(1)
    _select(coins)
    anim_lib.entrance(context, "drop", gap=0.08)
    anim_lib.camera_move(context, "push_in", 3.0)

    # 玩法（90-210）：手指点击 + 收集飞入
    scene.frame_set(90)
    _select([coins[2]])
    game_fx_lib.hand_tap(context, 1.0)
    scene.frame_set(120)
    _select(coins[0:3])
    game_fx_lib.fx_vanish(context, 0.5, to_corner=True)

    # 爽点（210-390）：飞分 + 彩带 + 星尘
    scene.frame_set(215)
    _select([coins[4]])
    game_fx_lib.fx_score_text(context, "+100", 0.9)
    physics_lib.fx_particle(context, "confetti", 60, start_frame=240)

    # HUD
    game_fx_lib.make_hud_score(context, "分数 0")
    game_fx_lib.make_hud_progress(context, 0.6)

    # TODO: 在这里添加你的专属特效/运镜/HUD

    _finish_template(context, "example")
    scene.frame_set(1)
    return 8


# ---------------------------------------------------------------------------
# 解环拔环模板：花心 C 环簇 → 点按拔环 → 飞槽 → 感叹词+彩带
# ---------------------------------------------------------------------------


def build_ring_unlock(context) -> int:
    """解环拔环：C 环簇入场 → 手指点按拔环回弹 → 飞入顶部同色槽 → 爽点收尾。

    免搭建器一键出片；用关卡搭建器出的关卡时，改用 ring_lib.scan_rings()
    扫出真实环对象后逐环调 ring_lib.ring_pull() 编排即可。
    """
    props = context.scene.uastudio
    props.engine = "eevee"
    props.stage = "podium"
    props.light_mode = "three_point"
    _common_setup(context, props)
    scene = context.scene

    cluster = ring_lib.build_demo_cluster(
        context, colors=("green", "blue", "purple", "orange", "cyan"))
    base_z = cluster["base_z"]
    slots = ring_lib.make_slot_row(context, colors=("green", "blue", "purple"),
                                   y=1.75, spacing=0.52, z=base_z + 0.02)

    # Hook（1-90）：全簇弹入 + 推近
    scene.frame_set(1)
    util.select_only(context, [cluster["hub"]] + cluster["rings"])
    anim_lib.entrance(context, "pop", gap=0.07)
    anim_lib.camera_move(context, "push_in", 2.5)

    # 玩法（95-210）：两次拔环 + 感叹词 + 邻环晃动
    scene.frame_set(95)
    util.select_only(context, [cluster["rings"][0]])
    press = ring_lib.ring_tap(context, cluster["rings"][0], 1.5, n=1)
    ring_lib.ring_pull(context, cluster["rings"][0], slot=slots[0], start=press)
    ring_lib.word_pop(context, "Nice!", "green",
                      location=(0.0, 0.4, base_z + 0.45), frame=press + 12)
    ring_lib.slot_fill(context, slots[0], frame=press + 18)

    scene.frame_set(150)
    ring_lib.ring_wiggle(context, cluster["rings"][1:3])
    scene.frame_set(158)
    util.select_only(context, [cluster["rings"][1]])
    press = ring_lib.ring_tap(context, cluster["rings"][1], 1.5, n=2)
    ring_lib.ring_pull(context, cluster["rings"][1], slot=slots[1], start=press)
    ring_lib.word_pop(context, "Great!", "blue",
                      location=(0.0, 0.4, base_z + 0.45), frame=press + 12)
    ring_lib.slot_fill(context, slots[1], frame=press + 18)

    # 爽点（215-390）：最后一拔 + 白闪 + 彩带 + HUD
    scene.frame_set(215)
    util.select_only(context, [cluster["rings"][2]])
    press = ring_lib.ring_tap(context, cluster["rings"][2], 1.5, n=3)
    ring_lib.ring_pull(context, cluster["rings"][2], slot=slots[2], start=press)
    ring_lib.word_pop(context, "Excellent!", "orange",
                      location=(0.0, 0.4, base_z + 0.45), frame=press + 12)
    ring_lib.slot_fill(context, slots[2], frame=press + 18)
    ring_lib.confetti(context, 70, start_frame=press + 20)
    game_fx_lib.white_flash(context, at_frame=press, seconds=0.15)

    game_fx_lib.make_hud_score(context, "Level 12")
    game_fx_lib.make_hud_progress(context, 0.75)

    _finish_template(context, "ring_unlock")
    scene.frame_set(1)
    return len(cluster["rings"]) + len(cluster["clasps"]) + 2


TEMPLATES = {
    "example": ("示例模板", build_example),
    "ring_unlock": ("解环拔环", build_ring_unlock),
    # TODO: 在这里注册你的下一个游戏模板
    # "your_game": ("你的玩法名", build_your_game),
}


def build_template(context, key: str) -> int:
    entry = TEMPLATES.get(key)
    if entry is None:
        raise ValueError("未知模板 " + key)
    return entry[1](context)
