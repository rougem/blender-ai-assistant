# ============================================================
#  panels/__init__.py  —  Blender UI Panels
# ============================================================
"""
Sidebar panels registered under:
  View3D › N-panel › AI Assistant

Panels
------
  AI_PT_main        — prompt input + send button
  AI_PT_response    — displays AI response / code
  AI_PT_execute     — code review + execute controls
  AI_PT_history     — conversation summary
  AI_PT_settings    — quick link to preferences
"""

import bpy
from bpy.types import Panel, Context

from ..operators import STATE


CATEGORY = "AI Assistant"


def _truncate(s: str, max_chars: int = 120) -> str:
    return s if len(s) <= max_chars else s[:max_chars] + "…"


# ── Main Panel ────────────────────────────────────────────────────

class AI_PT_main(Panel):
    bl_label       = "AI Assistant"
    bl_idname      = "AI_PT_main"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = CATEGORY

    def draw(self, context: Context):
        layout = self.layout
        scene  = context.scene
        prefs  = context.preferences.addons.get(__package__.split(".")[0])

        # API key warning
        if prefs:
            p = prefs.preferences
            if p.ai_provider != "OLLAMA" and not p.api_key:
                box = layout.box()
                box.label(text="⚠ No API key set!", icon="ERROR")
                box.operator("preferences.addon_show",
                             text="Open Preferences").module = __package__.split(".")[0]
                return

        # Prompt input
        col = layout.column(align=True)
        col.label(text="Your Prompt:", icon="OUTLINER_OB_SPEAKER")
        col.prop(scene, "ai_prompt", text="")

        # Options row
        row = layout.row(align=True)
        row.prop(scene, "ai_include_scene_ctx",
                 text="Include Scene Context", toggle=True)

        # Send button
        row2 = layout.row()
        row2.scale_y = 1.5
        if STATE.is_running:
            row2.enabled = False
            row2.operator("ai_assistant.send_prompt",
                          text="Sending…", icon="SORTTIME")
        else:
            row2.operator("ai_assistant.send_prompt",
                          text="Send to AI", icon="PLAY")

        # Clear
        layout.operator("ai_assistant.clear_history",
                        text="Clear Conversation", icon="TRASH")


# ── Response Panel ────────────────────────────────────────────────

class AI_PT_response(Panel):
    bl_label       = "AI Response"
    bl_idname      = "AI_PT_response"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = CATEGORY
    bl_options     = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        scene  = context.scene

        display = scene.ai_response_display
        if not display:
            layout.label(text="No response yet.", icon="INFO")
            return

        # Word-wrap the response text across multiple label rows
        box = layout.box()
        # Split into lines; wrap long lines
        for raw_line in display.split("\n"):
            if not raw_line.strip():
                box.separator(factor=0.3)
                continue
            # Blender labels auto-wrap; we just need separate lines
            wrapped = raw_line
            while len(wrapped) > 70:
                box.label(text=wrapped[:70])
                wrapped = wrapped[70:]
            if wrapped:
                box.label(text=wrapped)

        if STATE.last_error:
            error_box = layout.box()
            error_box.label(text=STATE.last_error[:80], icon="ERROR")


# ── Code Execution Panel ──────────────────────────────────────────

class AI_PT_execute(Panel):
    bl_label       = "Generated Code"
    bl_idname      = "AI_PT_execute"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = CATEGORY
    bl_options     = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout

        has_code = bool(STATE.staged_code.strip())

        if not has_code:
            layout.label(text="No code staged.", icon="INFO")
            return

        # Show code preview
        box = layout.box()
        box.label(text="Preview (first 8 lines):", icon="SCRIPT")
        preview_lines = STATE.staged_code.strip().split("\n")[:8]
        for line in preview_lines:
            box.label(text=line[:72] if line.strip() else " ")
        if len(STATE.staged_code.strip().split("\n")) > 8:
            box.label(text="… (more lines hidden)")

        # Explanation
        if STATE.staged_explain:
            layout.label(text=_truncate(STATE.staged_explain, 90))

        # Action buttons
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("ai_assistant.execute_code",
                     text="▶ Execute", icon="PLAY")
        row.operator("ai_assistant.copy_code",
                     text="Copy", icon="COPYDOWN")

        # Result from last execution
        if STATE.result_message:
            res_box = layout.box()
            icon = "CHECKMARK" if STATE.result_ok else "ERROR"
            for line in STATE.result_message.strip().split("\n")[:6]:
                res_box.label(text=line[:72], icon=icon)
                icon = "NONE"


# ── History Panel ─────────────────────────────────────────────────

class AI_PT_history(Panel):
    bl_label       = "Conversation History"
    bl_idname      = "AI_PT_history"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = CATEGORY
    bl_options     = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout

        if not STATE.chat_history:
            layout.label(text="No history yet.", icon="INFO")
            return

        box = layout.box()
        for msg in STATE.chat_history[-6:]:   # last 3 pairs
            role_icon = "OUTLINER_OB_SPEAKER" if msg.role == "user" else "FAKE_USER_ON"
            col = box.column(align=True)
            col.label(text=f"{msg.role.upper()}:", icon=role_icon)
            preview = _truncate(msg.content, 80)
            for line in preview.split("\n")[:3]:
                col.label(text=line[:72])
            box.separator(factor=0.5)

        layout.label(text=f"Total turns: {len(STATE.chat_history)}")


# ── Quick Settings Panel ──────────────────────────────────────────

class AI_PT_settings(Panel):
    bl_label       = "Quick Settings"
    bl_idname      = "AI_PT_settings"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = CATEGORY
    bl_options     = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout

        prefs_entry = context.preferences.addons.get(
            __package__.split(".")[0]
        )
        if not prefs_entry:
            layout.label(text="Add-on not found in prefs.", icon="ERROR")
            return

        p = prefs_entry.preferences

        col = layout.column(align=True)
        col.prop(p, "ai_provider", text="Provider")

        if p.ai_provider == "CLAUDE":
            col.prop(p, "claude_model", text="Model")
        elif p.ai_provider == "OPENAI":
            col.prop(p, "openai_model", text="Model")
        elif p.ai_provider == "OLLAMA":
            col.prop(p, "ollama_model", text="Model")

        col.separator()
        col.prop(p, "sandbox_enabled")
        col.prop(p, "auto_execute")

        layout.separator()
        layout.operator(
            "preferences.addon_show",
            text="Full Preferences →",
            icon="PREFERENCES",
        ).module = __package__.split(".")[0]

        layout.operator(
            "ai_assistant.insert_context",
            text="Copy Scene Context JSON",
            icon="COPYDOWN",
        )


# ── Registration ──────────────────────────────────────────────────

_classes = [
    AI_PT_main,
    AI_PT_response,
    AI_PT_execute,
    AI_PT_history,
    AI_PT_settings,
]

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
