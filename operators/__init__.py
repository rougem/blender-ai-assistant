# ============================================================
#  operators/__init__.py  —  All Blender Operators
# ============================================================
"""
Operators registered here:

  AI_OT_send_prompt      — sends user prompt, runs AI in background thread
  AI_OT_execute_code     — executes the staged AI code after user review
  AI_OT_clear_history    — clears conversation history
  AI_OT_copy_code        — copies staged code to clipboard
  AI_OT_insert_context   — inserts current scene context into prompt box
"""

from __future__ import annotations

import json
import threading
from typing import Optional

import bpy
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator, Context

from ..preferences  import get_prefs
from ..utils        import (
    AIClient, AIMessage,
    execute_blender_code,
    scene_context_prompt,
)

# ── Add-on state (module-level singletons) ────────────────────────
# Blender operators are stateless; we keep mutable state here.

class AddonState:
    is_running:      bool          = False   # background thread active?
    last_response:   str           = ""      # raw AI response text
    last_error:      str           = ""      # last error message
    staged_code:     str           = ""      # code ready to execute / review
    staged_explain:  str           = ""      # human explanation of staged code
    chat_history:    list[AIMessage] = []    # conversation turns
    result_message:  str           = ""      # shown after execution
    result_ok:       bool          = True


STATE = AddonState()

# ── Conversation store property on Scene ─────────────────────────
# We store the display text on bpy props so Blender's UI can show it.

def _register_scene_props():
    bpy.types.Scene.ai_prompt = StringProperty(
        name="Prompt",
        description="Your message to the AI",
        default="",
    )
    bpy.types.Scene.ai_response_display = StringProperty(
        name="AI Response",
        default="",
    )
    bpy.types.Scene.ai_include_scene_ctx = BoolProperty(
        name="Include Scene Context",
        description="Attach a JSON summary of the scene to your prompt",
        default=True,
    )


def _unregister_scene_props():
    for prop in ("ai_prompt", "ai_response_display", "ai_include_scene_ctx"):
        if hasattr(bpy.types.Scene, prop):
            try:
                delattr(bpy.types.Scene, prop)
            except Exception:
                pass


# ── Helper: parse AI response ─────────────────────────────────────

def _parse_response(text: str) -> dict:
    """
    Attempt to parse a JSON object from the AI response.
    Falls back to a plain 'explain' action if parsing fails.
    """
    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "action" in data:
            return data
    except json.JSONDecodeError:
        pass

    # Fallback — treat entire response as explanation
    return {"action": "explain", "explanation": text}


# ── Operator: Send Prompt ─────────────────────────────────────────

class AI_OT_send_prompt(Operator):
    bl_idname      = "ai_assistant.send_prompt"
    bl_label       = "Send"
    bl_description = "Send your prompt to the AI (runs in background)"

    def execute(self, context: Context):
        if STATE.is_running:
            self.report({"WARNING"}, "AI request already in progress.")
            return {"CANCELLED"}

        prompt = context.scene.ai_prompt.strip()
        if not prompt:
            self.report({"WARNING"}, "Please enter a prompt.")
            return {"CANCELLED"}

        prefs = get_prefs(context)

        if prefs.ai_provider != "OLLAMA" and not prefs.api_key:
            self.report(
                {"ERROR"},
                "No API key set. Go to Preferences → Add-ons → AI Assistant.",
            )
            return {"CANCELLED"}

        # Build the message
        user_content = prompt
        if context.scene.ai_include_scene_ctx:
            user_content = scene_context_prompt(context) + user_content

        STATE.chat_history.append(AIMessage(role="user", content=user_content))
        STATE.is_running    = True
        STATE.last_error    = ""
        STATE.staged_code   = ""
        STATE.staged_explain = ""
        context.scene.ai_response_display = "⏳ Thinking…"

        # Capture snapshot of prefs for the thread (prefs are main-thread)
        client = AIClient.from_prefs(prefs)
        history_snapshot = list(STATE.chat_history)

        def _worker():
            response = client.chat(history_snapshot)
            def _back():
                STATE.is_running = False
                if not response.ok:
                    STATE.last_error = response.error
                    context.scene.ai_response_display = f"❌ {response.error}"
                    return None

                STATE.last_response = response.text
                STATE.chat_history.append(
                    AIMessage(role="assistant", content=response.text)
                )

                parsed = _parse_response(response.text)
                action  = parsed.get("action", "explain")
                explain = parsed.get("explanation", "")
                code    = parsed.get("code", "")
                warnings = parsed.get("warnings", [])

                STATE.staged_code    = code
                STATE.staged_explain = explain

                display_lines = []
                if explain:
                    display_lines.append(explain)
                if warnings:
                    display_lines.append("⚠ " + "; ".join(warnings))
                if code:
                    display_lines.append(
                        f"\n--- Generated Code ---\n{code}\n"
                        "--- End Code ---"
                    )
                    if prefs.auto_execute:
                        _do_execute(context)

                context.scene.ai_response_display = (
                    "\n".join(display_lines) or response.text
                )
                # Clear the prompt box
                context.scene.ai_prompt = ""
                return None   # timers must return None or a float

            bpy.app.timers.register(_back, first_interval=0.05)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        return {"FINISHED"}


# ── Operator: Execute Staged Code ─────────────────────────────────

def _do_execute(context: Context):
    """Execute STATE.staged_code using the sandbox."""
    prefs = get_prefs(context)
    result = execute_blender_code(
        STATE.staged_code,
        sandbox_enabled = prefs.sandbox_enabled,
        timeout         = 30.0,
    )
    STATE.result_ok      = result.success
    STATE.result_message = (result.output or "Done.") if result.success else result.error
    STATE.staged_code    = ""   # clear after execution
    # Refresh UI
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class AI_OT_execute_code(Operator):
    bl_idname      = "ai_assistant.execute_code"
    bl_label       = "Execute Generated Code"
    bl_description = "Run the AI-generated code in Blender"

    def invoke(self, context: Context, event):
        prefs = get_prefs(context)
        if prefs.confirm_destructive and context.selected_objects:
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context: Context):
        if not STATE.staged_code.strip():
            self.report({"WARNING"}, "No code to execute.")
            return {"CANCELLED"}

        _do_execute(context)

        if STATE.result_ok:
            self.report({"INFO"}, "AI code executed successfully.")
        else:
            self.report({"ERROR"}, f"Execution error — see response panel.")
        return {"FINISHED"}


# ── Operator: Clear History ───────────────────────────────────────

class AI_OT_clear_history(Operator):
    bl_idname      = "ai_assistant.clear_history"
    bl_label       = "Clear Conversation"
    bl_description = "Clear the chat history"

    def execute(self, context: Context):
        STATE.chat_history.clear()
        STATE.staged_code   = ""
        STATE.staged_explain = ""
        STATE.last_error    = ""
        context.scene.ai_response_display = ""
        self.report({"INFO"}, "Conversation cleared.")
        return {"FINISHED"}


# ── Operator: Copy Code to Clipboard ─────────────────────────────

class AI_OT_copy_code(Operator):
    bl_idname      = "ai_assistant.copy_code"
    bl_label       = "Copy Code"
    bl_description = "Copy the generated code to the clipboard"

    def execute(self, context: Context):
        if not STATE.staged_code:
            self.report({"WARNING"}, "No staged code to copy.")
            return {"CANCELLED"}
        context.window_manager.clipboard = STATE.staged_code
        self.report({"INFO"}, "Code copied to clipboard.")
        return {"FINISHED"}


# ── Operator: Insert Scene Context ───────────────────────────────

class AI_OT_insert_context(Operator):
    bl_idname      = "ai_assistant.insert_context"
    bl_label       = "Insert Scene Context"
    bl_description = "Preview the scene JSON that will be sent to the AI"

    def execute(self, context: Context):
        ctx_str = scene_context_prompt(context)
        context.window_manager.clipboard = ctx_str
        self.report({"INFO"}, "Scene context copied to clipboard.")
        return {"FINISHED"}


# ── Registration ──────────────────────────────────────────────────

_classes = [
    AI_OT_send_prompt,
    AI_OT_execute_code,
    AI_OT_clear_history,
    AI_OT_copy_code,
    AI_OT_insert_context,
]

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    _register_scene_props()

def unregister():
    _unregister_scene_props()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
