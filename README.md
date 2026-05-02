# Blender AI Assistant

A Blender 4.5 add-on that brings real-time AI guidance and AI-driven 3D model generation directly into your workflow. Send natural language prompts to Claude, GPT-4, or a local Ollama model and have it generate or modify meshes, materials, modifiers, and Geometry Nodes — all without leaving Blender.

![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)
![Blender](https://img.shields.io/badge/Blender-4.5%2B-orange)
![Python](https://img.shields.io/badge/Python-3.11-yellow)

---

## Features

- **Natural language to 3D** — describe what you want and the AI generates the `bpy` code to build it
- **Multi-provider support** — works with Anthropic Claude, OpenAI / GPT-4, or a locally running Ollama model
- **Scene-aware prompts** — optionally attaches a live JSON summary of your scene so the AI knows what already exists
- **Code review before execution** — inspect generated code in the panel before running it
- **Safety sandbox** — AST static analysis blocks dangerous imports and operations before any code runs
- **Conversation history** — multi-turn chat so you can refine results iteratively
- **Non-blocking UI** — all API calls run in a background thread; Blender stays responsive

---

## Supported AI Providers

| Provider | Notes |
|---|---|
| Anthropic Claude | Claude Sonnet 4, Claude Opus 4 |
| OpenAI | GPT-4o and any OpenAI-compatible endpoint |
| Ollama (local) | llama3, mistral, codellama, etc. — fully offline |
| Custom endpoint | Any OpenAI-compatible REST API |

---

## Requirements

- Blender 4.5 or later
- Internet connection for cloud providers (Claude / OpenAI)
- [Ollama](https://ollama.com) installed locally for offline use
- The `requests` Python package — **auto-installed on first enable**

---

## Installation

1. Download the latest `blender_ai_assistant.zip` from the [Releases](../../releases) page.
2. Open Blender and go to **Edit → Preferences → Add-ons**.
3. Click **Install** and select the downloaded zip file.
4. Enable the add-on by ticking the checkbox next to **AI Assistant**.
5. On first enable, the add-on will automatically install the `requests` package into Blender's Python environment.

---

## Configuration

After enabling the add-on, go to **Edit → Preferences → Add-ons → AI Assistant** to configure:

### Choosing a Provider

Select your preferred provider from the **AI Provider** dropdown:

- **Anthropic Claude** — paste your API key from [console.anthropic.com](https://console.anthropic.com)
- **OpenAI / GPT** — paste your API key from [platform.openai.com](https://platform.openai.com)
- **Ollama (local)** — no API key needed; make sure Ollama is running (`ollama serve`)
- **Custom endpoint** — enter your endpoint URL and API key if required

### API Key Storage

Your API key is stored in Blender's user preferences file on your machine. It is never written into `.blend` files. You can also set it via environment variable:

```bash
# Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export OPENAI_API_KEY="sk-..."
```

### Safety Settings

| Setting | Default | Description |
|---|---|---|
| Sandbox AI Code | On | Scans generated code for dangerous patterns before running |
| Auto-Execute | Off | When off, code is staged for your review before execution |
| Confirm Before Modifying | On | Shows a confirmation dialog if objects are selected |

---

## Usage

1. Open the **N-panel** in the 3D Viewport by pressing **N**.
2. Click the **AI Assistant** tab.
3. Type a prompt in the text box, for example:
   - `Add a low-poly mountain range with 5 peaks`
   - `Create a procedural brick wall material on the selected object`
   - `Set up a Geometry Nodes scatter of rocks across the active plane`
4. Optionally enable **Include Scene Context** to give the AI awareness of your existing objects.
5. Click **Send to AI**.
6. The AI response and generated code appear in the **AI Response** and **Generated Code** panels.
7. Review the code preview, then click **▶ Execute** to run it.

### Tips

- Keep prompts specific — mention object names, target locations, or material names that already exist in your scene.
- Use the conversation history to iterate: `make the sphere larger` or `add a subdivision surface modifier to it` will work in follow-up messages.
- Click **Copy Code** to paste generated code into Blender's Text Editor for manual editing before running.
- Click **Clear Conversation** to start a fresh context.

---

## Project Structure

```
blender_ai_assistant/
├── __init__.py              # Add-on entry point, dependency bootstrap
├── preferences.py           # API keys, model selection, safety settings
├── operators/
│   └── __init__.py          # Operators: send prompt, execute code, clear history
├── panels/
│   └── __init__.py          # Sidebar UI panels
├── utils/
│   ├── ai_client.py         # HTTP client for Claude / OpenAI / Ollama
│   ├── sandbox.py           # AST scanner and restricted code executor
│   └── scene_context.py     # Serialises the Blender scene to JSON
└── assets/
    └── example_prompts.py   # Reference AI-generated code snippets
```

---

## Security

AI-generated code runs through a **soft sandbox** before execution:

- **Static analysis** — the AST is scanned for banned imports (`os`, `sys`, `subprocess`, `socket`, `ctypes`, and more) and dangerous `bpy` operations (`wm.quit_blender`, `preferences.addon_install`, etc.)
- **Restricted builtins** — code runs with a reduced set of Python builtins; `open`, `eval`, `exec`, and `__import__` are not available
- **Execution timeout** — a 30-second watchdog prevents infinite loops from hanging Blender
- **Namespace isolation** — code runs in a fresh namespace with only `bpy`, `mathutils`, and `math` available

> **Note:** This is a best-effort sandbox. It is not a hard security boundary. Do not run prompts from untrusted sources with the sandbox disabled. For fully untrusted input, the codebase includes a documented pattern for subprocess isolation.

---

## Running the Tests

The sandbox unit tests can be run without Blender:

```bash
python test_sandbox.py
```

All 15 tests should pass, covering static analysis, safe execution, violation detection, and timeout enforcement.

---

## Local LLM with Ollama

To use the add-on fully offline:

1. Install Ollama from [ollama.com](https://ollama.com).
2. Pull a code-capable model:
   ```bash
   ollama pull codellama
   # or
   ollama pull llama3
   ```
3. Start the server:
   ```bash
   ollama serve
   ```
4. In Blender preferences, set **AI Provider** to **Ollama** and set the model name to match what you pulled.

Cloud models (Claude, GPT-4) will produce significantly better Blender Python code than most local models. `codellama` is the recommended local option for this use case.

---

## Contributing

Contributions are welcome. Please open an issue before submitting a pull request for large changes.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "Add my feature"`
4. Push and open a pull request

---

## License

This project is licensed under the **GNU General Public License v3.0 or later**.
See the [LICENSE](LICENSE) file for the full text.

```
Copyright (C) 2026 Dilek ISIK AKCAKAYA, PhD

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
```
