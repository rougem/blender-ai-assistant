# ============================================================
#  preferences.py  —  Add-on Preferences
# ============================================================
"""
Stores:
  • AI provider selection (Claude / OpenAI / local Ollama)
  • API key (stored in Blender prefs, NOT in the .blend file)
  • Safety & execution settings
"""

import bpy
from bpy.props import (
    StringProperty,
    EnumProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
)
from bpy.types import AddonPreferences


class AIAssistantPreferences(AddonPreferences):
    bl_idname = __package__   # must match the add-on package name

    # ── Provider ──────────────────────────────────────────────
    ai_provider: EnumProperty(
        name="AI Provider",
        description="Which AI backend to use",
        items=[
            ("CLAUDE",  "Anthropic Claude",  "Use Anthropic Claude API"),
            ("OPENAI",  "OpenAI / GPT",      "Use OpenAI-compatible API"),
            ("OLLAMA",  "Ollama (local)",     "Use a locally running Ollama server"),
            ("CUSTOM",  "Custom endpoint",   "Any OpenAI-compatible REST endpoint"),
        ],
        default="CLAUDE",
    )

    # ── API credentials ───────────────────────────────────────
    api_key: StringProperty(
        name="API Key",
        description="Your secret API key — stored only in Blender preferences",
        subtype="PASSWORD",
        default="",
    )

    # ── Model selection ───────────────────────────────────────
    claude_model: EnumProperty(
        name="Claude Model",
        items=[
            ("claude-sonnet-4-20250514", "Claude Sonnet 4",  "Fast & capable"),
            ("claude-opus-4-20250514",   "Claude Opus 4",    "Most capable"),
        ],
        default="claude-sonnet-4-20250514",
    )

    openai_model: StringProperty(
        name="OpenAI Model",
        default="gpt-4o",
    )

    ollama_model: StringProperty(
        name="Ollama Model",
        default="llama3",
    )

    custom_endpoint: StringProperty(
        name="Custom Endpoint URL",
        default="http://localhost:11434/api/chat",
    )

    # ── Generation params ─────────────────────────────────────
    max_tokens: IntProperty(
        name="Max Response Tokens",
        default=2048,
        min=256,
        max=8192,
    )

    temperature: FloatProperty(
        name="Temperature",
        default=0.3,
        min=0.0,
        max=1.0,
    )

    request_timeout: IntProperty(
        name="Request Timeout (s)",
        default=60,
        min=5,
        max=300,
    )

    # ── Safety / sandbox settings ─────────────────────────────
    sandbox_enabled: BoolProperty(
        name="Sandbox AI Code",
        description="Restrict what AI-generated Python code can access",
        default=True,
    )

    auto_execute: BoolProperty(
        name="Auto-Execute Generated Code",
        description="Execute AI code immediately (disable for manual review first)",
        default=False,
    )

    confirm_destructive: BoolProperty(
        name="Confirm Before Modifying Existing Objects",
        default=True,
    )

    # ── UI ─────────────────────────────────────────────────────
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        col = layout.column(heading="Provider")
        col.prop(self, "ai_provider")

        box = layout.box()
        box.label(text="Credentials", icon="KEY_HLT")

        if self.ai_provider == "OLLAMA":
            box.label(text="No API key required for Ollama.", icon="INFO")
            box.prop(self, "ollama_model")
            box.prop(self, "custom_endpoint", text="Ollama URL")
        else:
            row = box.row()
            row.prop(self, "api_key")
            if not self.api_key:
                row.label(text="", icon="ERROR")

        if self.ai_provider == "CLAUDE":
            box.prop(self, "claude_model")
        elif self.ai_provider == "OPENAI":
            box.prop(self, "openai_model")
        elif self.ai_provider == "CUSTOM":
            box.prop(self, "custom_endpoint")

        box2 = layout.box()
        box2.label(text="Generation", icon="MODIFIER")
        box2.prop(self, "max_tokens")
        box2.prop(self, "temperature")
        box2.prop(self, "request_timeout")

        box3 = layout.box()
        box3.label(text="Safety", icon="LOCKED")
        box3.prop(self, "sandbox_enabled")
        box3.prop(self, "auto_execute")
        box3.prop(self, "confirm_destructive")

        if not self.sandbox_enabled:
            box3.label(
                text="⚠ Sandbox disabled — AI code runs unrestricted!",
                icon="ERROR",
            )


# ── helpers ───────────────────────────────────────────────────────

def get_prefs(context=None) -> AIAssistantPreferences:
    ctx = context or bpy.context
    return ctx.preferences.addons[__package__].preferences


# ── registration ──────────────────────────────────────────────────

_classes = [AIAssistantPreferences]

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
