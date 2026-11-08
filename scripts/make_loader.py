# -*- coding: utf-8 -*-
# Dev-time only: draws the traced-D loader's comet into resources/skins/Default/media/loader/comet.apng (committed).
# Needs Pillow; the addon never imports it. Run: python3 scripts/make_loader.py
#
# The look is the TV skin's loader: the D outline (path M29,23H49A31,31 0 0 1 49,85H29Z, stroke 11, round joins, in a
# 0 0 108 108 frame) lit by a 100deg conic wedge (2deg soft edges) turning once every 1.6 s round the frame's centre.
# Kodi decodes an animated PNG once into a texture array and steps it itself, one frame per drawn frame at most, so
# a delay shorter than a 60 Hz frame plays it at the display's pace: 96 frames, one per vsync, 1.6 s a turn at 60 Hz.
# (A multiimage of single PNGs held each frame for 3 or 4 vsyncs at random and reloaded them from disk.)

import math
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), '..', 'resources', 'skins', 'Default', 'media', 'loader', 'comet.apng')
SIZE = 180
FRAMES = 96
DELAY = 12  # ms: under one 60 Hz frame (16.7 ms), so Kodi steps once per frame; at 120 Hz once every other frame
COLOR = (64, 156, 255)  # #409cff, the plate's accent
SS = 8  # supersampling for the outline's edges

def arc(cx, cy, r, start, end, steps=90):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in (start + (end - start) * i / steps for i in range(steps + 1))]

def outline():
    # the stroke of the D: outside offset 5.5 (round at the two left corners), inside offset 5.5 (sharp)
    outer = arc(49, 54, 36.5, -90, 90) + arc(29, 85, 5.5, 90, 180) + arc(29, 23, 5.5, 180, 270)
    inner = [(34.5, 28.5)] + arc(49, 54, 25.5, -90, 90) + [(34.5, 79.5)]
    k = SIZE * SS / 108.0
    img = Image.new('L', (SIZE * SS, SIZE * SS), 0)
    draw = ImageDraw.Draw(img)
    draw.polygon([(x * k, y * k) for x, y in outer], fill=255)
    draw.polygon([(x * k, y * k) for x, y in inner], fill=0)
    return img.resize((SIZE, SIZE), Image.LANCZOS)

def wedge(a):
    # conic-gradient(transparent, accent 2deg 100deg, transparent 102deg), a in degrees clockwise from the wedge's start
    a %= 360
    return a / 2 if a < 2 else 1.0 if a <= 100 else (102 - a) / 2 if a < 102 else 0.0

def frames(count):
    mask = outline().load()
    lit = [(x, y, mask[x, y], math.degrees(math.atan2(x + 0.5 - SIZE / 2, SIZE / 2 - y - 0.5)))
           for y in range(SIZE) for x in range(SIZE) if mask[x, y]]
    for i in range(count):
        turn = 360.0 * i / count
        img = Image.new('RGBA', (SIZE, SIZE), COLOR + (0,))
        px = img.load()
        for x, y, alpha, angle in lit:
            px[x, y] = COLOR + (int(round(alpha * wedge(angle - turn))),)
        yield img

if __name__ == '__main__':
    images = list(frames(FRAMES))
    images[0].save(OUT, save_all=True, append_images=images[1:], duration=DELAY, loop=0, optimize=True)
    print(OUT, os.path.getsize(OUT))
