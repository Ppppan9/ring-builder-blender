"""Operator 层聚合。"""

from . import (
    deps_ops,
    scene_ops,
    ring_ops,
    camera_ops,
    physics_ops,
    render_ops,
    shot_ops,
    quality_ops,
)

classes = (
    *deps_ops.classes,
    *scene_ops.classes,
    *ring_ops.classes,
    *camera_ops.classes,
    *physics_ops.classes,
    *render_ops.classes,
    *shot_ops.classes,
    *quality_ops.classes,
)

registry = tuple(classes)  # 顶层 __init__ 遍历注册
