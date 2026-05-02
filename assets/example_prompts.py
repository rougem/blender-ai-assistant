# ============================================================
#  assets/example_prompts.py
#  Not imported by Blender — reference examples only.
# ============================================================
"""
Example AI-generated Blender Python snippets.
These are the kinds of code the LLM should produce when prompted.
They are also useful for testing the sandbox executor independently.

Run standalone:
    python assets/example_prompts.py   (requires bpy — run inside Blender)
"""

# ── 1. Add a UV Sphere with a material ───────────────────────────
ADD_SPHERE = """
import bpy, math

# Deselect all
bpy.ops.object.select_all(action='DESELECT')

# Add sphere
bpy.ops.mesh.primitive_uv_sphere_add(
    radius=1.0,
    location=(0, 0, 0),
    segments=32,
    ring_count=16,
)
sphere = bpy.context.active_object
sphere.name = "AI_Sphere"

# Smooth shading
bpy.ops.object.shade_smooth()

# Create and assign a red material
mat = bpy.data.materials.new(name="AI_Red")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.8, 0.1, 0.1, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.3
    bsdf.inputs["Metallic"].default_value = 0.5

if sphere.data.materials:
    sphere.data.materials[0] = mat
else:
    sphere.data.materials.append(mat)

print(f"Created: {sphere.name}")
"""

# ── 2. Procedural building ────────────────────────────────────────
ADD_BUILDING = """
import bpy, math

bpy.ops.object.select_all(action='DESELECT')

# Base
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
base = bpy.context.active_object
base.name = "AI_Building_Base"
base.scale = (1, 1, 2)
bpy.ops.object.transform_apply(scale=True)

# Roof
bpy.ops.mesh.primitive_cone_add(
    vertices=4, radius1=1.5, radius2=0,
    depth=1.0, location=(0, 0, 4.5),
    rotation=(0, 0, math.radians(45))
)
roof = bpy.context.active_object
roof.name = "AI_Building_Roof"

# Simple grey material
for obj in [base, roof]:
    mat = bpy.data.materials.new(name=f"AI_Mat_{obj.name}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1.0)
    obj.data.materials.append(mat)

print("Building created.")
"""

# ── 3. Geometry Nodes setup ───────────────────────────────────────
ADD_GEO_NODES = """
import bpy

bpy.ops.object.select_all(action='DESELECT')

# Add a plane as the base mesh
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, 0))
obj = bpy.context.active_object
obj.name = "AI_GeoNodes_Plane"

# Add Geometry Nodes modifier
mod = obj.modifiers.new(name="AI_GeometryNodes", type='NODES')

# Create a new node group
ng = bpy.data.node_groups.new(name="AI_ScatterNodes", type='GeometryNodeTree')
mod.node_group = ng

nodes = ng.nodes
links = ng.links

# Input / Output interface (Blender 4.x API)
ng.interface.new_socket("Geometry", in_out='INPUT',  socket_type='NodeSocketGeometry')
ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

# Nodes
input_node  = nodes.new("NodeGroupInput")
output_node = nodes.new("NodeGroupOutput")
scatter     = nodes.new("GeometryNodeDistributePointsOnFaces")
instance    = nodes.new("GeometryNodeInstanceOnPoints")
realize     = nodes.new("GeometryNodeRealizeInstances")
ico         = nodes.new("GeometryNodeMeshIcoSphere")

input_node.location  = (-600, 0)
scatter.location     = (-300, 0)
ico.location         = (-300, -200)
instance.location    = (0, 0)
realize.location     = (300, 0)
output_node.location = (600, 0)

ico.inputs["Radius"].default_value    = 0.05
ico.inputs["Subdivisions"].default_value = 2
scatter.inputs["Density"].default_value  = 20.0

links.new(input_node.outputs["Geometry"],  scatter.inputs["Mesh"])
links.new(scatter.outputs["Points"],       instance.inputs["Points"])
links.new(ico.outputs["Mesh"],             instance.inputs["Instance"])
links.new(instance.outputs["Instances"],   realize.inputs["Geometry"])
links.new(realize.outputs["Geometry"],     output_node.inputs["Geometry"])

print("Geometry Nodes scatter setup complete.")
"""

# ── 4. Subdivide + Displace (modifier stack) ─────────────────────
ADD_TERRAIN = """
import bpy

bpy.ops.object.select_all(action='DESELECT')

bpy.ops.mesh.primitive_grid_add(x_subdivisions=20, y_subdivisions=20,
                                 size=10, location=(0, 0, 0))
terrain = bpy.context.active_object
terrain.name = "AI_Terrain"

# Subdivision Surface for smooth base
sub = terrain.modifiers.new("AI_Subsurf", "SUBSURF")
sub.levels = 2

# Displace modifier + cloud texture
disp = terrain.modifiers.new("AI_Displace", "DISPLACE")
tex  = bpy.data.textures.new("AI_CloudTex", type="CLOUDS")
tex.noise_scale = 2.0
disp.texture        = tex
disp.strength       = 1.5
disp.texture_coords = "LOCAL"

# Green material
mat = bpy.data.materials.new("AI_Grass")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.1, 0.45, 0.1, 1.0)
terrain.data.materials.append(mat)

print("Terrain generated.")
"""


if __name__ == "__main__":
    # Quick self-test (must run inside Blender's Python)
    import sys
    print("Example scripts loaded. Use these as test inputs for the sandbox.")
    for name, code in [
        ("Sphere", ADD_SPHERE),
        ("Building", ADD_BUILDING),
        ("GeoNodes", ADD_GEO_NODES),
        ("Terrain", ADD_TERRAIN),
    ]:
        print(f"\n--- {name} ({len(code)} chars) ---")
        print(code[:120], "…")
