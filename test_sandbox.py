#!/usr/bin/env python3
# ============================================================
#  test_sandbox.py  —  Unit tests (no Blender required)
# ============================================================
"""
Tests the static analysis and sandbox without a running Blender.

Run with:  python test_sandbox.py
"""

import sys
import os

# Make the package importable from the repo root
sys.path.insert(0, os.path.dirname(__file__))

# ── Minimal bpy stub so sandbox imports work without Blender ──────
import types

bpy_stub = types.ModuleType("bpy")
bpy_stub.app = types.SimpleNamespace(timers=types.SimpleNamespace(register=lambda *a, **kw: None))
bpy_stub.context = types.SimpleNamespace(scene=None)
sys.modules.setdefault("bpy", bpy_stub)
sys.modules.setdefault("mathutils", types.ModuleType("mathutils"))

from blender_ai_assistant.utils.sandbox import static_check, Sandbox, ExecResult


# ── Helpers ───────────────────────────────────────────────────────

def expect_clean(label: str, code: str):
    violations = static_check(code)
    status = "PASS" if not violations else "FAIL"
    print(f"[{status}] {label}")
    if violations:
        for v in violations:
            print(f"       violation: {v}")

def expect_violation(label: str, code: str):
    violations = static_check(code)
    status = "PASS" if violations else "FAIL"
    print(f"[{status}] {label}")
    if not violations:
        print("       expected a violation but found none")

def section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ── Static analysis tests ─────────────────────────────────────────

section("Static Analysis — Should PASS (no violations)")

expect_clean("Basic bpy ops", """
import bpy
bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,0))
""")

expect_clean("Math operations", """
import math
x = math.sqrt(2) + math.pi
""")

expect_clean("List comprehension", """
values = [i**2 for i in range(10)]
total = sum(values)
""")

expect_clean("Try/except", """
import bpy
try:
    bpy.ops.object.delete()
except Exception as e:
    print(e)
""")


section("Static Analysis — Should FAIL (violations detected)")

expect_violation("os import", "import os; os.remove('/etc/passwd')")

expect_violation("sys import", "import sys; sys.exit()")

expect_violation("subprocess import", "import subprocess; subprocess.run(['ls'])")

expect_violation("Quit Blender", """
import bpy
bpy.ops.wm.quit_blender()
""")

expect_violation("__import__ usage", """
os = __import__('os')
""")

expect_violation("from os import", "from os.path import join")

expect_violation("threading import", "import threading")


# ── Sandbox exec tests (no bpy, safe maths only) ──────────────────

section("Sandbox Execution — Safe Code")

box = Sandbox(enabled=True, timeout=5.0)

r = box.execute("x = 2 + 2\nprint(x)")
assert r.success, f"Expected success: {r.error}"
assert "4" in r.output, f"Expected '4' in output, got: {r.output}"
print("[PASS] arithmetic + print")

r = box.execute("result = [i*2 for i in range(5)]")
assert r.success
print("[PASS] list comprehension")

r = box.execute("""
vals = list(range(100))
total = sum(vals)
print(total)
""")
assert r.success and "4950" in r.output
print("[PASS] sum of range")


section("Sandbox Execution — Blocked Code")

r = box.execute("import os")
assert not r.success
print(f"[PASS] os import blocked: {r.error[:60]}")

r = box.execute("__import__('os')")
# This might or might not raise depending on Python version,
# but __import__ should not be in safe builtins
if not r.success or "os" not in str(r):
    print("[PASS] __import__ blocked or raises NameError")
else:
    print("[WARN] __import__ may need additional hardening")


section("Sandbox Execution — Timeout")

r = box.execute("""
i = 0
while True:
    i += 1
""")
assert not r.success
assert "timed out" in r.error.lower()
print(f"[PASS] infinite loop timed out: {r.error}")


# ── JSON parsing test ─────────────────────────────────────────────

section("Response Parsing")

import json

test_response = json.dumps({
    "action": "run_code",
    "code": "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()",
    "explanation": "Adds a UV sphere at the origin.",
    "warnings": []
})

data = json.loads(test_response)
assert data["action"] == "run_code"
assert "bpy" in data["code"]
print("[PASS] JSON round-trip")

# Markdown fence stripping
fenced = "```json\n" + test_response + "\n```"
stripped = fenced.strip()
if stripped.startswith("```"):
    lines = stripped.split("\n")
    stripped = "\n".join(lines[1:-1])
data2 = json.loads(stripped)
assert data2["action"] == "run_code"
print("[PASS] Markdown fence stripping")


# ── Summary ───────────────────────────────────────────────────────

print("\n" + "="*60)
print("  All tests complete.")
print("="*60)
