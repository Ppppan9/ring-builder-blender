"""Blender extension entry point for the combined ring-level workflow."""

import bpy

from .core import builder, props
from .ops import registry as _ops
from .ui import registry as _panels


def register():
    if hasattr(bpy.types.Scene, "uastudio"):
        raise RuntimeError("请先停用旧版「买量工坊 UA Studio」，再启用合并版")
    builder.register()
    registered = []
    props_ready = False
    try:
        props.register()
        props_ready = True
        for cls in (*_ops, *_panels):
            bpy.utils.register_class(cls)
            registered.append(cls)
    except Exception:
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        if props_ready:
            props.unregister()
        builder.unregister()
        raise


def unregister():
    for cls in reversed((*_ops, *_panels)):
        bpy.utils.unregister_class(cls)
    props.unregister()
    builder.unregister()
