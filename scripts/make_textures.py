# -*- coding: utf-8 -*-
# Dev-time only: draws the window textures into resources/skins/Default/media/a4k/ (committed PNGs).
# Needs Pillow; the addon never imports it. Every shape is a primitive drawn from the numbers below
# (the #010 scope, section 5 and 6.1). Run: python3 scripts/make_textures.py

import os
import random

from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(__file__), '..', 'resources', 'skins', 'Default', 'media', 'a4k')
SS = 4  # supersampling: draw at 4x, downsample with LANCZOS for clean edges
PAGE = (7, 8, 12)  # #07080c

def save(img, name):
    img.save(os.path.join(OUT, name), optimize=True)

def rounded(size, radius, fill=(255, 255, 255, 255), inset=0):
    w, h = size
    img = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((inset * SS, inset * SS, (w - inset) * SS - 1, (h - inset) * SS - 1), radius * SS, fill=fill)
    return img.resize(size, Image.LANCZOS)

def ring():
    # card focus ring, 9-sliced (border 40) and drawn 9px outside the art: 6px #f5f6fa ring, then a 3px dark gap
    # down to the art's own r24 corner
    size, ss = 128, SS
    img = Image.new('RGBA', (size * ss, size * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    box = lambda inset: (inset * ss, inset * ss, (size - inset) * ss - 1, (size - inset) * ss - 1)
    draw.rounded_rectangle(box(0), 33 * ss, fill=(245, 246, 250, 255))
    draw.rounded_rectangle(box(6), 27 * ss, fill=(0, 0, 0, 140))
    draw.rounded_rectangle(box(9), 24 * ss, fill=(0, 0, 0, 0))
    return img.resize((size, size), Image.LANCZOS)

def shadow():
    # focused-card drop shadow (dobby 0 14u 28u rgba(0,0,0,.75)), 9-sliced with border 96; tinted at draw time
    img = Image.new('L', (256, 256), 0)
    ImageDraw.Draw(img).rounded_rectangle((72, 72, 183, 183), 24, fill=255)
    alpha = img.filter(ImageFilter.GaussianBlur(24))
    out = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    out.putalpha(alpha)
    return out

def placeholder(size, radius, a=(44, 44, 48), b=(26, 26, 30)):
    # card placeholder: dobby linear-gradient(160deg, #2c2c30, #1a1a1e), rounded
    w, h = size
    grad = Image.new('RGBA', size)
    px = grad.load()
    # 160deg points down and slightly left: project each pixel on that direction
    dx, dy = -0.342, 0.940
    lo = min(0, dx * w) + min(0, dy * h)
    hi = max(0, dx * w) + max(0, dy * h)
    for y in range(h):
        for x in range(w):
            t = ((x * dx + y * dy) - lo) / (hi - lo)
            px[x, y] = tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)) + (255,)
    grad.putalpha(rounded(size, radius).getchannel('A'))
    return grad

def ramp(stops, length):
    # alpha at each of `length` steps from (position 0..1, alpha 0..1) stops, linear in between
    out = []
    for i in range(length):
        p = i / (length - 1)
        for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
            if p0 <= p <= p1:
                out.append(a0 + (a1 - a0) * ((p - p0) / (p1 - p0) if p1 > p0 else 0))
                break
        else:
            out.append(stops[-1][1])
    return out

def scrim_left():
    # the hero text scrim (dobby .atv-hero-scrim::before), 1920x840 when drawn: a left-to-right #07080c ramp, faded out
    # at its own foot from 300u to 420u
    w, h = 256, 128
    across = ramp([(0, .97), (.15, .94), (.28, .88), (.40, .78), (.50, .64), (.60, .46), (.70, .26), (.80, .10), (.90, 0), (1, 0)], w)
    down = ramp([(0, 1), (300 / 420, 1), (1, 0)], h)
    img = Image.new('RGBA', (w, h))
    img.putdata([PAGE + (int(round(255 * across[x] * down[y])),) for y in range(h) for x in range(w)])
    return img

def scrim_bottom():
    # the hero's vertical scrim (dobby TV): clear to 187u, .45 at 400u, .5 at 460u, opaque at 560u; drawn 1920x1120
    h = 512
    alpha = ramp([(0, 0), (187 / 560, 0), (400 / 560, .45), (460 / 560, .5), (1, 1)], h)
    img = Image.new('RGBA', (1, h))
    img.putdata([PAGE + (int(round(255 * a)),) for a in alpha])
    return img

def fade_bottom():
    # diffuse mask for the sharp hero art: opaque to 60%, clear at its foot (dobby mask-image 180deg #000 60%)
    h = 256
    alpha = ramp([(0, 1), (.6, 1), (1, 0)], h)
    img = Image.new('RGBA', (8, h))
    img.putdata([(255, 255, 255, int(round(255 * alpha[y]))) for y in range(h) for _ in range(8)])
    return img

def bg_home():
    # home page: #07080c under two radial glows (dobby skin.css 142-144), at 960x540 (1u = 1px), with a light dither
    w, h = 960, 540
    glows = [((.8 * w, -.1 * h), (900, 500), (26, 33, 64)), ((0, 1.1 * h), (700, 400), (32, 20, 46))]
    rnd = random.Random(10)
    data = []
    for y in range(h):
        for x in range(w):
            c = list(PAGE)
            for (cx, cy), (rx, ry), color in glows:
                d = (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2) ** .5
                t = max(0.0, 1 - d / .6)  # color at the centre, transparent at 60% of the ellipse
                c = [c[i] + (color[i] - c[i]) * t for i in range(3)]
            n = rnd.random() - .5
            data.append(tuple(max(0, min(255, int(round(v + n)))) for v in c))
    img = Image.new('RGB', (w, h))
    img.putdata(data)
    return img

def star():
    # five-point star glyph, white, tinted #ffd166 at draw time
    import math
    size = 64 * SS
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    cx = cy = size / 2
    points = []
    for i in range(10):
        r = (size * .48) if i % 2 == 0 else (size * .19)
        a = math.pi / 2 + i * math.pi / 5
        points.append((cx + r * math.cos(a), cy - r * math.sin(a) + size * .03))
    ImageDraw.Draw(img).polygon(points, fill=(255, 255, 255, 255))
    return img.resize((64, 64), Image.LANCZOS)

def ring_face():
    # face focus ring (dobby .atvd-person focused: 3u #f5f6fa around the 88u face), drawn 6px outside the 176px face
    size = 188
    img = Image.new('RGBA', (size * SS, size * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size * SS - 1, size * SS - 1), fill=(245, 246, 250, 255))
    draw.ellipse((6 * SS, 6 * SS, (size - 6) * SS - 1, (size - 6) * SS - 1), fill=(0, 0, 0, 0))
    return img.resize((size, size), Image.LANCZOS)

def sheet():
    # sheet glass (dobby rgba(62,64,80,.97) -> rgba(34,36,46,.97)), r44, 1px top highlight 2EFFFFFF; 9-sliced, border 48.
    # Opaque: dobby's .97 sits on a backdrop blur, which Kodi cannot do, and at .97 the text behind still showed (live)
    w = h = 128
    a, b = (62, 64, 80), (34, 36, 46)
    rows = []
    for y in range(h):
        c = [a[i] + (b[i] - a[i]) * y / (h - 1) for i in range(3)]
        if y == 1:
            c = [v + (255 - v) * 0x2E / 255 for v in c]
        rows.append(tuple(int(round(v)) for v in c))
    img = Image.new('RGBA', (w, h))
    img.putdata([rows[y] + (255,) for y in range(h) for _ in range(w)])
    img.putalpha(rounded((w, h), 44).getchannel('A'))
    return img

def main():
    os.makedirs(OUT, exist_ok=True)
    save(rounded((64, 64), 20), 'rr20.png')
    save(rounded((64, 64), 24), 'rr24.png')
    save(ring(), 'ring.png')
    save(shadow(), 'shadow.png')
    save(rounded((264, 396), 24), 'mask_poster.png')
    save(placeholder((264, 396), 24), 'placeholder_poster.png')
    save(scrim_left(), 'scrim_left.png')
    save(scrim_bottom(), 'scrim_bottom.png')
    save(fade_bottom(), 'fade_bottom.png')
    save(bg_home(), 'bg_home.png')
    save(star(), 'star.png')
    # detail window: season pills, episode stills, cast faces
    save(rounded((128, 64), 32), 'pill.png')
    save(rounded((400, 224), 24), 'mask_ep.png')
    save(placeholder((400, 224), 24), 'placeholder_ep.png')
    save(rounded((176, 176), 88), 'mask_face.png')
    save(placeholder((176, 176), 88, (58, 58, 62), (31, 31, 35)), 'placeholder_face.png')
    save(ring_face(), 'ring_face.png')
    # sheets: flat veil, sheet glass, progress bar
    save(Image.new('RGBA', (8, 8), (255, 255, 255, 255)), 'white.png')
    save(sheet(), 'sheet.png')
    save(rounded((8, 8), 4), 'rr4.png')

if __name__ == '__main__':
    main()
