# ============================================================
#  utils/scene_context.py  —  Scene → JSON for AI Context
# ============================================================
"""
Builds a compact JSON description of the current Blender scene
so the AI has context about what already exists.

Kept deliberately small — don't send full mesh data to the API.
"""

from __future__ import annotations

import json
from typing import Any

import bpy
import mathutils


def _vec(v: mathutils.Vector | mathutils.Euler) -> list[float]:
    return [round(x, 4) for x in v]


def _obj_summary(obj: bpy.types.Object) -> dict[str, Any]:
    info: dict[str, Any] = {
        "name":     obj.name,
        "type":     obj.type,
        "location": _vec(obj.location),
        "rotation": _vec(obj.rotation_euler),
        "scale":    _vec(obj.scale),
        "visible":  not obj.hide_viewport,
    }

    if obj.type == "MESH" and obj.data:
        mesh: bpy.types.Mesh = obj.data
        info["mesh"] = {
            "vertices":  len(mesh.vertices),
            "edges":     len(mesh.edges),
            "polygons":  len(mesh.polygons),
            "materials": [m.name for m in obj.material_slots
                          if m.material],
        }
    elif obj.type == "LIGHT" and obj.data:
        light: bpy.types.Light = obj.data
        info["light"] = {
            "type":  light.type,
            "energy": round(light.energy, 2),
            "color": [round(c, 3) for c in light.color],
        }
    elif obj.type == "CAMERA" and obj.data:
        cam: bpy.types.Camera = obj.data
        info["camera"] = {
            "type": cam.type,
            "lens": round(cam.lens, 1) if cam.type == "PERSP" else None,
        }

    # Modifiers
    if obj.modifiers:
        info["modifiers"] = [
            {"name": m.name, "type": m.type, "enabled": m.show_viewport}
            for m in obj.modifiers
        ]

    return info


def build_scene_context(
    context: bpy.types.Context,
    max_objects: int = 30,
    include_materials: bool = True,
) -> str:
    """
    Return a compact JSON string describing the scene.
    Suitable for inclusion in an AI prompt.
    """
    scene   = context.scene
    objects = list(scene.objects)[:max_objects]

    active_name = (context.active_object.name
                   if context.active_object else None)
    selected    = [o.name for o in context.selected_objects]

    scene_data: dict[str, Any] = {
        "scene_name":    scene.name,
        "frame_current": scene.frame_current,
        "frame_range":   [scene.frame_start, scene.frame_end],
        "active_object": active_name,
        "selected":      selected,
        "object_count":  len(scene.objects),
        "objects":       [_obj_summary(o) for o in objects],
    }

    if include_materials:
        mats = [m.name for m in bpy.data.materials][:20]
        scene_data["materials"] = mats

    if context.mode:
        scene_data["mode"] = context.mode

    return json.dumps(scene_data, indent=2)


def scene_context_prompt(context: bpy.types.Context) -> str:
    """Return a formatted string to prepend to the user's prompt."""
    ctx_json = build_scene_context(context)
    return (
        "=== Current Blender Scene ===\n"
        f"{ctx_json}\n"
        "=== End Scene Context ===\n\n"
    )
