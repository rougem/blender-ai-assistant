# ============================================================
#  utils/ai_client.py  —  AI Provider HTTP Client
# ============================================================
"""
Thin, synchronous HTTP wrapper around Claude, OpenAI, and Ollama.

Why synchronous?
  Blender operators run in the main thread. We offload the blocking
  call to a background thread (see operators/generate.py) and report
  progress via bpy.app.timers.  This module stays simple and testable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False


# ── Data structures ───────────────────────────────────────────────

@dataclass
class AIMessage:
    role: str           # "user" | "assistant" | "system"
    content: str


@dataclass
class AIResponse:
    text: str
    model: str
    usage: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ── Client ────────────────────────────────────────────────────────

class AIClient:
    """
    Usage
    -----
    client = AIClient.from_prefs(prefs)
    response = client.chat([AIMessage("user", "Add a UV sphere")])
    if response.ok:
        print(response.text)
    """

    SYSTEM_PROMPT = """You are an expert Blender Python (bpy) assistant embedded inside Blender 4.5.

When the user asks you to create or modify 3D objects you must reply with ONLY a JSON object
in this exact schema — no prose, no markdown fences:

{
  "action": "run_code" | "explain" | "modify_scene",
  "code": "<valid Python using bpy>",          // present when action == "run_code"
  "explanation": "<human-readable summary>",
  "warnings": ["<optional list of caveats>"]
}

Rules for generated code:
- Use bpy.ops or bpy.data — never import external modules.
- Always deselect all objects first, then select only what you create.
- Wrap destructive operations in try/except and print errors.
- Never call bpy.ops.wm.quit_blender() or os/sys functions.
- Keep code under 150 lines per response.
"""

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        endpoint: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        timeout: int = 60,
    ):
        self.provider    = provider
        self.api_key     = api_key
        self.model       = model
        self.endpoint    = endpoint
        self.max_tokens  = max_tokens
        self.temperature = temperature
        self.timeout     = timeout

    # ── Factory ───────────────────────────────────────────────

    @classmethod
    def from_prefs(cls, prefs) -> "AIClient":
        """Build a client from an AIAssistantPreferences instance."""
        p = prefs
        if p.ai_provider == "CLAUDE":
            return cls(
                provider    = "CLAUDE",
                api_key     = p.api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
                model       = p.claude_model,
                endpoint    = "https://api.anthropic.com/v1/messages",
                max_tokens  = p.max_tokens,
                temperature = p.temperature,
                timeout     = p.request_timeout,
            )
        elif p.ai_provider == "OPENAI":
            return cls(
                provider    = "OPENAI",
                api_key     = p.api_key or os.environ.get("OPENAI_API_KEY", ""),
                model       = p.openai_model,
                endpoint    = "https://api.openai.com/v1/chat/completions",
                max_tokens  = p.max_tokens,
                temperature = p.temperature,
                timeout     = p.request_timeout,
            )
        elif p.ai_provider == "OLLAMA":
            return cls(
                provider    = "OLLAMA",
                api_key     = "",
                model       = p.ollama_model,
                endpoint    = p.custom_endpoint or "http://localhost:11434/api/chat",
                max_tokens  = p.max_tokens,
                temperature = p.temperature,
                timeout     = p.request_timeout,
            )
        else:  # CUSTOM
            return cls(
                provider    = "OPENAI",   # assume OpenAI-compatible
                api_key     = p.api_key,
                model       = p.openai_model,
                endpoint    = p.custom_endpoint,
                max_tokens  = p.max_tokens,
                temperature = p.temperature,
                timeout     = p.request_timeout,
            )

    # ── Public API ────────────────────────────────────────────

    def chat(
        self,
        messages: list[AIMessage],
        system: Optional[str] = None,
    ) -> AIResponse:
        if not _REQUESTS_OK:
            return AIResponse(
                text="", model=self.model,
                error="'requests' package not installed. See add-on preferences."
            )

        sys_prompt = system or self.SYSTEM_PROMPT

        try:
            if self.provider == "CLAUDE":
                return self._call_claude(messages, sys_prompt)
            elif self.provider in ("OPENAI", "CUSTOM"):
                return self._call_openai(messages, sys_prompt)
            elif self.provider == "OLLAMA":
                return self._call_ollama(messages, sys_prompt)
            else:
                return AIResponse(text="", model=self.model,
                                  error=f"Unknown provider: {self.provider}")
        except requests.exceptions.Timeout:
            return AIResponse(text="", model=self.model,
                              error="Request timed out. Increase timeout in preferences.")
        except requests.exceptions.ConnectionError as e:
            return AIResponse(text="", model=self.model,
                              error=f"Connection error: {e}")
        except Exception as e:
            return AIResponse(text="", model=self.model, error=str(e))

    # ── Provider implementations ──────────────────────────────

    def _call_claude(self, messages: list[AIMessage], system: str) -> AIResponse:
        """
        Anthropic Messages API
        https://docs.anthropic.com/en/api/messages
        """
        headers = {
            "x-api-key":         self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
        body = {
            "model":      self.model,
            "max_tokens": self.max_tokens,
            "system":     system,
            "messages":   [{"role": m.role, "content": m.content}
                           for m in messages if m.role != "system"],
            "temperature": self.temperature,
        }
        r = requests.post(
            self.endpoint, headers=headers,
            json=body, timeout=self.timeout
        )
        return self._parse_claude(r)

    def _parse_claude(self, r: "requests.Response") -> AIResponse:
        if r.status_code != 200:
            try:
                detail = r.json().get("error", {}).get("message", r.text)
            except Exception:
                detail = r.text
            return AIResponse(text="", model=self.model,
                              error=f"Claude API error {r.status_code}: {detail}")
        data = r.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        return AIResponse(
            text  = text,
            model = data.get("model", self.model),
            usage = data.get("usage", {}),
        )

    def _call_openai(self, messages: list[AIMessage], system: str) -> AIResponse:
        """OpenAI Chat Completions — also works for Groq, Together, etc."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        msgs = [{"role": "system", "content": system}]
        msgs += [{"role": m.role, "content": m.content} for m in messages]

        body = {
            "model":       self.model,
            "messages":    msgs,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
        }
        r = requests.post(
            self.endpoint, headers=headers,
            json=body, timeout=self.timeout
        )
        return self._parse_openai(r)

    def _parse_openai(self, r: "requests.Response") -> AIResponse:
        if r.status_code != 200:
            try:
                detail = r.json().get("error", {}).get("message", r.text)
            except Exception:
                detail = r.text
            return AIResponse(text="", model=self.model,
                              error=f"API error {r.status_code}: {detail}")
        data  = r.json()
        text  = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return AIResponse(text=text, model=self.model, usage=usage)

    def _call_ollama(self, messages: list[AIMessage], system: str) -> AIResponse:
        """Ollama /api/chat (OpenAI-compatible format)."""
        msgs = [{"role": "system", "content": system}]
        msgs += [{"role": m.role, "content": m.content} for m in messages]
        body = {
            "model":    self.model,
            "messages": msgs,
            "stream":   False,
            "options":  {"temperature": self.temperature,
                         "num_predict": self.max_tokens},
        }
        r = requests.post(self.endpoint, json=body, timeout=self.timeout)
        if r.status_code != 200:
            return AIResponse(text="", model=self.model,
                              error=f"Ollama error {r.status_code}: {r.text}")
        data = r.json()
        text = data.get("message", {}).get("content", "")
        return AIResponse(text=text, model=self.model)
