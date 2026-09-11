"""Build a deterministic rigged talking-head export and a matching Gaussian PLY.

This is a delivery-stage adapter for static USDZ captures. It does not pretend that
the source scans contain a rig: it creates an explicit lightweight head rig and
viseme blend-shapes, records that fact, and preserves the imported materials/textures
in the exported USD package where Blender's USD exporter supports them.
"""

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector


VISEME_NAMES = (
    "jawOpen", "mouthClose", "mouthSmileLeft", "mouthSmileRight",
    "mouthFunnel", "mouthPucker", "viseme_PP", "viseme_FF", "viseme_TH",
    "viseme_DD", "viseme_KK", "viseme_CH", "viseme_SS", "viseme_NN",
    "viseme_RR", "viseme_AA", "viseme_E", "viseme_I", "viseme_O", "viseme_U",
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def args():
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--identity", default="identity")
    return parser.parse_args(values)


def import_meshes(source):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    result = bpy.ops.wm.usd_import(filepath=str(source))
    if "FINISHED" not in result:
        raise RuntimeError(f"USD import failed: {result}")
    meshes = [item for item in bpy.context.scene.objects if item.type == "MESH"]
    if not meshes:
        raise RuntimeError("USDZ contains no meshes")
    return meshes


def bounds(meshes):
    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def add_rig(meshes, low, high):
    # Put a simple facial rig in scan coordinates. Bone and weight names are stable
    # so downstream retargeting can use the manifest without inspecting Blender.
    bpy.ops.object.armature_add( location=(0, 0, low.z))
    armature = bpy.context.object
    armature.name = "SceneFactoryHeadRig"
    data = armature.data
    data.name = "SceneFactoryHeadRig"
    bpy.ops.object.mode_set(mode="EDIT")
    data.edit_bones.remove(data.edit_bones[0])
    def bone(name, head, tail, parent=None):
        item = data.edit_bones.new(name)
        item.head, item.tail = head, tail
        if parent:
            item.parent = data.edit_bones.get(parent)
        return item
    height = max(high.z - low.z, 0.01)
    center = (low + high) / 2
    bone("root", (center.x, center.y, low.z), (center.x, center.y, low.z + height * 0.25))
    bone("neck", (center.x, center.y, low.z + height * 0.20), (center.x, center.y, low.z + height * 0.48), "root")
    bone("head", (center.x, center.y, low.z + height * 0.42), (center.x, center.y, high.z), "neck")
    bone("jaw", (center.x, center.y, low.z + height * 0.25), (center.x, center.y, low.z + height * 0.38), "head")
    bone("eye.L", (center.x - (high.x-low.x)*0.16, low.y, low.z + height*0.57), (center.x - (high.x-low.x)*0.16, low.y, low.z + height*0.63), "head")
    bone("eye.R", (center.x + (high.x-low.x)*0.16, low.y, low.z + height*0.57), (center.x + (high.x-low.x)*0.16, low.y, low.z + height*0.63), "head")
    bpy.ops.object.mode_set(mode="OBJECT")
    for mesh in meshes:
        bpy.context.view_layer.objects.active = mesh
        mesh.select_set(True)
        modifier = mesh.modifiers.new("SceneFactoryHeadRig", "ARMATURE")
        modifier.object = armature
        for name in ("root", "neck", "head", "jaw", "eye.L", "eye.R"):
            mesh.vertex_groups.new(name=name)
        # A stable head weight keeps the static scan usable while facial blend
        # shapes carry expression. The jaw receives a smooth lower-face influence.
        for vertex in mesh.data.vertices:
            z = mesh.matrix_world @ vertex.co
            t = max(0.0, min(1.0, (z.z - low.z) / max(high.z - low.z, 1e-6)))
            mesh.vertex_groups["head"].add([vertex.index], 1.0, "REPLACE")
            if t < 0.40:
                mesh.vertex_groups["jaw"].add([vertex.index], min(1.0, (0.40 - t) * 3.0), "REPLACE")
    return armature


def add_blend_shapes(meshes, low, high):
    # Blend-shapes are generated in object coordinates from the imported scan. The
    # formulas are deliberately bounded and auditable rather than random sculpting.
    width = max(high.x - low.x, 0.01)
    height = max(high.z - low.z, 0.01)
    mouth_z = low.z + height * 0.34
    for mesh in meshes:
        if not mesh.data.shape_keys:
            mesh.shape_key_add(name="Basis")
        for name in VISEME_NAMES:
            key = mesh.shape_key_add(name=name)
            for point, vertex in zip(key.data, mesh.data.vertices):
                world = mesh.matrix_world @ vertex.co
                x = (world.x - (low.x + high.x) / 2) / width
                z = (world.z - mouth_z) / height
                region = math.exp(-((x / 0.42) ** 2) - ((z / 0.16) ** 2))
                delta = Vector((0, 0, 0))
                if name == "jawOpen":
                    delta.z = -0.06 * height * region
                elif name == "mouthClose":
                    delta.z = 0.025 * height * region
                elif "Smile" in name:
                    side = -1 if name.endswith("Left") else 1
                    delta.x = side * 0.018 * width * region
                    delta.z = 0.022 * height * region
                elif name in {"mouthFunnel", "mouthPucker"}:
                    delta.y = -0.018 * width * region
                elif name.startswith("viseme_"):
                    delta.z = (0.012 if name in {"viseme_AA", "viseme_E", "viseme_I"} else -0.008) * height * region
                point.co = vertex.co + delta


def write_gaussian_ply(meshes, path, low, high):
    vertices = []
    for mesh in meshes:
        color = (0.62, 0.40, 0.30)
        if mesh.data.materials and mesh.data.materials[0]:
            color = tuple(mesh.data.materials[0].diffuse_color[:3])
        for vertex in mesh.data.vertices:
            co = mesh.matrix_world @ vertex.co
            normal = mesh.matrix_world.to_3x3() @ vertex.normal
            vertices.append((co, normal.normalized(), color))
    header = [
        "ply", "format binary_little_endian 1.0", f"element vertex {len(vertices)}",
        "property float x", "property float y", "property float z",
        "property float nx", "property float ny", "property float nz",
        "property float f_dc_0", "property float f_dc_1", "property float f_dc_2",
        "property float opacity", "property float scale_0", "property float scale_1", "property float scale_2",
        "property float rot_0", "property float rot_1", "property float rot_2", "property float rot_3", "end_header",
    ]
    with path.open("wb") as stream:
        stream.write(("\n".join(header) + "\n").encode())
        for co, normal, color in vertices:
            stream.write(struct.pack("<fffffffffffffffff", co.x, co.y, co.z, normal.x, normal.y, normal.z,
                                     color[0], color[1], color[2], 1.0, -5.0, -5.0, -5.0, 1.0, 0.0, 0.0, 0.0))
    return len(vertices)


def export_usdz(path):
    # Blender 5 supports direct USDZ output. Keep all imported materials, normals,
    # UVs, textures, animation, and blend-shapes in the export contract.
    bpy.ops.wm.usd_export(
        filepath=str(path), selected_objects_only=False,
        export_animation=True, export_uvmaps=True, export_normals=True,
        export_materials=True, export_armatures=True, export_shapekeys=True,
        # NEW localizes images imported from a USDZ temp extraction directory into
        # the export package; PRESERVE would leave dangling temp-file references.
        export_textures_mode="NEW", overwrite_textures=True, relative_paths=True,
    )


def main():
    config = args()
    source = config.source.resolve()
    root = config.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    meshes = import_meshes(source)
    low, high = bounds(meshes)
    add_rig(meshes, low, high)
    add_blend_shapes(meshes, low, high)
    mesh_path = root / f"{config.identity}_talking_head.usdz"
    splat_path = root / f"{config.identity}_head_gaussian.ply"
    export_usdz(mesh_path)
    vertex_count = write_gaussian_ply(meshes, splat_path, low, high)
    manifest = {
        "schema_version": 1, "identity_id": config.identity,
        "source": {"path": str(source), "sha256": sha256(source)},
        "mesh_usdz": {"path": str(mesh_path), "sha256": sha256(mesh_path), "bytes": mesh_path.stat().st_size,
                      "features": ["geometry", "skeleton", "skin_weights", "blend_shapes", "visemes", "uvs", "textures", "normals", "materials"]},
        "gaussian_splat": {"path": str(splat_path), "sha256": sha256(splat_path), "bytes": splat_path.stat().st_size,
                           "vertex_count": vertex_count, "format": "binary_little_endian_ply_3dgs_fields",
                           "color_source": "imported_material_diffuse_fallback_when_vertex_texture_sampling_unavailable"},
        "rig": {"bones": ["root", "neck", "head", "jaw", "eye.L", "eye.R"], "blend_shapes": list(VISEME_NAMES),
                "weight_policy": "head_full_weight_with_smooth_jaw_override"},
        "voice_viseme_timing": {"status": "pending_supplied_tts_audio", "waveform_hash": None, "alignment_artifact": None},
        "visionos": {"persona_shareplay_native_validation": "not_claimed", "delivery": "pre_recorded_and_postproduction_ready"},
    }
    (root / "avatar_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


main()
