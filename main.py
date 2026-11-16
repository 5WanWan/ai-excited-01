#!/usr/bin/env python3
"""ai-excited-01 entry: "The Lighthouse Inside the Wave".

A procedural 1024x1024 PNG, pure Python stdlib (zlib + struct only).
No image libraries, no downloaded assets, fully deterministic (fixed seed).

Scene: one colossal ocean wave curls into a spiral barrel that fills the
frame on a diagonal. Inside the barrel -- impossibly small against the
water -- stands a tiny lighthouse on a rock, its beam cutting out toward
the viewer. The moment is the second before the wave swallows it.
One big readable shape (the curl) for the small-size read, one small
surprise detail (the lighthouse) for the second look.
"""
import math
import os
import random
import struct
import zlib

W = 1024
H = 1024
SEED = 20261116


# ---------------------------------------------------------------- framebuffer
class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)

    def set(self, x, y, r, g, b):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = r
            self.px[i + 1] = g
            self.px[i + 2] = b

    def blend(self, x, y, r, g, b, a):
        """Alpha-blend a colour over the pixel at (x, y); a in 0..1."""
        if 0 <= x < self.w and 0 <= y < self.h and a > 0.0:
            i = (y * self.w + x) * 3
            if a >= 1.0:
                self.px[i] = r
                self.px[i + 1] = g
                self.px[i + 2] = b
            else:
                ia = 1.0 - a
                self.px[i] = int(self.px[i] * ia + r * a)
                self.px[i + 1] = int(self.px[i + 1] * ia + g * a)
                self.px[i + 2] = int(self.px[i + 2] * ia + b * a)

    def get(self, x, y):
        i = (y * self.w + x) * 3
        return self.px[i], self.px[i + 1], self.px[i + 2]


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_rgb(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)),
            int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))


def clamp(v, lo=0, hi=255):
    return lo if v < lo else hi if v > hi else int(v)


# ------------------------------------------------------------------- shapes
def fill_rect(cv, x0, y0, x1, y1, col):
    x0 = max(0, int(x0))
    y0 = max(0, int(y0))
    x1 = min(cv.w, int(x1))
    y1 = min(cv.h, int(y1))
    r, g, b = col
    for y in range(y0, y1):
        base = (y * cv.w + x0) * 3
        for x in range(x0, x1):
            cv.px[base] = r
            cv.px[base + 1] = g
            cv.px[base + 2] = b
            base += 3


def fill_circle(cv, cx, cy, rad, col, alpha=1.0):
    r0 = int(cx - rad)
    r1 = int(cx + rad) + 1
    r, g, b = col
    rad2 = rad * rad
    for y in range(max(0, int(cy - rad)), min(cv.h, int(cy + rad) + 1)):
        dy = y - cy
        dx = math.sqrt(max(0.0, rad2 - dy * dy))
        x0 = max(0, int(cx - dx))
        x1 = min(cv.w, int(cx + dx) + 1)
        for x in range(x0, x1):
            cv.blend(x, y, r, g, b, alpha)


def fill_polygon(cv, pts, col, alpha=1.0):
    """Scanline fill of a simple polygon; col may be a callable (x, y) -> rgb."""
    if len(pts) < 3:
        return
    ys = [p[1] for p in pts]
    y0 = max(0, int(min(ys)))
    y1 = min(cv.h - 1, int(max(ys)) + 1)
    n = len(pts)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            x1, y1p = pts[i]
            x2, y2p = pts[(i + 1) % n]
            if (y1p <= y < y2p) or (y2p <= y < y1p):
                t = (y - y1p) / (y2p - y1p)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            xa = max(0, int(math.ceil(xs[k])))
            xb = min(cv.w - 1, int(math.floor(xs[k + 1])))
            for x in range(xa, xb + 1):
                if callable(col):
                    r, g, b = col(x, y)
                else:
                    r, g, b = col
                cv.blend(x, y, r, g, b, alpha)


def thick_polyline(cv, pts, width, col, alpha=1.0):
    """Draw a thick smooth-ish polyline by stamping circles along it."""
    r = width / 2.0
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(dist / max(2.0, r * 0.5)))
        for s in range(steps + 1):
            t = s / steps
            fill_circle(cv, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, r, col, alpha)


def disc_gradient(cv, cx, cy, rad, inner, outer):
    """Radial glow: inner colour at centre fading to outer at rad."""
    r0 = int(cx - rad)
    r1 = int(cx + rad) + 1
    for y in range(max(0, int(cy - rad)), min(cv.h, int(cy + rad) + 1)):
        dy = y - cy
        for x in range(max(0, r0), min(cv.w, r1)):
            dx = x - cx
            d = math.sqrt(dx * dx + dy * dy) / rad
            if d <= 1.0:
                t = d * d
                cv.blend(x, y, *lerp_rgb(inner, outer, t), 1.0 - t * 0.85)


# ----------------------------------------------------------------- PNG writer
def write_png(cv, path):
    raw = bytearray()
    stride = cv.w * 3
    prev = bytearray(stride)
    for y in range(cv.h):
        row = bytes(cv.px[y * stride:(y + 1) * stride])
        # Try filters 0 (none), 1 (sub), 2 (up); keep the smallest SAD.
        best = None
        best_data = None
        for f in (0, 1, 2):
            if f == 0:
                data = row
            elif f == 1:
                buf = bytearray(stride)
                for i in range(stride):
                    left = row[i - 3] if i >= 3 else 0
                    buf[i] = (row[i] - left) & 0xFF
                data = bytes(buf)
            else:
                buf = bytearray(stride)
                for i in range(stride):
                    buf[i] = (row[i] - prev[i]) & 0xFF
                data = bytes(buf)
            sad = sum(v if v < 128 else 256 - v for v in data)
            if best is None or sad < best:
                best = sad
                best_data = data
                best_f = f
        raw.append(best_f)
        raw.extend(best_data)
        prev = bytearray(row)
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# --------------------------------------------------------------------- scene
# Palette
DEEP_SKY = (8, 22, 52)        # top of sky
DUSK_SKY = (34, 58, 110)      # horizon sky
SUN_CORE = (255, 214, 120)
SUN_GLOW = (255, 150, 60)
SEA_DEEP = (4, 38, 66)
SEA_MID = (10, 84, 112)
SEA_LIT = (22, 138, 150)
SEA_FOAM = (214, 240, 244)
FOAM_WHITE = (240, 250, 252)
SPRAY = (190, 225, 232)
ROCK = (16, 24, 38)
LIGHT_BEAM = (255, 226, 140)


def draw_sky(cv):
    # Vertical gradient, deep indigo at top warming toward the horizon.
    for y in range(H):
        t = y / H
        if t < 0.55:
            col = lerp_rgb(DEEP_SKY, DUSK_SKY, t / 0.55)
        else:
            col = lerp_rgb(DUSK_SKY, (96, 92, 130), (t - 0.55) / 0.45)
        fill_rect(cv, 0, y, W, y + 1, col)
    # Low golden sun, top-right, half-hidden behind the crest.
    disc_gradient(cv, 838, 168, 260, SUN_GLOW, DUSK_SKY)
    disc_gradient(cv, 838, 168, 120, SUN_CORE, SUN_GLOW)
    fill_circle(cv, 838, 168, 58, SUN_CORE)
    # A few faint high stars in the darkest corner (top-left).
    rng = random.Random(SEED + 7)
    for _ in range(46):
        x = rng.uniform(0, 420)
        y = rng.uniform(0, 260)
        a = rng.uniform(0.25, 0.8)
        cv.blend(int(x), int(y), 220, 230, 255, a)


def catmull_rom(pts, samples=24):
    """Dense smooth points through control points (Catmull-Rom spline)."""
    if len(pts) < 2:
        return list(pts)
    ext = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(pts[-1])
    return out


def ellipse_points(cx, cy, rx, ry, a0=0.0, a1=2 * math.pi, steps=72):
    pts = []
    for i in range(steps + 1):
        t = a0 + (a1 - a0) * i / steps
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def draw_wave(cv):
    # --- Wave body: ONE solid breaking-wave mass. Smooth silhouette:
    # face rising from the lower left, crest curling over at top-right,
    # mass filling the whole right side down to the sea.
    ctrl = [(0, 1024), (0, 780), (60, 560), (180, 360), (360, 200),
            (560, 120), (760, 130), (890, 240), (960, 400),
            (1024, 540), (1024, 1024)]
    mass = catmull_rom(ctrl, 28)

    def wave_shade(x, y):
        # Dark at the base, bright teal near the crest.
        t = max(0.0, min(1.0, (1010 - y) / 900.0))
        base = lerp_rgb(SEA_DEEP, SEA_MID, t)
        lit = lerp_rgb(base, SEA_LIT, max(0.0, (y - 240) / 760.0) * 0.45)
        return lit

    fill_polygon(cv, mass, wave_shade)

    def is_water(x, y):
        """True when the pixel is wave water (not sky / sun / foam)."""
        if not (0 <= x < W and 0 <= y < H):
            return False
        r, g, b = cv.get(int(x), int(y))
        return g > 45 and b > 55 and b > g * 0.8

    # --- Flow bands: curved lines inside the water, following the
    # crest's shape, giving the mass motion and depth. Stamped point
    # by point so they never spill onto the sky.
    rng = random.Random(SEED + 41)
    for k in range(6):
        off = 60 + k * 62
        band_ctrl = [(20, 1024 - off * 0.4), (140, 860 - off),
                     (330, 640 - off), (560, 520 - off),
                     (780, 500 - off), (940, 560 - off)]
        band = catmull_rom(band_ctrl, 20)
        col = SEA_LIT if k % 2 == 0 else SEA_DEEP
        rad = rng.uniform(5, 11)
        a = rng.uniform(0.10, 0.18)
        for (px, py) in band:
            if is_water(px, py):
                fill_circle(cv, px, py, rad, col, a)
    # Soft mottling: large faint teal blotches for water texture,
    # only where the canvas is already water.
    for _ in range(260):
        x = rng.uniform(60, 1000)
        y = rng.uniform(180, 1000)
        if not is_water(x, y):
            continue
        r = rng.uniform(18, 70)
        col = SEA_LIT if rng.random() < 0.5 else SEA_DEEP
        fill_circle(cv, x, y, r, col, rng.uniform(0.04, 0.10))

    # --- Crest lip: organic foam along the top edge, curling over and
    # spiralling inward to a tip near the barrel.
    crest_ctrl = [(60, 560), (180, 360), (360, 200), (560, 120),
                  (760, 130), (890, 240), (950, 380), (900, 500),
                  (800, 570), (720, 560)]
    crest = catmull_rom(crest_ctrl, 22)
    rng = random.Random(SEED + 11)
    # Foam hugs the crest line: small overlapping circles straddling it.
    for i, (fx, fy) in enumerate(crest):
        r = rng.uniform(8, 18)
        fill_circle(cv, fx + rng.uniform(-6, 6), fy + rng.uniform(-6, 6),
                    r, FOAM_WHITE, rng.uniform(0.7, 0.95))
        if i % 3 == 0:
            fill_circle(cv, fx + rng.uniform(-10, 10),
                        fy + rng.uniform(4, 16), rng.uniform(4, 9),
                        SEA_FOAM, rng.uniform(0.5, 0.8))
    thick_polyline(cv, crest, 6, FOAM_WHITE, 0.7)
    # Warm sun-side highlight just under the foam, near the sun.
    sun_edge = catmull_rom([(560, 132), (760, 142), (890, 252),
                            (940, 380)], 18)
    thick_polyline(cv, sun_edge, 12, (255, 196, 110), 0.35)

    # --- Barrel hollow: a smooth dark tunnel mouth inside the mass,
    # soft edge, gold rim-light on its upper lip.
    bx, by = 590, 545
    for grow, a in ((26, 0.18), (14, 0.25), (5, 0.35)):
        fill_polygon(cv, ellipse_points(bx, by, 185 + grow, 132 + grow),
                     (10, 30, 62), a)
    fill_polygon(cv, ellipse_points(bx, by, 185, 132), (8, 24, 52))
    rim = ellipse_points(bx, by, 178, 126,
                         math.radians(195), math.radians(345), 40)
    thick_polyline(cv, rim, 9, (255, 196, 110), 0.75)

    # --- Spray: fine droplets flying off the lip toward the sun.
    rng = random.Random(SEED + 23)
    for _ in range(700):
        p = crest[rng.randrange(len(crest))]
        ang = rng.uniform(-0.6, 0.9)
        dist = rng.uniform(0, 110)
        x = p[0] + math.cos(ang) * dist + rng.uniform(-8, 8)
        y = p[1] + math.sin(ang) * dist * 0.6 + rng.uniform(-8, 8)
        cv.blend(int(x), int(y), *SPRAY, rng.uniform(0.35, 0.9))


def draw_sea(cv):
    # Foreground sea at the bottom: dark water with foam streaks
    # rushing toward the viewer, bottom-left to bottom-right.
    def sea_shade(x, y):
        t = (y - 830) / 194.0
        return lerp_rgb(SEA_MID, SEA_DEEP, max(0.0, min(1.0, t)))

    fill_polygon(cv, [(0, 1024), (0, 868), (1024, 800), (1024, 1024)],
                 sea_shade)
    rng = random.Random(SEED + 31)
    # Foam streaks: short diagonal dashes, sparse.
    for _ in range(34):
        x = rng.uniform(0, 1024)
        y = rng.uniform(860, 1000)
        ln = rng.uniform(20, 80)
        ang = rng.uniform(-0.35, -0.05)
        w = rng.uniform(2, 4)
        x2 = x + math.cos(ang) * ln
        y2 = y + math.sin(ang) * ln
        thick_polyline(cv, [(x, y), (x2, y2)], w, FOAM_WHITE,
                       rng.uniform(0.15, 0.4))
    # Whitecaps near the wave base.
    for _ in range(14):
        x = rng.uniform(60, 980)
        y = rng.uniform(850, 910)
        fill_circle(cv, x, y, rng.uniform(4, 10), FOAM_WHITE,
                    rng.uniform(0.3, 0.6))


def draw_lighthouse(cv):
    # The surprise: a tiny lighthouse on a rock INSIDE the barrel,
    # at the hollow's floor. Beam fans out toward the viewer (down-left).
    bx, by = 590, 634  # barrel hollow floor
    S = 1.25  # lighthouse scale

    def lx(dx):
        return bx + dx * S

    def ly(dy):
        return by + dy * S

    # Rock.
    fill_polygon(cv, [(lx(-52), ly(46)), (lx(-30), ly(2)),
                      (lx(-6), ly(-8)), (lx(26), ly(6)),
                      (lx(52), ly(46))], ROCK)
    # Tower: white with two red bands.
    tx = lx(-8)
    ty = ly(-66)
    tw = 24 * S
    fill_polygon(cv, [(tx, ty + 58 * S), (tx + 4 * S, ty),
                      (tx + 20 * S, ty), (tx + tw, ty + 58 * S)],
                 (235, 238, 240))
    fill_rect(cv, tx + 1 * S, ty + 16 * S, tx + 23 * S, ty + 26 * S,
              (198, 52, 44))
    fill_rect(cv, tx + 1 * S, ty + 38 * S, tx + 23 * S, ty + 48 * S,
              (198, 52, 44))
    # Lamp room + dome.
    fill_rect(cv, tx + 2 * S, ty - 12 * S, tx + 22 * S, ty, (24, 30, 44))
    fill_circle(cv, tx + 12 * S, ty - 6 * S, 7 * S, (255, 240, 170))
    fill_polygon(cv, [(tx + 1 * S, ty - 12 * S), (tx + 12 * S, ty - 22 * S),
                      (tx + 23 * S, ty - 12 * S)], (198, 52, 44))
    # Glow around the lamp.
    disc_gradient(cv, tx + 12 * S, ty - 6 * S, 46 * S,
                  (255, 226, 140), (255, 226, 140))
    # Beam: a wide translucent fan toward the viewer, down-left.
    beam = [(tx + 12 * S, ty - 6 * S), (bx - 330, by + 330),
            (bx - 180, by + 420)]
    fill_polygon(cv, beam, LIGHT_BEAM, 0.16)
    beam2 = [(tx + 12 * S, ty - 6 * S), (bx - 260, by + 260),
             (bx - 150, by + 330)]
    fill_polygon(cv, beam2, LIGHT_BEAM, 0.14)
    # A second, fainter beam to the right, into the barrel wall.
    beam3 = [(tx + 12 * S, ty - 6 * S), (bx + 190, by - 40),
             (bx + 150, by + 40)]
    fill_polygon(cv, beam3, LIGHT_BEAM, 0.10)


def draw_birds(cv):
    # Three tiny birds fleeing the crest, top-left.
    for (bx, by, s) in [(300, 250, 16), (352, 216, 12), (262, 300, 10)]:
        thick_polyline(cv, [(bx - s, by - s * 0.5), (bx, by),
                            (bx + s, by - s * 0.5)], 3.5, (12, 18, 30), 0.9)


def draw_vignette(cv):
    # Gentle darkening at the corners to pull the eye to the curl.
    # Border band darkened with distance-based alpha.
    for y in range(H):
        dy = min(y, H - 1 - y)
        for x in range(W):
            dx = min(x, W - 1 - x)
            d = min(dx, dy)
            if d < 90:
                a = (90 - d) / 90.0 * 0.22
                r, g, b = cv.get(x, y)
                cv.set(x, y, int(r * (1 - a)), int(g * (1 - a)),
                       int(b * (1 - a)))


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    cv = Canvas(W, H)
    draw_sky(cv)
    draw_wave(cv)
    draw_sea(cv)
    draw_lighthouse(cv)
    draw_birds(cv)
    draw_vignette(cv)
    path = os.path.join(out_dir, "entry.png")
    size = write_png(cv, path)
    print(f"wrote {path} ({size} bytes)")


if __name__ == "__main__":
    main()
