"""Grain geometry and a render-only dust layer sourced from the rigid grains."""

import math

import bmesh
import bpy
from mathutils import Vector


def grain_material(name, materials):
    base = next((mat.diffuse_color for mat in materials if mat is not None),
                (0.42, 0.29, 0.17, 1.0))
    color = (*(0.82 * c + 0.18 * tint for c, tint in zip(base, (0.42, 0.29, 0.17))), 1.0)
    mat = bpy.data.materials.new(name)
    mat["ua_sand_material"] = True
    mat.diffuse_color = color
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    surface = nodes.new("ShaderNodeBsdfPrincipled")
    surface.inputs["Base Color"].default_value = color
    surface.inputs["Roughness"].default_value = 0.87
    links.new(surface.outputs[0], output.inputs["Surface"])
    return mat


def grain_mesh(name, material, radius, variant):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=radius)
        for i, vert in enumerate(bm.verts):
            vert.co *= 0.82 + 0.18 * math.sin(i * 2.31 + variant)
            vert.co.y *= 0.79 + 0.08 * variant
            vert.co.z *= 0.73 + 0.09 * variant
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.materials.append(material)
    return mesh


def sample_centers(mesh, count, rng, inset, *, cut_faces=False):
    """Area-weighted samples on the parent section's outside, not its caps."""
    mesh.calc_loop_triangles()
    faces = [tri for tri in mesh.loop_triangles if tri.area > 1e-12]
    if cut_faces:
        shell = [tri for tri in faces if tri.material_index < len(mesh.materials) - 1]
        faces = shell or faces
    else:
        faces = list(faces)
    if not faces:
        raise ValueError("环网格没有可用于生成沙粒的表面")
    for tri in rng.choices(faces, weights=[tri.area for tri in faces], k=count):
        a, b, c = (mesh.vertices[i].co for i in tri.vertices)
        u, v = math.sqrt(rng.random()), rng.random()
        yield (1 - u) * a + u * ((1 - v) * b + v * c) - inset * tri.normal


def _dust_mesh():
    mesh = next((m for m in bpy.data.meshes if m.get("ua_sand_volume_mesh")), None)
    if mesh is not None:
        return mesh
    mesh = bpy.data.meshes.new("UA_SandVolume")
    mesh["ua_sand_volume_mesh"] = True
    bm = bmesh.new()
    try:
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mat = bpy.data.materials.new("UA_SandVolume")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    volume = nodes.new("ShaderNodeVolumePrincipled")
    volume.inputs["Color"].default_value = (0.59, 0.48, 0.35, 1)
    volume.inputs["Anisotropy"].default_value = 0.18
    coord = nodes.new("ShaderNodeTexCoord")
    length = nodes.new("ShaderNodeVectorMath")
    length.operation = "LENGTH"
    falloff = nodes.new("ShaderNodeMapRange")
    falloff.interpolation_type = "SMOOTHSTEP"
    falloff.inputs["From Min"].default_value = 0.08
    falloff.inputs["From Max"].default_value = 0.86
    falloff.inputs["To Min"].default_value = 1.0
    falloff.inputs["To Max"].default_value = 0.0
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.5
    density = nodes.new("ShaderNodeMath")
    density.operation = "MULTIPLY"
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 26.0
    links.new(coord.outputs["Object"], length.inputs[0])
    links.new(coord.outputs["Object"], noise.inputs["Vector"])
    links.new(length.outputs["Value"], falloff.inputs["Value"])
    links.new(falloff.outputs[0], density.inputs[0])
    links.new(noise.outputs["Fac"], density.inputs[1])
    links.new(density.outputs[0], gain.inputs[0])
    links.new(gain.outputs[0], volume.inputs["Density"])
    links.new(volume.outputs[0], output.inputs["Volume"])
    mesh.materials.append(mat)
    return mesh


def add_dust(coll, ring, grains, created, *, fps, radius, set_hidden):
    """Each puff follows its own grain's actual world-space rigid-body motion."""
    mesh = _dust_mesh()
    stride = max(1, math.ceil(len(grains) / 48))
    for i, grain in enumerate(grains[::stride]):
        start = int(grain["ua_release_frame"])
        length = max(4, round((0.43 + 0.035 * (i % 5)) * fps))
        end = start + length
        obj = bpy.data.objects.new(f"{ring.name}·扬尘 {i + 1:02d}", mesh)
        created.append(obj)
        obj["rp_kind"] = "shard"
        obj["rp_ring"] = ring["rp_id"]
        obj["ua_sand_dust"] = True
        obj["ua_dust_source"] = grain
        obj["ua_release_frame"] = start
        obj["ua_dust_end"] = end
        obj.display_type = "WIRE"
        coll.objects.link(obj)
        follow = obj.constraints.new("COPY_LOCATION")
        follow.target = grain
        follow.use_offset = True
        follow.target_space = follow.owner_space = "WORLD"
        drift = Vector((math.sin(i * 2.3), math.cos(i * 1.8), 0.55)) * radius * 3.4
        for offset, size, travel in ((0, 0.45, 0), (length // 2, 3.2, 0.5),
                                     (length - 1, 0.03, 1.0)):
            obj.location = drift * travel
            obj.scale = (radius * size,) * 3
            for path in ("location", "scale"):
                obj.keyframe_insert(data_path=path, frame=start + offset)
        set_hidden(obj, start - 1, True)
        set_hidden(obj, start, False)
        set_hidden(obj, end, True)
