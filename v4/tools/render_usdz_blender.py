"""Blender-side canonical USDZ conditioning renderer. Run with Blender --python."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, default=768)
    return parser.parse_args(values)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def look_at(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def compositor(scene, root, near, far):
    tree = bpy.data.node_groups.new("SceneFactoryCompositor", "CompositorNodeTree")
    scene.compositing_node_group = tree
    layers = tree.nodes.new("CompositorNodeRLayers")

    def output_node(name, folder, mode="PNG", color="BW", depth="16"):
        node = tree.nodes.new("CompositorNodeOutputFile")
        node.name = name
        node.directory = str(root / folder)
        node.file_name = f"{name}_"
        # Blender 5 chooses the on-disk type from the socket as well as the
        # requested format. A FLOAT socket silently forced OpenEXR even when
        # PNG was requested, so use an RGBA image socket for all display maps.
        item = node.file_output_items.new("RGBA", "Image")
        item.override_node_format = True
        item.format.file_format = mode
        item.format.color_mode = color
        item.format.color_depth = depth
        if mode == "OPEN_EXR":
            item.format.exr_codec = "ZIP"
        return node

    alpha = output_node("alpha", "alpha")
    silhouette = output_node("silhouette", "silhouette")
    tree.links.new(layers.outputs["Alpha"], alpha.inputs["Image"])
    tree.links.new(layers.outputs["Alpha"], silhouette.inputs["Image"])

    metric = output_node("metric_depth", "depth_metric", "OPEN_EXR", "BW", "32")
    tree.links.new(layers.outputs["Depth"], metric.inputs["Image"])
    depth_map = tree.nodes.new("ShaderNodeMapRange")
    depth_map.inputs[1].default_value = near
    depth_map.inputs[2].default_value = far
    depth_map.inputs[3].default_value = 1.0
    depth_map.inputs[4].default_value = 0.0
    tree.links.new(layers.outputs["Depth"], depth_map.inputs[0])
    normalized = output_node("normalized_depth", "depth_normalized")
    tree.links.new(depth_map.outputs[0], normalized.inputs["Image"])

    multiply = tree.nodes.new("ShaderNodeVectorMath")
    multiply.operation = "SCALE"
    multiply.inputs[3].default_value = 0.5
    tree.links.new(layers.outputs["Normal"], multiply.inputs[0])
    add = tree.nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    add.inputs[1].default_value = (0.5, 0.5, 0.5)
    tree.links.new(multiply.outputs[0], add.inputs[0])
    normals = output_node("normals", "normals", "PNG", "RGB", "16")
    tree.links.new(add.outputs[0], normals.inputs["Image"])
    return {node.name: node for node in (alpha, silhouette, metric, normalized, normals)}


def convert_display_passes(scene, root, name):
    """Use Blender's EXR decoder, avoiding host FFmpeg codec limitations."""
    for folder, color_mode in (
        ("alpha", "BW"),
        ("silhouette", "BW"),
        ("depth_normalized", "BW"),
        ("normals", "RGB"),
    ):
        matches = sorted((root / folder).glob(f"{name}_*.exr"))
        if len(matches) != 1:
            raise RuntimeError(f"expected one {folder} EXR for {name}, found {len(matches)}")
        source = matches[0]
        image = bpy.data.images.load(str(source), check_existing=False)
        image.colorspace_settings.name = "Non-Color"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = color_mode
        scene.render.image_settings.color_depth = "16"
        image.save_render(str((root / folder / name).with_suffix(".png")), scene=scene)
        bpy.data.images.remove(image)
        source.unlink()


def main():
    args = parse_args()
    source = args.source.resolve()
    root = args.output.resolve()
    for folder in ("rgb", "alpha", "silhouette", "depth_metric", "depth_normalized", "normals"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    result = bpy.ops.wm.usd_import(filepath=str(source))
    if "FINISHED" not in result:
        raise RuntimeError(f"USD import failed: {result}")
    meshes = [item for item in bpy.context.scene.objects if item.type == "MESH"]
    if not meshes:
        raise RuntimeError("USDZ contains no imported meshes")
    corners = []
    for obj in meshes:
        corners.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    minimum = Vector((min(point.x for point in corners), min(point.y for point in corners), min(point.z for point in corners)))
    maximum = Vector((max(point.x for point in corners), max(point.y for point in corners), max(point.z for point in corners)))
    center = (minimum + maximum) / 2
    extent = maximum - minimum
    radius = max(extent.length / 2, 0.001)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.size
    scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "16"
    scene.render.film_transparent = True
    scene.render.image_settings.compression = 50
    scene.render.engine = "BLENDER_EEVEE"
    view_layer = scene.view_layers[0]
    view_layer.use_pass_z = True
    view_layer.use_pass_normal = True

    camera_data = bpy.data.cameras.new("SceneFactoryCanonicalCamera")
    camera_data.lens = 70.0
    camera_data.sensor_width = 36.0
    camera = bpy.data.objects.new("SceneFactoryCanonicalCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    distance = radius / math.tan(math.radians(26.0) / 2) * 1.15
    camera.data.clip_start = max(radius * 0.01, 0.0001)
    camera.data.clip_end = distance + radius * 4

    world = bpy.data.worlds.new("SceneFactoryWorld") if scene.world is None else scene.world
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.18, 0.18, 0.18, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    light_data = bpy.data.lights.new("SceneFactoryKey", "AREA")
    light_data.energy = 1200
    light_data.shape = "DISK"
    light_data.size = radius * 2
    light = bpy.data.objects.new("SceneFactoryKey", light_data)
    scene.collection.objects.link(light)
    light.location = center + Vector((radius * 2, -radius * 2, radius * 3))
    look_at(light, center)

    outputs = compositor(scene, root, camera.data.clip_start, camera.data.clip_end)
    views = []
    for index, azimuth in enumerate(range(0, 360, 45), 1):
        radians = math.radians(azimuth)
        camera.location = center + Vector((math.sin(radians) * distance, -math.cos(radians) * distance, extent.z * 0.05))
        look_at(camera, center)
        frame = index
        scene.frame_set(frame)
        name = f"view_{azimuth:03d}"
        scene.render.filepath = str(root / "rgb" / f"{name}.png")
        for node in outputs.values():
            node.file_name = f"{name}_"
        bpy.ops.render.render(write_still=True)
        convert_display_passes(scene, root, name)
        views.append({
            "name": name,
            "azimuth_degrees": azimuth,
            "camera_location": list(camera.location),
            "camera_rotation_euler": list(camera.rotation_euler),
            "lens_mm": camera.data.lens,
            "sensor_width_mm": camera.data.sensor_width,
            "clip_start": camera.data.clip_start,
            "clip_end": camera.data.clip_end,
            "frame": frame,
        })
    manifest = {
        "schema_version": 4,
        "renderer": {"name": "Blender", "version": bpy.app.version_string, "engine": scene.render.engine},
        "source": {"path": str(source), "sha256": sha256(source)},
        "mesh": {
            "object_count": len(meshes), "objects": [obj.name for obj in meshes],
            "vertex_count": sum(len(obj.data.vertices) for obj in meshes),
            "polygon_count": sum(len(obj.data.polygons) for obj in meshes),
            "materials": sorted({slot.material.name for obj in meshes for slot in obj.material_slots if slot.material}),
            "bounds_min": list(minimum), "bounds_max": list(maximum), "extent": list(extent), "center": list(center),
        },
        "resolution": [args.size, args.size],
        "normal_space": "blender_render_normal_pass",
        "metric_depth_format": "OpenEXR 32-bit scene depth",
        "views": views,
    }
    (root / "render_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


main()
