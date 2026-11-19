"""Shoot fresh turntable footage from the current PingBlip models in Blender."""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
MODELS = ROOT.parents[1] / 'pingblip/memeforge/public/models'
CREATURES = ['taxi-larva', 'rain-pigeon', 'button-spider', 'caramel-bust',
             'lollipop-golem', 'sour-worm', 'tongs-golem', 'winged-bolt', 'mirror-idol']
if '--' in sys.argv:
    CREATURES = sys.argv[sys.argv.index('--')+1:]

for slug in CREATURES:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(MODELS / f'{slug}.glb'))
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    originals = list(scene.objects)
    points = [obj.matrix_world @ Vector(point) for obj in originals
              if obj.type == 'MESH' for point in obj.bound_box]
    lower = Vector([min(p[i] for p in points) for i in range(3)])
    upper = Vector([max(p[i] for p in points) for i in range(3)])
    center = (lower + upper) / 2
    span = max(upper - lower)
    root = bpy.data.objects.new('Turntable', None)
    scene.collection.objects.link(root)
    root.location = center
    bpy.context.view_layer.update()
    for obj in originals:
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world

    def aim(obj):
        obj.rotation_euler = (center - obj.location).to_track_quat('-Z', 'Y').to_euler()

    cam_data = bpy.data.cameras.new('Portrait camera')
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = span * 1.46
    cam = bpy.data.objects.new('Portrait camera', cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + Vector((.05, -3.2, .18)) * span
    aim(cam)
    scene.camera = cam
    for name, offset, energy, color in [
        ('Warm key', (-1.8,-2.4,2.5), 320, (1,.91,.78)),
        ('Cool fill', (2,-1.6,.7), 115, (.73,.85,1)),
        ('Edge', (.45,1.3,2), 390, (1,.70,.80)),
    ]:
        light = bpy.data.lights.new(name, 'AREA')
        light.energy = energy * span**2
        light.size = span * 1.7
        light.color = color
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = center + Vector(offset) * span
        aim(obj)

    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 8
    scene.render.resolution_x = 520
    scene.render.resolution_y = 600
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.compression = 12
    scene.view_settings.view_transform = 'AgX'
    output = ROOT / 'work' / slug
    output.mkdir(parents=True, exist_ok=True)
    for n in range(24):
        phase = n / 24 * 2 * math.pi
        if (output / f'{n:03d}.png').exists():
            continue
        root.rotation_euler = (0, math.radians(4) * math.sin(phase), math.radians(29) * math.sin(phase))
        scene.render.filepath = str(output / f'{n:03d}.png')
        bpy.ops.render.render(write_still=True)
    print('SHOT', slug, flush=True)
