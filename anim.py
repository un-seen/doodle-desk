#!/usr/bin/env python3
"""Doodle animation engine: scene JSON -> SVG frames -> PNG -> MP4.

    python3 anim.py scene.json --out build/scene1            # SVG frames only
    python3 anim.py scene.json --out build/scene1 --render   # + PNG (resvg) + MP4 (ffmpeg)

Scene format (what the scene writer produces):
{
  "title": "...", "setting": "park|city|beach|night",
  "cast": [{"name": "Dot", "role": "cop", "sex": "male", "x": 0.2}, ...],
  "beats": [{"t": 0.5, "who": "Dot", "do": "walk_to", "to": "Pip"},
            {"t": 2.0, "who": "Dot", "do": "say", "text": "Ahoy?"}, ...]
}
Actions: walk_to, run_to (x or to), jump, wave, point, cheer, shrug, dance, surprised, laugh, say.
Speech is a text bubble, shown for its reading time (2.5 words a second).
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doodle as D  # noqa: E402

W, H, FPS = 1280, 720, 24
GY = 652                      # where feet touch the ground (the pills sit under it)
R = 122                       # character scale
BOIL_EVERY = 3                # redraw the shaky lines every 3 frames (8 drawings/s)
FONT = "Chalkboard SE, Comic Sans MS, Comic Neue, sans-serif"
MONO = "Menlo, DejaVu Sans Mono, monospace"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _data_uri(name):
    import base64
    try:
        return "data:image/png;base64," + base64.b64encode(open(os.path.join(ASSETS, name), "rb").read()).decode()
    except OSError:
        return None


QWEN_LOGO, HEDWIGAI_LOGO = _data_uri("qwen.png"), _data_uri("hedwigai.png")

GESTURE_SECONDS = {"jump": 1.0, "wave": 1.6, "point": 1.4, "cheer": 1.5, "shrug": 1.2,
                   "dance": 2.4, "surprised": 0.9, "laugh": 1.5}
WALK, RUN = .16, .42          # screen widths per second
READ_WPS = 2.5                # words per second, for bubbles and mouth flaps
ENGINE = "qwen"               # voice engine for --voice
TTS_DIRECT, OUT_DIR = False, "."   # --tts: talk to the TTS worker directly (no sound server)


def smooth(e0, e1, x):
    x = min(1, max(0, (x - e0) / (e1 - e0)))
    return x * x * (3 - 2 * x)


def lerp(a, b, w):
    return a + (b - a) * w


# ---------- things you can see (and walk to, point at) ----------

# Set pieces drawn by backdrop(): name -> list of (x, high). x is in scene units (0..1 is the walkable
# stretch; the edges hold trees). The scene writer is told these names.
SET_PIECES = {
    "park": {"tree": [(-.03, False), (1.04, False)], "sun": [(1.0, True)], "clouds": [(.45, True)],
             "grass": [(.5, False)]},
    "city": {"buildings": [(.5, True)], "windows": [(.5, True)], "sun": [(1.0, True)],
             "clouds": [(.45, True)], "pavement": [(.5, False)]},
    "beach": {"palm tree": [(1.08, False)], "coconuts": [(1.08, True)], "sea": [(.5, False)],
              "sun": [(1.0, True)], "clouds": [(.45, True)], "sand": [(.5, False)]},
    "night": {"moon": [(.97, True)], "stars": [(.5, True)], "tree": [(-.03, False), (1.04, False)],
              "grass": [(.5, False)]},
}
SET_TEXT = {
    "park": "a sunny park: a leafy tree at each edge, grass, the sun top right, slow clouds",
    "city": "a city street: a row of buildings with lit windows, the pavement, the sun, clouds",
    "beach": "a beach: the sea with little waves, sand, a palm tree with coconuts on the right, the sun, clouds",
    "night": "a park at night: a dark sky full of stars, the moon top right, two dark trees, grass",
}
PROP_KINDS = ["tv", "newsstand", "sign", "bench", "lamp"]
# how far from a thing's centre a character stops, so it never stands in front of it (scene units)
STAND_OFF = {"tv": .36, "newsstand": .26, "sign": .16, "bench": .2, "lamp": .1}


def things_of(scene):
    """name -> list of (x, high) for set pieces and props."""
    th = {k: list(v) for k, v in SET_PIECES.get(scene.get("setting", "park"), {}).items()}
    for p in scene.get("props", []):
        th.setdefault(p.get("name") or p["kind"], []).append((float(p.get("x", .5)), False))
    return th


def nearest(things, name, x):
    opts = things.get(name)
    return min(opts, key=lambda o: abs(o[0] - x)) if opts else None


# ---------- compile beats into per-actor tracks ----------

STYLE, PALETTE = "v2", "pastel"     # character style ("v1" the first doodles) and v2 palette ("skin" or "pastel")


def cast_looks():
    """Per-character look settings from cast.toml (hair, hair_color, head), by name."""
    try:
        import tomllib
        cfg = tomllib.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cast.toml"), "rb"))
        return {c["name"]: c.get("look", {}) for c in cfg.get("character", [])}
    except Exception:
        return {}


LOOKS = cast_looks()


class Actor:
    def __init__(self, spec):
        self.name = spec["name"]
        self.seed = zlib.crc32(self.name.encode()) % 100000
        self.g = D.apply_role(D.genome(self.seed, spec.get("sex")), spec.get("role", "none"), self.seed)
        if STYLE == "v2":                 # identity from the name only; the push shows on the face
            D.apply_style(self.g, self.seed, PALETTE, **LOOKS.get(self.name, {}))
        self.voice = spec.get("voice")
        self.personas = []                # (time, push) of each line, so the face follows the push
        self.x0 = self.x_end = float(spec.get("x", .5))
        self.moves, self.gestures, self.says = [], [], []
        self.busy = self.say_busy = 0.0
        self.anc = D.anchors(self.g, R)

    def x_at(self, t):
        x = self.x0
        for t0, t1, a, b, _ in self.moves:
            if t >= t1:
                x = b
            elif t >= t0:
                return lerp(a, b, smooth(0, 1, (t - t0) / (t1 - t0)) * .25 + (t - t0) / (t1 - t0) * .75)
        return x


def compile_scene(scene):
    actors = {c["name"]: Actor(c) for c in scene["cast"]}
    things = things_of(scene)
    for b in sorted(scene["beats"], key=lambda b: b.get("t", 0)):
        a = actors.get(b.get("who"))
        if not a:
            continue
        do, t = b.get("do"), float(b.get("t", 0))
        other = actors.get(b.get("to"))
        if do in ("walk_to", "run_to"):
            thing = nearest(things, b.get("to"), a.x_end)
            if other:   # stop short of them, on the side we come from
                side = -1 if a.x_end < other.x_end else 1
                x1 = other.x_end + side * .24
            elif thing:  # stand beside it, clear of it
                side = -1 if a.x_end < thing[0] else 1
                x1 = thing[0] + side * STAND_OFF.get(b.get("to"), .15)
            else:
                x1 = float(b.get("x", a.x_end))
            # never stop in front of another prop: step past it, away from where we were heading
            for p_ in scene.get("props", []):
                px_ = float(p_.get("x", .5))
                clear = STAND_OFF.get(p_.get("kind"), .15)       # each prop's own width
                if p_.get("kind") != b.get("to") and abs(x1 - px_) < clear - .02:
                    # stop beside it on the side we came from: never walk through or past the TV
                    x1 = px_ + (clear if a.x_end >= px_ else -clear)
            x1 = min(.95, max(.05, x1))
            if abs(x1 - a.x_end) < .02:
                continue
            t0 = max(t, a.busy)
            dur = max(.5, abs(x1 - a.x_end) / (RUN if do == "run_to" else WALK))
            a.moves.append((t0, t0 + dur, a.x_end, x1, "run" if do == "run_to" else "walk"))
            a.busy, a.x_end = t0 + dur, x1
        elif do in GESTURE_SECONDS:
            t0 = max(t, a.busy)
            a.gestures.append((t0, t0 + GESTURE_SECONDS[do], do, b.get("to")))
            a.busy = t0 + GESTURE_SECONDS[do]
        elif do == "say" and b.get("text"):
            words = len(b["text"].split())
            t0 = max(t, a.say_busy)
            talk = b.get("seconds") or words / READ_WPS      # spoken length when there is a voice
            t1 = t0 + max(1.8, words / READ_WPS + 1.0, talk + .8)
            a.says.append((t0, t1, t0 + talk, b["text"], b.get("mouths")))
            a.personas.append((t0, (b.get("persona") or (b.get("voice") or "").split(" @ ")[0] or a.voice) or None))
            b["t_said"] = t0
            a.say_busy = t1 + .15
    end = max([0.0] + [m[1] for a in actors.values() for m in a.moves]
              + [g[1] for a in actors.values() for g in a.gestures]
              + [s[1] for a in actors.values() for s in a.says])
    return actors, min(end + 1.0, 60.0), things


# ---------- pose at time t ----------

def pose_at(a, t, actors, things=None):
    x = a.x_at(t)
    others = [o for o in actors.values() if o is not a]
    near = min(others, key=lambda o: abs(o.x_at(t) - x)) if others else None
    toward = (1 if near.x_at(t) > x else -1) if near else 1

    breath = math.sin(t * 2.2 + a.seed)
    arms = [[28 + 3 * breath, -12], [28 + 3 * breath, -12]]
    legs, dy, lean, squash = None, 0.0, 0.0, 1 + .012 * breath
    look = (toward * .8, 0)
    mouth = None

    nl = 2 if a.g["sex"] == "male" else a.g["legs"]
    for t0, t1, x0, x1, gait in a.moves:
        if t0 <= t < t1:
            d = 1 if x1 > x0 else -1
            run = gait == "run"
            ph = (t - t0) * (1.6 if run else 1.0) * 2 * math.pi
            amp, stride, lift = (40, .3, .24) if run else (22, .18, .12)
            arms = [[25 + amp * math.sin(ph), -70 if run else -15],
                    [25 - amp * math.sin(ph), -70 if run else -15]]
            legs = [(d * R * stride * math.sin(ph + i * 2 * math.pi / nl),
                     max(0, math.cos(ph + i * 2 * math.pi / nl)) * R * lift) for i in range(nl)]
            dy = -abs(math.sin(ph)) * (12 if run else 5)
            lean = d * (10 if run else 4)
            look = (d * .9, 0)

    for t0, t1, kind, to in a.gestures:
        if not (t0 <= t < t1):
            continue
        u = (t - t0) / (t1 - t0)
        w = smooth(0, .15, u) * (1 - smooth(.85, 1, u))
        tgt = actors.get(to)
        thing = nearest(things or {}, to, x)
        high = bool(thing and thing[1])
        if tgt:
            side = 1 if tgt.x_at(t) > x else -1
        elif thing:
            side = 1 if thing[0] > x else -1
        else:
            side = toward
        k = 1 if side > 0 else 0          # arm index toward the target
        want = [list(arms[0]), list(arms[1])]
        if (tgt or thing) and kind != "point":
            look = (side * .7, -.6 if high else 0)
        if kind == "wave":
            want[k] = [125, 25 + 30 * math.sin(2 * math.pi * 3 * t)]
        elif kind == "point":
            want[k] = [148, 0] if high else [82, 4]
            look = (side * .6, -.8) if high else (side * .9, 0)
        elif kind == "cheer":
            want = [[150, 15 + 15 * math.sin(2 * math.pi * 4 * t)], [150, 15 - 15 * math.sin(2 * math.pi * 4 * t)]]
            dy -= 12 * abs(math.sin(2 * math.pi * 2 * t)) * w
            mouth = "grin"
        elif kind == "shrug":
            want = [[55, -105], [55, -105]]
            dy -= 4 * w
            mouth = "flat"
        elif kind == "dance":
            s2 = math.sin(2 * math.pi * 2 * t)
            want = [[120 + 30 * s2, 30], [120 - 30 * s2, 30]]
            lean = 10 * s2 * w
            dy -= abs(s2) * 10 * w
            legs = [(R * .12 * s2 * (1 if i % 2 else -1), max(0, s2 if i % 2 else -s2) * R * .1) for i in range(nl)]
            mouth = "smile"
        elif kind == "surprised":
            want = [[140, 20], [140, 20]]
            dy -= 18 * math.sin(math.pi * min(1, u * 2)) * w
            mouth = "o"
        elif kind == "laugh":
            want = [[35, -70], [35, -70]]
            dy -= abs(math.sin(2 * math.pi * 5 * t)) * 5 * w
            mouth = "grin"
        elif kind == "jump":
            if u < .2:
                squash = 1 - .16 * smooth(0, 1, u / .2)
                want = [[10, -20], [10, -20]]
            elif u < .75:
                v = (u - .2) / .55
                dy -= R * 1.0 * math.sin(math.pi * v)
                squash = 1.06
                want = [[150, 10], [150, 10]]
                legs = [(0, R * .12)] * nl
            else:
                squash = 1 - .14 * math.sin(math.pi * (u - .75) / .25)
            w = 1 if .2 <= u < .75 else w
        arms = [[lerp(arms[i][j], want[i][j], w) for j in range(2)] for i in range(2)]

    emotion = None
    for t0, t1, kind, to in a.gestures:
        if t0 <= t < t1:
            emotion = {"surprised": "surprised", "laugh": "laugh", "cheer": "laugh", "shrug": "shrug"}.get(kind, emotion)
    persona = a.voice
    for pt, pv in a.personas:             # the push of the line being said, or the last one said
        if pt <= t:
            persona = pv
    bubble = None
    for t0, t1, talk_end, text, mouths in a.says:
        if t0 <= t < t1:
            bubble = (text, t - t0)
            if t < talk_end and mouths:      # lip sync: the voice engine's mouth shapes
                shape = "flat"
                for mt, m in mouths:
                    if mt <= t - t0:
                        shape = m
                mouth = shape
            elif t < talk_end and mouth is None:
                mouth = ["o", "smile", "flat", "o", "grin"][int(t * 9) % 5]

    period = 2.8 + (a.seed % 7) * .25
    blink = (t + a.seed % 13) % period < .12
    return dict(x=x, arms=arms, legs=legs, dy=dy, lean=lean, squash=squash,
                look=look, mouth=mouth, blink=blink, bubble=bubble, persona=persona, emotion=emotion,
                brow_lift=5.0 if mouth in ("grin", "o") and bubble else 0.0,
                talk={"grin": 1.0, "teeth": .7, "o": .8, "smile": .45, "flat": .15}.get(mouth, 0.0) if bubble else 0.0,
                sway=max(-1.0, min(1.0, lean / 10 + .12 * math.sin(t * 1.3 + a.seed))), t=t)


# ---------- backdrops ----------

SKIES = {"park": ("#dff3ff", "#bfe6a8"), "city": ("#ffe9d6", "#d9d4cc"),
         "beach": ("#d6f0ff", "#f6e3b4"), "night": ("#2b2d42", "#3d5a40")}


def backdrop(setting, t, boil):
    sky, ground = SKIES.get(setting, SKIES["park"])
    rng = random.Random(1000 + boil)
    pen = D.Pen(rng, shake=1.4)
    hz = GY - 70                                   # horizon
    out = [f'<rect width="{W}" height="{H}" fill="{sky}"/>']
    r0 = random.Random(hash(setting) % 9973)       # fixed layout per setting

    if setting == "night":
        for _ in range(60):
            out.append(f'<circle cx="{r0.uniform(0, W):.0f}" cy="{r0.uniform(0, hz - 40):.0f}" '
                       f'r="{r0.uniform(1, 2.6):.1f}" fill="#fdffb6" opacity="{r0.uniform(.4, 1):.2f}"/>')
        pen.closed(D.ellipse(1080, 110, 48, 48, 16), fill="#fdffb6")
    else:
        pen.closed(D.ellipse(1110, 105, 52, 52, 16), fill="#ffd166")
        for i in range(3):   # clouds drift slowly
            cx = (r0.uniform(0, W) + t * (10 + 4 * i)) % (W + 300) - 150
            cy = r0.uniform(70, 220)
            for dx, dy, rr in ((-40, 8, 30), (0, -6, 40), (42, 6, 30)):
                pen.closed(D.ellipse(cx + dx, cy + dy, rr * 1.2, rr, 12), fill="#ffffff", w=2.4, passes=1)

    if setting == "city":
        x = -20
        while x < W:
            bw, bh = r0.uniform(90, 160), r0.uniform(160, 360)
            col = r0.choice(["#c9b7a6", "#e0cfc0", "#b8c4d6", "#d8c3b0"])
            pen.closed([(x, hz), (x + bw, hz), (x + bw, hz - bh), (x, hz - bh)], fill=col, w=2.6, passes=1)
            for wy in range(int(hz - bh + 24), int(hz - 20), 38):
                for wx in range(int(x + 16), int(x + bw - 22), 30):
                    out_col = "#fdffb6" if r0.random() < .3 else "#ffffff"
                    pen.closed([(wx, wy), (wx + 14, wy), (wx + 14, wy + 18), (wx, wy + 18)], fill=out_col, w=1.6, passes=1)
            x += bw + r0.uniform(4, 20)
    if setting == "beach":
        pen.closed([(-20, hz - 60), (W + 20, hz - 60), (W + 20, hz + 5), (-20, hz + 5)], fill="#4fb3d9", w=2.4, passes=1)
        for k in range(8):   # little wave marks on the sea
            wx = (k * 170 + t * 25) % (W + 100) - 50
            pen.line([(wx, hz - 25), (wx + 14, hz - 33), (wx + 28, hz - 25)], w=2, passes=1)

    # ground
    pen.closed([(-20, hz)] + [(x, hz + r0.uniform(-4, 4)) for x in range(80, W, 160)] +
               [(W + 20, hz), (W + 20, H + 20), (-20, H + 20)], fill=ground, w=3)

    if setting in ("park", "night"):
        for tx in (140, 1150):
            pen.line([(tx, hz + 10), (tx + 4, hz - 120)], w=7, passes=1)
            pen.closed([(tx + 4 + 70 * math.cos(a) * (1 + .1 * math.sin(3 * a)),
                         hz - 170 + 60 * math.sin(a)) for a in [i * math.pi / 7 for i in range(14)]],
                       fill="#7cc576" if setting == "park" else "#2f4a32")
    if setting == "beach":
        tx, ty = 1185, hz - 230               # palm: curved trunk, drooping leaf blades
        pen.closed([(tx - 14, hz + 20), (tx + 10, hz + 20), (tx + 2, hz - 100), (tx + 8, ty + 4),
                    (tx - 4, ty + 4), (tx - 12, hz - 100)], fill="#b5835a", w=2.6, passes=1)
        for ang in (-2.9, -2.3, -1.6, -.9, -.25):
            ex, ey = tx + 95 * math.cos(ang), ty + 45 * math.sin(ang) + 55
            mx, my_ = tx + 55 * math.cos(ang), ty + 40 * math.sin(ang) - 5
            nx, ny = -(my_ - ty), (mx - tx)
            nn = math.hypot(nx, ny) or 1
            pen.closed([(tx, ty), (mx + 12 * nx / nn, my_ + 12 * ny / nn), (ex, ey),
                        (mx - 12 * nx / nn, my_ - 12 * ny / nn)], fill="#5fb85a", w=2.4, passes=1)
        pen.closed(D.ellipse(tx - 6, ty + 8, 9, 9, 8), fill="#7a4b2a", w=2, passes=1)
        pen.closed(D.ellipse(tx + 9, ty + 10, 9, 9, 8), fill="#7a4b2a", w=2, passes=1)
    return "\n".join(out + pen.out)


# ---------- props ----------

def draw_prop(p, t, boil, idx):
    kind, px = p["kind"], 170 + float(p.get("x", .5)) * (W - 340)
    pen = D.Pen(random.Random(500 + idx * 7 + boil), shake=1.3)
    out = []
    text = esc(p.get("text", ""))
    if kind == "tv":
        w, h = 470, 310
        top = GY - h - 86
        for dx in (-130, 130):
            pen.line([(px + dx, GY - 4), (px + dx * .8, top + h)], w=6, passes=1)
        pen.closed([(px - w / 2, top), (px + w / 2, top), (px + w / 2, top + h), (px - w / 2, top + h)], fill="#3a3a48", w=3.4)
        sx, sy, sw, sh = px - w / 2 + 14, top + 14, w - 28, h - 28
        pen.closed([(sx, sy), (sx + sw, sy), (sx + sw, sy + sh), (sx, sy + sh)], fill="#f4f9ff", w=2, passes=1)
        out.append(f'<clipPath id="scr{idx}"><rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}"/></clipPath>')
        g = [f'<g clip-path="url(#scr{idx})">',
             f'<rect x="{sx + 10:.1f}" y="{sy + 10:.1f}" width="78" height="28" fill="#d62828"/>',
             f'<text x="{sx + 49:.1f}" y="{sy + 31:.1f}" font-family="{FONT}" font-size="19" fill="#fff" '
             f'text-anchor="middle" font-weight="bold">NEWS</text>']
        # the headline, whole and big: the largest size at which it fits in four lines
        head = p.get("text", "")
        for fs in (27, 25, 23, 21, 19):
            per = int(sw / (fs * .5))
            lines = wrap(head, per)
            if len(lines) <= 4:
                break
        y = sy + 46
        for l in lines[:4]:
            y += fs * 1.18
            g.append(f'<text x="{sx + 12:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{fs}" font-weight="bold" '
                     f'fill="{D.INK}">{esc(l)}</text>')
        prog_ = p.get("program") or {}
        series = prog_.get("series") or []
        run = smooth(.6, 2.8, t)                     # the program "runs": the chart plots in
        pill_y = sy + sh - 36
        if series:
            x0, x1 = sx + 14, sx + sw - 14
            y1, y0 = y + 30, pill_y - 10            # between the headline and the command
            if y0 - y1 > 24:
                peak = max(series) or 1
                pts = [(x0 + (x1 - x0) * i / max(1, len(series) - 1), y0 - (y0 - y1) * v / peak) for i, v in enumerate(series)]
                g.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y0:.1f}" stroke="#9aa7b4" stroke-width="1.5"/>')
                shown = pts[:max(2, int(len(pts) * run))]
                g.append('<polyline points="' + " ".join(f"{x:.1f},{yy:.1f}" for x, yy in shown) +
                         '" fill="none" stroke="#d62828" stroke-width="3" stroke-linejoin="round"/>')
                g.append(f'<circle cx="{shown[-1][0]:.1f}" cy="{shown[-1][1]:.1f}" r="4" fill="#d62828"/>')
                g.append(f'<text x="{x1:.1f}" y="{y1 - 8:.1f}" font-family="{FONT}" font-size="14" fill="#4a5560" '
                         f'text-anchor="end">{esc(prog_.get("label", ""))}</text>')
        if prog_.get("cmd"):                          # the hedwigai shell command feeding the screen
            px0, py0, pw, ph = sx + 8, pill_y, sw - 16, 30
            g.append(f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{pw:.1f}" height="{ph}" rx="15" fill="#1d1b19"/>')
            if HEDWIGAI_LOGO:
                g.append(f'<rect x="{px0 + 5:.1f}" y="{py0 + 4:.1f}" width="28" height="22" rx="6" fill="#f4efe6"/>')
                g.append(f'<image href="{HEDWIGAI_LOGO}" x="{px0 + 7:.1f}" y="{py0 + 6:.1f}" width="24" height="18"/>')
            g.append(f'<text x="{px0 + 40:.1f}" y="{py0 + 21:.1f}" font-family="Georgia, serif" font-style="italic" '
                     f'font-size="16" fill="#f4efe6">hedwigai</text>')
            spin = "" if run >= 1 else " " + "|/-\\"[int(t * 10) % 4]
            cmd = "$ " + prog_["cmd"] + spin
            cx0 = px0 + 112
            avail = pw - 122
            tw = len(cmd) * 14 * .6
            over = max(0.0, tw - avail)               # hold the start, scroll, hold the end, repeat
            cycle = 3.0 + over / 45 if over else 1.0
            u_ = t % cycle
            off = 0.0 if not over else min(over, max(0.0, (u_ - 1.5) * 45))
            g.append(f'<clipPath id="pill{idx}"><rect x="{cx0:.1f}" y="{py0:.1f}" width="{avail:.1f}" height="{ph}"/></clipPath>')
            g.append(f'<text x="{cx0 - off:.1f}" y="{py0 + 20:.1f}" font-family="{MONO}" font-size="14" fill="#e8e8e8" '
                     f'clip-path="url(#pill{idx})">{esc(cmd)}</text>')
        g.append("</g>")
        out += g
        pen.line([(px - 40, top - 36), (px, top)], w=3, passes=1)       # antenna
        pen.line([(px + 44, top - 40), (px, top)], w=3, passes=1)
    elif kind == "newsstand":
        w, h = 220, 200
        top = GY - h
        pen.closed([(px - w / 2, GY), (px + w / 2, GY), (px + w / 2, top), (px - w / 2, top)], fill="#8ecae6", w=3)
        for k in range(6):   # striped awning
            x0 = px - w / 2 - 10 + k * (w + 20) / 6
            pen.closed([(x0, top - 40), (x0 + (w + 20) / 6, top - 40), (x0 + (w + 20) / 6, top),
                        (x0 + (w + 20) / 12, top + 14), (x0, top)], fill="#d62828" if k % 2 == 0 else "#ffffff", w=2.2, passes=1)
        out_text = [f'<text x="{px:.1f}" y="{top - 14:.1f}" font-family="{FONT}" font-size="20" text-anchor="middle" '
                    f'fill="{D.INK}" font-weight="bold">NEWS</text>']
        bx, by_, bw, bh = px - w / 2 + 14, top + 16, w - 28, 120
        pen.closed([(bx, by_), (bx + bw, by_), (bx + bw, by_ + bh), (bx, by_ + bh)], fill="#ffffff", w=2.2, passes=1)
        lines = wrap(p.get("text", ""), 21)[:5]
        for i, l in enumerate(lines):
            out_text.append(f'<text x="{px:.1f}" y="{by_ + 24 + i * 21:.1f}" font-family="{FONT}" font-size="16" '
                            f'text-anchor="middle" fill="{D.INK}">{esc(l)}</text>')
        return "\n".join(pen.out + out_text)
    elif kind == "sign":
        pen.line([(px, GY), (px + 2, GY - 200)], w=7, passes=1)
        lines = wrap(p.get("text", ""), 14)[:3]
        bw, bh = 190, 30 + 28 * len(lines)
        top = GY - 200 - bh / 2
        pen.closed([(px - bw / 2, top), (px + bw / 2, top + 4), (px + bw / 2, top + bh), (px - bw / 2, top + bh - 3)],
                   fill="#fff3c4", w=3)
        for i, l in enumerate(lines):
            out.append(f'<text x="{px:.1f}" y="{top + 34 + i * 28:.1f}" font-family="{FONT}" font-size="23" '
                       f'text-anchor="middle" fill="{D.INK}">{esc(l)}</text>')
    elif kind == "bench":
        pen.closed([(px - 100, GY - 60), (px + 100, GY - 60), (px + 100, GY - 46), (px - 100, GY - 46)], fill="#c08552", w=2.6)
        pen.closed([(px - 95, GY - 120), (px + 95, GY - 120), (px + 95, GY - 92), (px - 95, GY - 92)], fill="#c08552", w=2.6)
        for dx in (-85, 85):
            pen.line([(px + dx, GY - 2), (px + dx, GY - 120)], w=5, passes=1)
    elif kind == "lamp":
        pen.line([(px, GY), (px + 2, GY - 290)], w=7, passes=1)
        pen.line([(px + 2, GY - 290), (px + 30, GY - 305), (px + 50, GY - 290)], w=5, passes=1)
        pen.closed(D.ellipse(px + 50, GY - 280, 16, 13, 10), fill="#ffd166", w=2.4, passes=1)
    return "\n".join(pen.out + out)


# ---------- speech bubbles ----------

def wrap(text, n=22):
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + ([cur] if cur else [])


FS = 26


def bubble_box(text, age, hx, top_y):
    lines = wrap(text)
    pop = .7 + .3 * smooth(0, .15, age)            # little pop as it appears
    bw_ = (max(len(l) for l in lines) * FS * .55 + 44) * pop
    bh_ = (len(lines) * FS * 1.2 + 26) * pop
    return {"lines": lines, "pop": pop, "w": bw_, "h": bh_, "hx": hx, "top_y": top_y, "age": age,
            "x": min(W - 12 - bw_, max(12, hx - bw_ / 2)), "y": max(12, top_y - 28 - bh_)}


def separate(boxes):
    """Push overlapping bubbles apart sideways; if the screen edge stops that, lift the newer one."""
    boxes.sort(key=lambda b: b["hx"])
    for _ in range(4):
        for a, b in zip(boxes, boxes[1:]):
            ox = a["x"] + a["w"] + 14 - b["x"]
            oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ox <= 0 or oy <= 0:
                continue
            a["x"] = max(12, a["x"] - ox / 2)
            b["x"] = min(W - 12 - b["w"], b["x"] + ox / 2)
            ox = a["x"] + a["w"] + 14 - b["x"]
            if ox > 0:
                newer = a if a["age"] < b["age"] else b
                older = b if newer is a else a
                newer["y"] = max(12, older["y"] - newer["h"] - 14)


def bubble_svg(box, boil, seed):
    lines, pop, hx, top_y = box["lines"], box["pop"], box["hx"], box["top_y"]
    fs, bw_, bh_, bx, by = FS, box["w"], box["h"], box["x"], box["y"]
    pen = D.Pen(random.Random(seed * 31 + boil), shake=1.2, width=2.8)
    r = 18
    pts = []
    for (cx, cy, a0) in ((bx + bw_ - r, by + r, -math.pi / 2), (bx + bw_ - r, by + bh_ - r, 0),
                         (bx + r, by + bh_ - r, math.pi / 2), (bx + r, by + r, math.pi)):
        pts += [(cx + r * math.cos(a0 + k * math.pi / 6), cy + r * math.sin(a0 + k * math.pi / 6)) for k in range(4)]
    tail_x = min(max(hx, bx + 30), bx + bw_ - 30)
    tip_y = max(top_y - 6, by + bh_ + 10)
    pen.closed([(tail_x - 12, by + bh_ - 3), (hx + 4, tip_y), (tail_x + 12, by + bh_ - 3)], fill="#ffffff", w=2.6, passes=1)
    pen.closed(pts, fill="#ffffff", w=2.8, passes=1)
    if pop < .99:
        return "\n".join(pen.out)
    tx = bx + bw_ / 2
    spans = "".join(f'<tspan x="{tx:.1f}" dy="{fs * 1.2 if i else 0:.1f}">{esc(l)}</tspan>' for i, l in enumerate(lines))
    pen.out.append(f'<text x="{tx:.1f}" y="{by + 18 + fs * .85:.1f}" font-family="{FONT}" font-size="{fs}" '
                   f'text-anchor="middle" fill="{D.INK}">{spans}</text>')
    return "\n".join(pen.out)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- frames ----------

PILL_H = 44


def char_pill(scene, name, cx, top_y, t=0.0):
    """Floating over the head: the Qwen mark, the name, the model id and the personality."""
    c = next((c for c in scene.get("cast", []) if c["name"] == name), {})
    model = scene.get("model", "Qwen3.5-4B")
    line2 = f"{model} · {c.get('voice') or 'no push'}"
    w = max(len(name) * 9.6 + 40, len(line2) * 7.0 + 26)
    h = PILL_H
    bob = 3 * math.sin(t * 2.4 + zlib.crc32(name.encode()) % 7)
    y0 = top_y - 14 - h + bob
    x0 = min(W - 8 - w, max(8, cx - w / 2))
    out = [f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h}" rx="16" fill="#ffffff" stroke="{D.INK}" stroke-width="2"/>']
    if QWEN_LOGO:
        out.append(f'<image href="{QWEN_LOGO}" x="{x0 + 12:.1f}" y="{y0 + 5:.1f}" width="18" height="18"/>')
    out.append(f'<text x="{x0 + 36:.1f}" y="{y0 + 19:.1f}" font-family="{FONT}" font-size="16" font-weight="bold" '
               f'fill="{D.INK}">{esc(name)}</text>')
    out.append(f'<text x="{x0 + 13:.1f}" y="{y0 + 37:.1f}" font-family="{FONT}" font-size="13" fill="#4a4f57">{esc(line2)}</text>')
    return "\n".join(out)


def frame_svg(scene, actors, t, f, things=None):
    boil = f // BOIL_EVERY % 3
    parts = [backdrop(scene.get("setting", "park"), t, boil)]
    parts += [draw_prop(p, t, boil, i) for i, p in enumerate(scene.get("props", []))
              if p.get("kind") in PROP_KINDS]
    bubbles = []
    poses = {n: pose_at(a, t, actors, things) for n, a in actors.items()}
    for n, a in sorted(actors.items(), key=lambda kv: kv[1].seed):
        p = poses[n]
        cx = 170 + p["x"] * (W - 340)
        cy = GY - a.anc["feet"] + p["dy"]
        body = D.draw_character(a.g, cx, cy, R, a.seed * 7919 + boil,
                                pose={"arms": p["arms"], "legs": p["legs"], "look": p["look"],
                                      "mouth": p["mouth"], "blink": p["blink"], "persona": p["persona"],
                                      "emotion": p["emotion"], "brow_lift": p["brow_lift"],
                                      "talk": p["talk"], "sway": p["sway"], "t": t})
        sq = p["squash"]
        tf = (f'rotate({p["lean"]:.2f} {cx:.1f} {GY}) translate({cx:.1f} {GY}) '
              f'scale({1 / math.sqrt(sq):.4f} {sq:.4f}) translate({-cx:.1f} {-GY})')
        parts.append(f'<ellipse cx="{cx:.1f}" cy="{GY - 2}" rx="{R * .75:.1f}" ry="9" fill="#000" opacity=".12"/>')
        parts.append(f'<g transform="{tf}">{body}</g>')
        if p["bubble"]:
            text, age = p["bubble"]
            bubbles.append((bubble_box(text, age, cx, cy + a.anc["top"] - PILL_H - 16), a.seed))
    for n, a in actors.items():
        pcx = 170 + poses[n]["x"] * (W - 340)
        parts.append(char_pill(scene, n, pcx, GY - a.anc["feet"] + poses[n]["dy"] + a.anc["top"], t))
    separate([b for b, _ in bubbles])
    parts += [bubble_svg(b, boil, seed) for b, seed in bubbles]
    if scene.get("title") and t < 2.2:   # title card fades out
        op = 1 - smooth(1.4, 2.2, t)
        parts.append(f'<text x="{W / 2}" y="70" font-family="{FONT}" font-size="44" text-anchor="middle" '
                     f'fill="{"#fdffb6" if scene.get("setting") == "night" else D.INK}" opacity="{op:.2f}">{esc(scene["title"])}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            + "\n".join(parts) + "</svg>")


# ---------- voices (sonic-forge /api/voice) ----------

QWEN_SPEAKERS = {"male": ["ryan", "aiden", "eric", "dylan", "uncle_fu"], "female": ["serena", "vivian", "sohee", "ono_anna"]}
# how each persona push sounds when spoken (the instruct line for Qwen3-TTS)
PERSONA_DELIVERY = {
    "flattering": "warm, gushing and admiring", "contemptuous": "scornful and contemptuous", "poetic": "dreamy and lyrical",
    "upbeat": "bright, cheerful and energetic", "suspicious": "suspicious, slow and questioning",
    "condescending": "condescending and superior", "wistful": "soft, wistful and nostalgic",
    "oracle": "calm, mysterious and prophetic", "bleak": "flat, weary and gloomy", "dismissive": "bored and dismissive",
    "ornate": "grand, slow and theatrical", "curt": "short, clipped and impatient", "hostile": "angry and hostile",
}
ROLE_DELIVERY = {"cop": "like a police officer", "hero": "like a cartoon superhero", "chef": "like a fussy chef",
                 "pirate": "like a cartoon pirate", "wizard": "like an old wizard", "doctor": "like a busy doctor",
                 "firefighter": "like a firefighter", "ninja": "in a hushed voice, like a ninja",
                 "royal": "like a pompous monarch", "astronaut": "like an astronaut on the radio",
                 "detective": "like a noir detective"}


def qwen_speech(a, cast_entry, taken=()):
    """A neural voice: one fixed preset speaker per character (never one another character in the
    scene has), the delivery from its persona push."""
    sex = a.g["sex"]
    names = QWEN_SPEAKERS[sex]
    k = zlib.crc32(a.name.encode()) % len(names)
    speaker = next((names[(k + j) % len(names)] for j in range(len(names)) if names[(k + j) % len(names)] not in taken),
                   names[k])
    how = PERSONA_DELIVERY.get(cast_entry.get("voice") or "", "natural and expressive")
    who = ROLE_DELIVERY.get(a.g.get("role", "none"), "like a cartoon character")
    return {"engine": "qwen", "speaker": speaker, "instruct": f"Speak {how}, {who}."}


def default_speech(a):
    """A voice from the doodle: sex, role and body size. cast.toml can override any field."""
    g, role = a.g, a.g.get("role", "none")
    male = g["sex"] == "male"
    r = random.Random(a.seed)
    v = {"pitch": (108 if male else 212) * r.uniform(.9, 1.1), "size": (1.0 if male else 1.17) / g["size"] ** .5,
         "speed": r.uniform(.95, 1.08), "breath": .15, "vibrato": 0.0, "range": 1.0}
    v.update({"cop": {"range": .8, "speed": 1.05}, "pirate": {"breath": .28, "range": 1.3},
              "chef": {"range": 1.4}, "hero": {"range": 1.25},
              "wizard": {"pitch": v["pitch"] * .85, "vibrato": .03, "speed": .85, "breath": .3},
              "royal": {"speed": .85, "range": 1.5}, "detective": {"breath": .3, "range": .7},
              "ninja": {"breath": .6, "speed": 1.15, "range": .6}, "astronaut": {"range": .9},
              "doctor": {"speed": 1.05}, "firefighter": {"range": 1.3}}.get(role, {}))
    return v


def voice_scene(scene, actors, url, name):
    """Speak every line on the sound server, then give each line its spoken length (and the
    scene room for it: a line never starts before the previous one is said)."""
    import urllib.request
    says = [b for b in sorted(scene["beats"], key=lambda b: b["t"]) if b["do"] == "say" and b.get("text")]
    spec = {c["name"]: c.get("speech") for c in scene["cast"]}
    cast = {c["name"]: c for c in scene["cast"]}
    voices, taken = {}, set()
    for c in scene["cast"]:
        if ENGINE == "qwen":
            v = qwen_speech(actors[c["name"]], c, taken) | {k: x for k, x in (c.get("speech") or {}).items()
                                                            if k in ("speaker", "instruct")}
            taken.add(v["speaker"])
            voices[c["name"]] = v
    lines = []
    for i, b in enumerate(says):
        act = actors[b["who"]]
        if ENGINE == "qwen":
            v = voices[b["who"]]
        else:
            v = default_speech(act) | (spec.get(b["who"]) or {})
        lines.append({"text": b["text"], "pan": (act.x_at(b["t"]) - .5) * 1.4, "voice": v, "seed": act.seed + i})
    if TTS_DIRECT:                  # straight to the Qwen3-TTS worker (tts_server.py)
        out = speak_direct(lines, url, os.path.join(OUT_DIR, "voice"))
    else:                           # through a sound server that offers /api/voice
        req = urllib.request.Request(url.rstrip("/") + "/api/voice", data=json.dumps({"name": name, "lines": lines}).encode(),
                                     headers={"Content-Type": "application/json"})
        out = json.load(urllib.request.urlopen(req, timeout=600))
        if not out.get("ok"):
            raise SystemExit(f"voice server: {out}")
    for b, r in zip(says, out["lines"]):
        b["seconds"], b["mouths"], b["audio"] = r["seconds"], r["mouths"], r["path"]
    # re-time: shift everything after a line that would start before the last one finished
    shift, free = 0.0, 0.0
    for b in sorted(scene["beats"], key=lambda b: b["t"]):
        b["t"] = round(b["t"] + shift, 3)
        if b["do"] == "say" and b.get("seconds"):
            if b["t"] < free:
                shift += free - b["t"]
                b["t"] = round(free, 3)
            free = b["t"] + b["seconds"] + .25
    return says


def mouths_from_audio(x, sr):
    """Mouth shapes from the sound, every 10 ms: quiet -> closed, hiss -> spread, loud -> open, else round."""
    import numpy as np
    hop = max(1, sr // 100)
    frames = []
    for i in range(0, len(x), hop):
        c = x[i:i + hop]
        rms = float(np.sqrt(np.mean(c ** 2)) + 1e-9)
        zc = float(np.mean(np.signbit(c[1:]) != np.signbit(c[:-1]))) if len(c) > 1 else 0.0
        frames.append((20 * np.log10(rms), zc))
    top = max(f[0] for f in frames)
    out, held = [], 0
    for i, (db, zc) in enumerate(frames):
        rel = db - top
        shape = "flat" if rel < -32 else "smile" if zc > .22 else "grin" if rel > -9 else "o"
        held += 1
        if (not out or out[-1][1] != shape) and (held >= 4 or not out):
            out.append([round(i * hop / sr, 3), shape])
            held = 0
    if out[-1][1] != "flat":
        out.append([round(len(frames) * hop / sr, 3), "flat"])
    return out


def speak_direct(lines, url, folder):
    """Each line on the TTS worker; padded, panned, normalised here. Same answer as /api/voice."""
    import urllib.request
    import numpy as np
    import soundfile as sf
    os.makedirs(folder, exist_ok=True)
    res = []
    for i, l in enumerate(lines):
        raw, wav = os.path.join(folder, f"{i:03d}.raw.wav"), os.path.join(folder, f"{i:03d}.wav")
        v = l["voice"]
        body = {"text": l["text"], "speaker": v.get("speaker", "ryan"), "instruct": v.get("instruct", ""), "out": raw}
        req = urllib.request.Request(url.rstrip("/") + "/tts", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        json.load(urllib.request.urlopen(req, timeout=600))
        x, sr = sf.read(raw, dtype="float64")
        if x.ndim > 1:
            x = x.mean(axis=1)
        x = np.concatenate([np.zeros(int(.12 * sr)), x, np.zeros(int(.1 * sr))])
        x = x * (10 ** (-3 / 20) / (np.abs(x).max() or 1))
        th = (max(-1, min(1, l["pan"])) * .6 + 1) * math.pi / 4
        sf.write(wav, np.stack([x * math.cos(th), x * math.sin(th)], axis=1), sr, subtype="PCM_24")
        os.remove(raw)
        res.append({"text": l["text"], "path": os.path.abspath(wav), "seconds": round(len(x) / sr, 3),
                    "mouths": mouths_from_audio(x, sr)})
    return {"ok": True, "lines": res}


def mix_voices(says, video, dur, out):
    """Each line's WAV at the moment it is said, under the picture."""
    ins, parts = [], []
    for i, b in enumerate(says):
        ms = int(b["t_said"] * 1000)
        ins += ["-i", b["audio"]]
        parts.append(f"[{i + 1}:a]adelay={ms}|{ms}[d{i}]")
    mixed = "".join(f"[d{i}]" for i in range(len(says)))
    filt = ";".join(parts) + f";{mixed}amix=inputs={len(says)}:normalize=0,apad,atrim=0:{dur:.3f},volume=0.9[a]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video] + ins +
                   ["-filter_complex", filt, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    out], check=True)


def render_png(args):
    svg_path, png_path = args
    import resvg_py
    data = resvg_py.svg_to_bytes(svg_path=svg_path)
    with open(png_path, "wb") as fh:
        fh.write(bytes(data))
    return png_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--out", required=True)
    ap.add_argument("--render", action="store_true", help="also rasterise (resvg) and encode MP4 (ffmpeg)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--style", default="v2", choices=["v1", "v2"], help="character style")
    ap.add_argument("--palette", default="pastel", choices=["skin", "pastel"], help="v2 head colours")
    ap.add_argument("--engine", default="qwen", choices=["qwen", "fof"],
                    help="qwen: Qwen3-TTS neural voices (tts_server.py); fof: formant synthesis in Csound")
    ap.add_argument("--tts", default="", help="Qwen3-TTS worker URL (tts_server.py), e.g. http://127.0.0.1:8091: "
                    "voices without a sound server")
    ap.add_argument("--voice", nargs="?", const=os.environ.get("SOUND_SERVER", "http://127.0.0.1:8080"),
                    help="speak the lines on the sonic-forge server (default $SOUND_SERVER or localhost:8080)")
    a = ap.parse_args()
    global ENGINE, STYLE, PALETTE, TTS_DIRECT, OUT_DIR
    ENGINE, STYLE, PALETTE = a.engine, a.style, a.palette
    OUT_DIR = a.out
    if a.tts:
        TTS_DIRECT, a.voice = True, a.tts

    scene = json.load(open(a.scene))
    says = []
    if a.voice:
        actors, _, _ = compile_scene(scene)
        says = voice_scene(scene, actors, a.voice, os.path.basename(os.path.normpath(a.out)))
    actors, dur, things = compile_scene(scene)
    os.makedirs(a.out, exist_ok=True)
    json.dump([{"who": b["who"], "text": b["text"], "t": round(b.get("t_said", b["t"]), 3),
                "dur": round(b.get("seconds") or len(b["text"].split()) / READ_WPS, 3)}
               for b in sorted(scene["beats"], key=lambda b: b["t"]) if b["do"] == "say" and b.get("text")],
              open(os.path.join(a.out, "lines.json"), "w"), indent=1)       # for captions
    import shutil
    for sub in ("svg", "png"):
        shutil.rmtree(os.path.join(a.out, sub), ignore_errors=True)
    os.makedirs(os.path.join(a.out, "svg"), exist_ok=True)
    n = int(dur * FPS)
    for f in range(n):
        with open(os.path.join(a.out, "svg", f"{f:05d}.svg"), "w") as fh:
            fh.write(frame_svg(scene, actors, f / FPS, f, things))
    print(f"{n} frames, {dur:.1f}s")
    if not a.render:
        return
    from multiprocessing import Pool
    os.makedirs(os.path.join(a.out, "png"), exist_ok=True)
    jobs = [(os.path.join(a.out, "svg", f"{f:05d}.svg"), os.path.join(a.out, "png", f"{f:05d}.png")) for f in range(n)]
    with Pool(a.jobs) as pool:
        pool.map(render_png, jobs, chunksize=4)
    mp4 = os.path.join(a.out, "scene.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i",
                    os.path.join(a.out, "png", "%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "18", mp4], check=True)
    if says:
        silent = os.path.join(a.out, "picture.mp4")
        os.replace(mp4, silent)
        mix_voices(says, silent, n / FPS, mp4)
    print(mp4)


if __name__ == "__main__":
    main()
