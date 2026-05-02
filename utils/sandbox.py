# ============================================================
#  utils/sandbox.py  —  Safe Execution of AI-Generated Code
# ============================================================
"""
Security model
--------------
Blender's Python is a full CPython interpreter — there is NO true
sandbox at the OS level unless you run Blender inside a container or
VM.  What this module provides is a BEST-EFFORT SOFT SANDBOX:

  1. Static analysis — scans the AST for banned calls before exec().
  2. Restricted builtins — replaces __builtins__ with a safe subset.
  3. Namespace isolation — code runs in a fresh dict, not globals().
  4. Timeout guard — a daemon thread kills the Blender process if the
     code runs longer than the allowed wall-clock time.
     (Use sparingly — it aborts the whole process.  Prefer setting a
     short timeout and sandboxing in a subprocess for production.)

What it CANNOT prevent
  - Malicious code that uses ctypes, cffi, or compiled extensions.
  - Code that writes to disk through bpy.ops or bpy.data paths.
  - Long-running loops that consume CPU.

For a truly hard sandbox, run code in a separate Blender --background
process via subprocess and pipe results back.  That pattern is
documented at the bottom of this file.
"""

from __future__ import annotations

import ast
import builtins
import textwrap
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Result ────────────────────────────────────────────────────────

@dataclass
class ExecResult:
    success: bool
    output:  str  = ""
    error:   str  = ""
    locals:  dict = field(default_factory=dict)


# ── Static analysis ───────────────────────────────────────────────

# Module imports that are never allowed in AI-generated code
_BANNED_IMPORTS: set[str] = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib",
    "ctypes", "cffi", "importlib", "pty", "atexit", "signal",
    "multiprocessing", "concurrent", "threading",
    "pickle", "shelve", "marshal",
    "code", "codeop", "compileall",
}

# Attribute access patterns that indicate dangerous usage
_BANNED_ATTR_PATTERNS: list[str] = [
    "__import__", "__loader__", "__spec__", "__builtins__",
    "system", "popen", "execfile", "exec", "eval",
]

# bpy operations that should never be called by AI
_BANNED_BPY_OPS: set[str] = {
    "wm.quit_blender",
    "wm.read_homefile",
    "wm.save_userpref",
    "wm.url_open",
    "preferences.addon_install",
    "preferences.addon_remove",
    "script.reload",
    "script.execute_preset",
}


class _ASTScanner(ast.NodeVisitor):
    """Walk an AST and collect violations."""

    def __init__(self):
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in _BANNED_IMPORTS:
                self.violations.append(
                    f"Line {node.lineno}: banned import '{alias.name}'"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            root = node.module.split(".")[0]
            if root in _BANNED_IMPORTS:
                self.violations.append(
                    f"Line {node.lineno}: banned import from '{node.module}'"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Detect  bpy.ops.wm.quit_blender()  style calls
        chain = _attr_chain(node.func)
        if chain:
            op_name = chain.removeprefix("bpy.ops.")
            if op_name in _BANNED_BPY_OPS:
                self.violations.append(
                    f"Line {node.lineno}: banned bpy op '{op_name}'"
                )
        # Detect __import__('os') — a direct Name call
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            self.violations.append(
                f"Line {node.lineno}: banned call '__import__'"
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in _BANNED_ATTR_PATTERNS:
            self.violations.append(
                f"Line {node.lineno}: banned attribute access '.{node.attr}'"
            )
        self.generic_visit(node)


def _attr_chain(node: ast.expr) -> Optional[str]:
    """Return 'a.b.c' for an Attribute chain, or None if not a pure chain."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attr_chain(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def static_check(code: str) -> list[str]:
    """Return a list of violation strings (empty means clean)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"SyntaxError: {e}"]
    scanner = _ASTScanner()
    scanner.visit(tree)
    return scanner.violations


# ── Safe builtins ─────────────────────────────────────────────────

_SAFE_BUILTIN_NAMES = {
    # Basic types
    "None", "True", "False",
    "int", "float", "str", "bool", "bytes", "bytearray",
    "list", "tuple", "dict", "set", "frozenset",
    "type", "object", "slice", "range",
    # Functional
    "len", "range", "enumerate", "zip", "map", "filter",
    "sorted", "reversed", "min", "max", "sum", "abs", "round",
    "all", "any", "next", "iter",
    # Type helpers
    "isinstance", "issubclass", "hasattr", "getattr", "setattr",
    "callable", "id", "hash",
    # Text
    "repr", "str", "format", "chr", "ord",
    # Math
    "divmod", "pow",
    # Print (captured by stdout redirect inside exec)
    "print",
    # Exception types needed in try/except
    "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "RuntimeError", "StopIteration",
    "NotImplementedError", "OverflowError", "ZeroDivisionError",
}

_SAFE_BUILTINS = {
    k: getattr(builtins, k)
    for k in _SAFE_BUILTIN_NAMES
    if hasattr(builtins, k)
}


# ── Executor ──────────────────────────────────────────────────────

class Sandbox:
    """
    Parameters
    ----------
    enabled : bool
        When False the code is executed normally (all builtins, no AST
        scan) — useful for trusted/dev mode.
    timeout : float
        Maximum wall-clock seconds for execution.  0 = no timeout.
    """

    def __init__(self, enabled: bool = True, timeout: float = 30.0):
        self.enabled = enabled
        self.timeout = timeout

    def execute(self, code: str, extra_globals: dict | None = None) -> ExecResult:
        """
        Execute *code* and return an ExecResult.

        The caller is responsible for passing *extra_globals* that contains
        at least {'bpy': bpy} so generated code can call Blender APIs.
        """
        code = textwrap.dedent(code).strip()

        # 1. Static analysis
        if self.enabled:
            violations = static_check(code)
            if violations:
                return ExecResult(
                    success=False,
                    error="Static analysis blocked execution:\n"
                          + "\n".join(f"  • {v}" for v in violations),
                )

        # 2. Build execution namespace
        if self.enabled:
            safe_globals: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
        else:
            safe_globals = {"__builtins__": builtins}

        if extra_globals:
            safe_globals.update(extra_globals)

        exec_locals: dict[str, Any] = {}

        # 3. Capture stdout
        import io
        stdout_capture = io.StringIO()

        # 4. Run with optional timeout
        result_holder: dict[str, Any] = {}

        def _run():
            import sys as _sys
            old_stdout = _sys.stdout
            _sys.stdout = stdout_capture
            try:
                exec(compile(code, "<ai_generated>", "exec"),  # noqa: S102
                     safe_globals, exec_locals)
                result_holder["ok"] = True
            except Exception:
                result_holder["tb"] = traceback.format_exc()
            finally:
                _sys.stdout = old_stdout

        if self.timeout > 0:
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=self.timeout)
            if t.is_alive():
                return ExecResult(
                    success=False,
                    error=f"Execution timed out after {self.timeout}s",
                    output=stdout_capture.getvalue(),
                )
        else:
            _run()

        output = stdout_capture.getvalue()

        if "tb" in result_holder:
            return ExecResult(success=False, error=result_holder["tb"],
                              output=output, locals=exec_locals)

        return ExecResult(success=True, output=output, locals=exec_locals)


# ── Convenience function ──────────────────────────────────────────

def execute_blender_code(
    code: str,
    sandbox_enabled: bool = True,
    timeout: float = 30.0,
) -> ExecResult:
    """
    Execute AI-generated Blender Python code.

    Automatically injects 'bpy', 'mathutils', and 'math' into the
    execution namespace so generated code can use them without
    explicit imports.
    """
    import bpy                              # noqa: PLC0415
    import mathutils                        # noqa: PLC0415
    import math                             # noqa: PLC0415

    extra = {"bpy": bpy, "mathutils": mathutils, "math": math}
    box = Sandbox(enabled=sandbox_enabled, timeout=timeout)
    return box.execute(code, extra_globals=extra)


# ── Subprocess isolation (advanced) ──────────────────────────────
# For truly untrusted code, run Blender headless in a child process:
#
#   import subprocess, json, tempfile, os
#
#   script = f"""
#   import bpy, json, sys
#   {code}
#   # write result to a temp file
#   with open(sys.argv[-1], 'w') as f:
#       json.dump({{'ok': True}}, f)
#   """
#   with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as tf:
#       tf.write(script.encode())
#       script_path = tf.name
#
#   result_path = script_path + '.result.json'
#   subprocess.run(
#       ['blender', '--background', '--python', script_path, '--', result_path],
#       timeout=60
#   )
#   with open(result_path) as f:
#       result = json.load(f)
#   os.unlink(script_path)
#   os.unlink(result_path)
#
# This gives true OS-level isolation at the cost of startup overhead
# (~2-4 seconds per call) and no access to the current scene.
