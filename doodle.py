#!/usr/bin/env python3
"""Procedural doodle characters as SVG. Pure Python, no dependencies.

    python3 doodle.py --seed 7 --out one.svg            # one character
    python3 doodle.py --sheet 4x3 --seed 100 --out sheet.svg
    python3 doodle.py --seed 7 --boil 3 --out boil.svg  # animated line boil

Each seed gives the same character every time. --boil draws the same
character several times with fresh pen jitter and flips between them,
the classic hand-drawn "line boil" look.
"""
import argparse
import math
import random

INK = "#1d1b19"
PALETTE = ["#ffd166", "#ef476f", "#06d6a0", "#118ab2", "#f78c6b",
           "#c3a6ff", "#9ee493", "#ffadad", "#a0e7e5", "#fdffb6"]


# ---------- pen: everything is drawn with a slightly shaky hand ----------

def smooth_closed(pts):
    """Catmull-Rom through closed points -> cubic bezier path."""
    n = len(pts)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d + "Z"


def smooth_open(pts):
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


class Pen:
    def __init__(self, rng, shake=1.6, width=3.2):
        self.rng, self.shake, self.width = rng, shake, width
        self.out = []

    def j(self, p, k=1.0):
        s = self.shake * k
        return (p[0] + self.rng.uniform(-s, s), p[1] + self.rng.uniform(-s, s))

    def closed(self, pts, fill="none", w=None, passes=2):
        w = w or self.width
        if fill != "none":  # flat fill, a bit off-register like a cheap print
            off = [(x + 3, y + 3) for x, y in pts]
            self.out.append(f'<path d="{smooth_closed(off)}" fill="{fill}"/>')
        for k in range(passes):
            jp = [self.j(p) for p in pts]
            op = 1 if k == 0 else 0.55
            self.out.append(f'<path d="{smooth_closed(jp)}" fill="none" stroke="{INK}" '
                            f'stroke-width="{w if k == 0 else w * .6:.1f}" opacity="{op}" '
                            'stroke-linejoin="round"/>')

    def line(self, pts, w=None, passes=2, color=INK):
        w = w or self.width
        for k in range(passes):
            jp = [self.j(p) for p in pts]
            op = 1 if k == 0 else 0.5
            self.out.append(f'<path d="{smooth_open(jp)}" fill="none" stroke="{color}" '
                            f'stroke-width="{w if k == 0 else w * .6:.1f}" opacity="{op}" '
                            'stroke-linecap="round" stroke-linejoin="round"/>')

    def dot(self, p, r, fill=INK):
        x, y = self.j(p, .4)
        self.out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}"/>')


def ellipse(cx, cy, rx, ry, n=14, rot=0.0):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = rx * math.cos(a), ry * math.sin(a)
        pts.append((cx + x * math.cos(rot) - y * math.sin(rot),
                    cy + x * math.sin(rot) + y * math.cos(rot)))
    return pts


# ---------- the character: a "genome" picked once per seed ----------

def genome(seed, sex=None):
    r = random.Random(seed)
    head_col = r.choice(PALETTE)
    return {
        "head": r.choice(["round", "egg", "wide", "bean"]),
        "harm": [(r.randint(2, 5), r.uniform(.015, .04), r.uniform(0, 6.28)) for _ in range(3)],
        "head_color": head_col,
        "body_color": r.choice([c for c in PALETTE if c != head_col]),
        "sex": r.choice(["female", "male"]),
        "waist": r.uniform(.22, .32),     # male: half-width at the bottom of the cone, x R
        "neck": r.uniform(.10, .2),       # half-width at the top of the cone, x R
        "base": r.uniform(.5, .75),       # half-width at the bottom of the cone, x R
        "height": r.uniform(1.0, 1.3),    # cone height, x R
        "eyes": r.choice([1, 2, 2, 2, 3]),
        "eye_style": r.choice(["googly", "dot", "sleepy", "googly"]),
        "look": (r.uniform(-1, 1), r.uniform(-1, 1)),
        "mouth": r.choice(["smile", "grin", "o", "flat", "teeth", "frown"]),
        "arms": r.choice(["wave", "down", "up", "hips"]),
        "legs": r.choice([2, 2, 2, 3]),
        "top": r.choice(["none", "antenna", "hair", "hat", "horns", "sprout", "none"]),
        "blush": r.random() < .5,
        "buttons": r.choice([0, 0, 2, 3]),
        "size": r.uniform(.9, 1.05),
    } | ({"sex": sex} if sex else {})


ROLES = ["cop", "hero", "chef", "pirate", "wizard", "doctor", "firefighter", "ninja", "royal", "astronaut", "detective"]


def apply_role(g, role, seed):
    """Dress a character for a role. Uses its own rng, so the base look of a seed stays."""
    r = random.Random(seed * 31 + 7)
    if role == "any":
        role = r.choice(ROLES)
    g["role"] = role
    if role == "cop":
        g.update(body_color="#2d4a7a", top="none", buttons=3,
                 mouth=r.choice(["smile", "flat", "grin"]))
    elif role == "hero":
        g.update(body_color=r.choice(["#d62828", "#1d4ed8"]), top="none", buttons=0,
                 cape=r.choice(["#ffd166", "#d62828", "#1d1b19"]))
        if g["cape"] == g["body_color"]:
            g["cape"] = "#ffd166"
    elif role == "chef":
        g.update(body_color="#ffffff", top="none", buttons=2, eyes=2,
                 mouth=r.choice(["smile", "grin", "o"]))
    elif role == "pirate":
        g.update(body_color="#ffffff", top="none", buttons=0, eyes=2,
                 eye_style=r.choice(["googly", "dot"]), mouth=r.choice(["grin", "teeth", "smile"]))
    elif role == "wizard":
        g.update(body_color="#5b3e96", top="none", buttons=0,
                 hair_color=r.choice(["#c0c0c8", "#2b2d42", "#b5651d", "#e8c547"]))
    elif role == "doctor":
        g.update(body_color="#e9f5f2", top="none", buttons=2)
    elif role == "firefighter":
        g.update(body_color="#f2c14e", top="none", buttons=0)
    elif role == "ninja":
        g.update(body_color="#2b2d42", top="none", buttons=0, eyes=2, blush=False,
                 eye_style=r.choice(["googly", "dot"]))
    elif role == "royal":
        g.update(body_color=r.choice(["#b23a48", "#3d5a9e"]), top="none", buttons=0)
    elif role == "astronaut":
        g.update(body_color="#f1f1f1", top="none", buttons=0)
    elif role == "detective":
        g.update(body_color="#c8a978", top="none", buttons=2, eyes=min(g["eyes"], 2))
    return g


# ---------- style v2: a fixed identity, and a face that shows the current push ----------
#
# The body (head shape, hair, colours, proportions) belongs to the character and never changes.
# The push can change from line to line, so it shows only on the face: eyes, brows, resting mouth.

# persona push -> eyes, brows, resting mouth (applied per frame, from the push now active)
PERSONA_FACE = {
    "suspicious":    ("narrow", "angled", "flat"),
    "curt":          ("narrow", "flat_low", "flat"),
    "dismissive":    ("halflid", "raised_one", "flat"),
    "upbeat":        ("big", "high", "grin"),
    "flattering":    ("big", "high", "smile"),
    "ornate":        ("halflid", "raised_one", "smile"),
    "condescending": ("halflid", "raised_one", "flat"),
    "wistful":       ("halflid", "worried", "smile"),
    "poetic":        ("big", "high", "smile"),
    "oracle":        ("closed", "flat", "flat"),
    "bleak":         ("halflid", "worried", "frown"),
    "hostile":       ("narrow", "angry", "teeth"),
    "contemptuous":  ("narrow", "raised_one", "flat"),
}
HEADS = ["round", "egg", "tall", "square", "egg_narrow", "bean"]


def expression_for(persona):
    """The face a push wears: (eyes, brows, resting mouth); a neutral face when there is no push."""
    return PERSONA_FACE.get(persona or "", ("googly", "flat", "smile"))
SKIN = ["#f8d9c4", "#f1c3a1", "#e0a57f", "#c68660", "#9c6646", "#74472f"]
PASTEL = ["#ffd6a5", "#fdffb6", "#caffbf", "#9bf6ff", "#a0c4ff", "#bdb2ff", "#ffc6ff", "#ffadad"]
HAIR_COLORS = ["#2b2018", "#4a3426", "#7a4e2d", "#c08a4a", "#e8c547", "#a33b20"]
HAIR = {"female": ["bob", "long", "bun", "ponytail"], "male": ["tuft", "side", "short", "bald"]}


def apply_style(g, seed, palette="skin", hair=None, hair_color=None, head=None):
    """Style v2, from the character's seed only: a head shape from a curated set, two eyes and
    brows, hair, a calmer palette, a bigger head. `palette` is "skin" (human tones) or "pastel".
    The personality push is not used here: it changes over time and shows on the face instead."""
    r = random.Random(seed * 13 + 5)
    g.update(style="v2", head=head or r.choice(HEADS), eye_style="googly", brows="flat", eyes=2, legs=2,
             head_scale=1.12, harm=[(k, amp * .35, ph) for k, amp, ph in g["harm"]], look=(0, 0))
    if g.get("role", "none") not in ("ninja", "wizard"):
        g["mouth"] = "smile"
    if g.get("role", "none") == "none":
        g["top"] = "none"
    g["head_color"] = r.choice(SKIN if palette == "skin" else PASTEL)
    g["hair"] = hair or r.choice(HAIR[g["sex"]])
    g["hair_color"] = hair_color or r.choice(HAIR_COLORS)
    g["blush"] = g["sex"] == "female" or r.random() < .3
    return g


def head_point(g, a, hx, hy, Rh):
    sx, sy = {"round": (1, 1), "egg": (.88, 1.08), "wide": (1.18, .9), "bean": (.95, 1),
              "egg_narrow": (.8, 1.1), "tall": (.86, 1.16), "square": (1.0, .98)}[g["head"]]
    rr = 1 + sum(amp * math.sin(k * a + ph) for k, amp, ph in g["harm"])
    if g["head"] in ("egg", "egg_narrow"):
        rr *= 1 - .08 * math.sin(a)  # wider at the top
    if g["head"] == "square":        # a superellipse: flat sides, rounded corners
        c, s_ = abs(math.cos(a)), abs(math.sin(a))
        rr *= 1 / ((c ** 4 + s_ ** 4) ** .25) * .92
    return hx + Rh * rr * sx * math.cos(a), hy + Rh * rr * sy * math.sin(a)


def star(cx, cy, r, n=5):
    return [(cx + (r if i % 2 == 0 else r * .45) * math.cos(-math.pi / 2 + i * math.pi / n),
             cy + (r if i % 2 == 0 else r * .45) * math.sin(-math.pi / 2 + i * math.pi / n)) for i in range(2 * n)]


def anchors(g, R):
    """Where things sit relative to the centre y: feet bottom and top of head (both as dy)."""
    R *= g["size"]
    H, Rh = R * g["height"], R * .52 * g.get("head_scale", 1)
    hy = -H * .5 - Rh * .55 - R * .15
    return {"feet": H * .5 + R * .4 + 9, "head": hy, "top": hy - Rh * 1.1, "Rh": Rh}


def draw_character(g, cx, cy, R, pen_seed, pose=None):
    """pose (all optional): arms=((a, b), (a, b)) left/right shoulder and elbow degrees,
    0 = hanging down, + = out and up; legs=[(dx, lift), ...] per leg; blink; mouth; look=(x, y)."""
    pose = pose or {}
    rng = random.Random(pen_seed)
    pen = Pen(rng)
    R *= g["size"]
    role = g.get("role", "none")

    # layout, top to bottom: head, cone body, legs
    H = R * g["height"]
    Rh = R * .52 * g.get("head_scale", 1)
    hy = cy - H * .5 - Rh * .55 - R * .15
    v2 = g.get("style") == "v2"
    W_OUT, W_LIMB = (4.4, 4.6) if v2 else (3.6, 3.2)     # line hierarchy: bold outline, sturdy limbs
    # cloth reacts: `talk` (0-1, how open the mouth is now), `sway` (-1..1, body motion), `t` (seconds)
    talk, sway, tt = float(pose.get("talk", 0.0)), float(pose.get("sway", 0.0)), float(pose.get("t", 0.0))
    flut = lambda k: math.sin(tt * (5 + 5 * talk) + k * 1.7) * (1 + 1.6 * talk)
    ny = hy + Rh * .8               # neck: top of the cone, hidden under the chin
    by = ny + H                      # base of the cone
    male = g["sex"] == "male"
    if male:   # inverted cone: broad shoulders, narrow waist
        tw, bw = R * g["base"], R * g["waist"]
    else:      # cone: narrow neck, wide hem
        tw, bw = R * g["neck"], R * g["base"]
    side = lambda t, s: (cx + s * (tw + (bw - tw) * t), ny + H * t)
    sag = R * (.03 if male else .07)  # the base bows down a little

    shoulder_t = .08 if male else .22
    if role == "hero":  # cape hangs behind the whole body
        ls, rs = side(shoulder_t, -1), side(shoulder_t, 1)
        flare = max(tw, bw) + R * .3
        hem = by + R * .2
        cape = [ls, rs, (cx + flare * .8, (ny + hem) / 2), (cx + flare, hem)]
        cape += [(cx + flare * u - sway * R * .14 + flut(k) * R * .025, hem + (R * .06 if k % 2 else 0) + flut(k + 2) * R * .02)
                 for k, u in enumerate((.6, .2, -.2, -.6))]
        cape += [(cx - flare - sway * R * .12, hem), (cx - flare * .8 - sway * R * .06, (ny + hem) / 2)]
        cape[3] = (cape[3][0] - sway * R * .12, cape[3][1])
        pen.closed(cape, fill=g["cape"], w=3)

    if role == "astronaut":  # life-support pack behind the body
        bw_ = max(tw, bw) * .85
        pen.closed([(cx - bw_, ny + H * .05), (cx + bw_, ny + H * .05), (cx + bw_, ny + H * .7), (cx - bw_, ny + H * .7)],
                   fill="#b8bec8", w=3)

    # legs first, so the cone covers their tops
    nl = 2 if male else g["legs"]  # a narrow waist has room for two
    for i in range(nl):
        u = (i - (nl - 1) / 2) / max(nl - 1, 1)
        hip = (cx + u * bw * .9, by + sag * math.cos(u * math.pi / 2) - 6)
        dx, lift = (pose.get("legs") or [(0, 0)] * nl)[i % len(pose.get("legs") or [0])]
        foot = (hip[0] + u * R * .1 + dx, by + R * .42 - lift)
        knee = ((hip[0] + foot[0]) / 2 + rng.uniform(-3, 3) + lift * .35, (hip[1] + foot[1]) / 2)
        pen.line([hip, knee, foot], w=W_LIMB)
        s = 1 if u >= 0 else -1
        pen.closed(ellipse(foot[0] + s * 8, foot[1] + 2, 13, 7, 10), fill=INK, w=2.4, passes=1)

    # cone body
    top_edge = [(cx + tw * u, ny - R * .04 * math.cos(u * math.pi / 2)) for u in (-.5, 0, .5)] if male else []
    pts = top_edge + [side(t, 1) for t in (0, .25, .5, .75, .95)]
    pts += [(cx + bw * u, by + sag * math.cos(u * math.pi / 2)) for u in (.92, .5, 0, -.5, -.92)]
    pts += [side(t, -1) for t in (.95, .75, .5, .25, 0)]
    pen.closed(pts, fill=g["body_color"], w=W_OUT)
    half = lambda t: tw + (bw - tw) * t  # half-width of the cone at t
    if role == "pirate":  # sailor stripes
        for t in (.25, .45, .65, .85):
            pen.line([(cx - half(t) + 4, ny + H * t), (cx + half(t) - 4, ny + H * t)], w=6, passes=1, color="#d62828")
    if role == "wizard":  # stars on the robe
        for t, u in ((.4, -.4), (.6, .35), (.82, -.1)):
            pen.closed(star(cx + u * half(t), ny + H * t, 7), fill="#ffd166", w=1.4, passes=1)
    if role == "hero":  # chest emblem and belt
        ey_ = ny + H * .3
        pen.closed([(cx, ey_ - 16), (cx + 18, ey_), (cx, ey_ + 16), (cx - 18, ey_)], fill="#ffd166", w=2.4, passes=1)
        pen.line([(cx + 4, ey_ - 9), (cx - 4, ey_ + 1), (cx + 4, ey_ - 1), (cx - 4, ey_ + 9)], w=2.2, passes=1)
        pen.line([(cx - half(.72) + 3, ny + H * .72), (cx + half(.72) - 3, ny + H * .72)], w=7, passes=1, color="#ffd166")
    if role == "cop":  # gold star badge on the chest
        pen.closed(star(cx - half(.25) * .5, ny + H * .25, 10), fill="#ffd166", w=1.8, passes=1)
    if role == "doctor":  # stethoscope round the neck, the chest piece hanging
        swing = -sway * 10 + flut(1) * 2.5
        pen.line([(cx - R * .16, ny + 2), (cx - R * .2, ny + H * .25), (cx - R * .06 + swing, ny + H * .42)], w=3, passes=1, color="#555")
        pen.line([(cx + R * .16, ny + 2), (cx + R * .2, ny + H * .25), (cx + R * .06 + swing, ny + H * .42)], w=3, passes=1, color="#555")
        pen.closed(ellipse(cx + swing, ny + H * .46, 9, 9, 10), fill="#c9ced6", w=2.2, passes=1)
        pen.closed([(cx + half(.3) * .35, ny + H * .3), (cx + half(.3) * .75, ny + H * .3),
                    (cx + half(.3) * .75, ny + H * .4), (cx + half(.3) * .35, ny + H * .4)], fill="#ffffff", w=1.8, passes=1)
    if role == "firefighter":  # reflective stripes
        for t in (.55, .78):
            pen.line([(cx - half(t) + 4, ny + H * t), (cx + half(t) - 4, ny + H * t)], w=9, passes=1, color="#e8e8e8")
            pen.line([(cx - half(t) + 4, ny + H * t), (cx + half(t) - 4, ny + H * t)], w=2, passes=1, color="#9aa0a6")
    if role == "ninja":  # sash
        pen.line([(cx - half(.5) + 3, ny + H * .5), (cx + half(.5) - 3, ny + H * .5)], w=7, passes=1, color="#d62828")
        knot = (cx + half(.5) * .6, ny + H * .5)
        for k in (0, 1):
            end = (knot[0] + half(.5) * (.3 + .1 * k) - sway * R * .18 + flut(k) * R * .03, ny + H * (.68 + .06 * k))
            pen.line([knot, ((knot[0] + end[0]) / 2 + flut(k + 3) * R * .02, (knot[1] + end[1]) / 2), end], w=4, passes=1, color="#d62828")
    if role == "royal":  # ermine trim at the hem and a gold chain
        y = by - 8
        pen.line([(cx - bw + 6, y), (cx + bw - 6, y)], w=12, passes=1, color="#ffffff")
        for k in range(-3, 4):
            pen.dot((cx + k * bw * .25, y), 2.5)
        swing = -sway * 9 + flut(2) * 2
        pen.line([(cx - R * .2, ny + 4), (cx + swing, ny + H * .22), (cx + R * .2, ny + 4)], w=3, passes=1, color="#e0a800")
        pen.closed(ellipse(cx + swing, ny + H * .24, 7, 7, 8), fill="#ffd166", w=1.6, passes=1)
    if role == "astronaut":  # chest control panel
        px_, py_ = cx - 22, ny + H * .3
        pen.closed([(px_, py_), (px_ + 44, py_), (px_ + 44, py_ + 26), (px_, py_ + 26)], fill="#d0d6de", w=2, passes=1)
        for k, col in enumerate(("#ef476f", "#06d6a0", "#118ab2")):
            pen.dot((px_ + 9 + k * 13, py_ + 13), 4, fill=col)
    if role == "detective":  # trench coat lapels and belt
        pen.line([(cx - R * .14, ny + 2), (cx, ny + H * .3), (cx + R * .14, ny + 2)], w=3, passes=1)
        pen.line([(cx - half(.6) + 3, ny + H * .6), (cx + half(.6) - 3, ny + H * .6)], w=7, passes=1, color="#7a5a3a")
        bk = (cx + half(.6) * .45, ny + H * .6)
        for k in (0, 1):   # the belt's loose ends hang and swing
            pen.line([bk, (bk[0] + 6 + k * 6 - sway * R * .12 + flut(k) * 3, bk[1] + R * (.2 + .06 * k))], w=5, passes=1, color="#7a5a3a")
    if role == "chef":  # red neckerchief
        pen.closed([(cx - R * .17, ny + 2), (cx + R * .17, ny + 2), (cx, ny + R * .28)], fill="#d62828", w=2.2, passes=1)
    for k in range(g["buttons"]):
        pen.dot((cx, ny + H * (.35 + k * .2)), 4)

    # arms from the shoulders, a little below the neck
    for s in (-1, 1):
        sh = side(shoulder_t, s)
        style = g["arms"] if not (g["arms"] == "wave" and s < 0) else "down"
        L = R * .75
        arm = pose.get("arms")
        if arm:  # explicit angles: shoulder a, elbow b, measured from hanging straight down
            a_, b_ = (math.radians(v) for v in arm[0 if s < 0 else 1])
            L1, L2 = L * .5, L * .48
            mid = (sh[0] + s * L1 * math.sin(a_), sh[1] + L1 * math.cos(a_))
            hand = (mid[0] + s * L2 * math.sin(a_ + b_), mid[1] + L2 * math.cos(a_ + b_))
            style = "posed"
        elif style == "down":
            mid, hand = (sh[0] + s * L * .4, sh[1] + L * .4), (sh[0] + s * L * .55, sh[1] + L * .85)
        elif style in ("up", "wave"):
            mid, hand = (sh[0] + s * L * .55, sh[1] - L * .15), (sh[0] + s * L * .65, sh[1] - L * .7)
        else:  # hips: elbow out, hand back on the cone
            hip = side(.6, s)
            mid, hand = (sh[0] + s * L * .5, sh[1] + L * .25), (hip[0] - s * 5, hip[1])
        pen.line([sh, mid, hand], w=W_LIMB)
        if v2 and style != "hips":  # a mitten hand
            pen.closed(ellipse(hand[0], hand[1], R * .075, R * .075, 10), fill=g["head_color"], w=2.6, passes=1)
        elif style != "hips":  # three little fingers
            ang = math.atan2(hand[1] - mid[1], hand[0] - mid[0])
            for f in (-.6, 0, .6):
                pen.line([hand, (hand[0] + 9 * math.cos(ang + f), hand[1] + 9 * math.sin(ang + f))], w=2.4, passes=1)

    # head, drawn over the neck
    hp = lambda a: head_point(g, a, cx, hy, Rh)
    if role == "wizard" and not male:  # long hair falling past the shoulders
        hw0 = abs(hp(0)[0] - cx)
        hair = [(cx + hw0 * .95, hy + Rh * 1.35), (cx + hw0 * 1.2, hy + Rh * .6)]
        hair += [(cx + (x - cx) * 1.12, hy + (y - hy) * 1.12) for x, y in
                 (hp(-k * math.pi / 8) for k in range(9))]
        hair += [(cx - hw0 * 1.2, hy + Rh * .6), (cx - hw0 * .95, hy + Rh * 1.35), (cx, hy + Rh * 1.1)]
        pen.closed(hair, fill=g["hair_color"], w=3)
    hair = g.get("hair") if v2 and role != "ninja" else None
    hwk = abs(hp(0)[0] - cx)
    if hair in ("long", "bob"):                       # behind the head
        drop = Rh * (1.3 if hair == "long" else .55)
        back = [(cx + hwk * (1.08 if hair == "bob" else .98), hy + drop), (cx + hwk * 1.18, hy + drop * .45)]
        back += [(cx + (x - cx) * 1.1, hy + (y - hy) * 1.1) for x, y in (hp(-k * math.pi / 8) for k in range(9))]
        back += [(cx - hwk * 1.18, hy + drop * .45), (cx - hwk * (1.08 if hair == "bob" else .98), hy + drop),
                 (cx, hy + drop * .8)]
        pen.closed(back, fill=g["hair_color"], w=3)
    elif hair == "ponytail":
        pen.closed(ellipse(cx + hwk * 1.05, hy + Rh * .15, Rh * .26, Rh * .5, 12, rot=-.35), fill=g["hair_color"], w=3)
    pen.closed([hp(2 * math.pi * i / 20) for i in range(20)], fill=g["head_color"], w=W_OUT)
    top = hp(-math.pi / 2)
    Rt = Rh * 1.4  # scale for things on top of the head
    if hair and hair != "bald":                        # the hairline over the top of the head
        fringe = {"short": .5, "tuft": .62, "side": .4}.get(hair, .3)
        cap = [(cx + (x - cx) * 1.05, hy + (y - hy) * 1.05)
               for x, y in (hp(math.pi + .12 + k * (math.pi - .24) / 12) for k in range(13))]
        cap += [(cx + hwk * .8, hy - Rh * fringe), (cx + hwk * .3, hy - Rh * (fringe - .1)),
                (cx - hwk * .25, hy - Rh * (fringe + .05)), (cx - hwk * .8, hy - Rh * fringe)]
        pen.closed(cap, fill=g["hair_color"], w=2.8, passes=1)
        if hair == "side":
            pen.line([(cx - hwk * .35, top[1] + 4), (cx - hwk * .25, hy - Rh * (fringe + .05))], w=2.2, passes=1)
        if hair == "tuft":
            for k in (-1, 0, 1):
                b_ = hp(-math.pi / 2 + k * .25)
                pen.line([b_, (b_[0] + k * 7, b_[1] - Rh * .28)], w=3.4, passes=1, color=g["hair_color"])
        if hair == "bun":
            pen.closed(ellipse(cx, top[1] - Rh * .14, Rh * .3, Rh * .26, 12), fill=g["hair_color"], w=2.8, passes=1)
    elif hair == "bald":
        pen.line([(top[0] - 4, top[1] + 2), (top[0] - 8, top[1] - Rh * .14)], w=1.8, passes=1)
        pen.line([(top[0] + 3, top[1] + 2), (top[0] + 6, top[1] - Rh * .12)], w=1.8, passes=1)

    t = g["top"]
    if t == "antenna":
        tip = (top[0] + rng.uniform(-10, 10), top[1] - Rt * .45)
        pen.line([(top[0], top[1] + 4), (top[0] + 6, top[1] - Rt * .2), tip])
        pen.closed(ellipse(*tip, 7, 7, 8), fill="#ef476f", w=2.4, passes=1)
    elif t == "hair":
        for k in range(-2, 3):
            b = hp(-math.pi / 2 + k * .22)
            pen.line([b, (b[0] + k * 6 + rng.uniform(-3, 3), b[1] - Rt * .25 - rng.uniform(0, 8))], w=2.6)
    elif t == "hat":
        w = Rh * .85
        pen.closed([(top[0] - w, top[1] + 6), (top[0] + w, top[1] + 6),
                    (top[0] + w * .5, top[1] - 2), (top[0] + w * .45, top[1] - Rt * .5),
                    (top[0] - w * .45, top[1] - Rt * .5), (top[0] - w * .5, top[1] - 2)],
                   fill=INK, w=2.4, passes=1)
    elif t == "horns":
        for s in (-1, 1):
            b = hp(-math.pi / 2 + s * .6)
            pen.closed([(b[0] - 7, b[1] + 6), (b[0] + s * 9, b[1] - Rt * .35), (b[0] + 7, b[1] + 8)],
                       fill="#fff", w=2.4, passes=1)
    elif t == "sprout":
        tip = (top[0], top[1] - Rt * .3)
        pen.line([(top[0], top[1] + 3), tip], w=2.6)
        for s in (-1, 1):
            pen.closed(ellipse(tip[0] + s * 10, tip[1] - 4, 11, 5, 10, rot=s * -.5), fill="#06d6a0", w=2.2, passes=1)

    hw = abs(hp(0)[0] - cx)  # half-width of the head
    if role == "cop":  # peaked cap
        y0 = top[1] + Rh * .3
        pen.closed([(cx - hw * .95, y0), (cx + hw * .95, y0), (cx + hw * 1.1, y0 - Rh * .55),
                    (cx, y0 - Rh * .68), (cx - hw * 1.1, y0 - Rh * .55)], fill="#2d4a7a", w=2.8, passes=1)
        pen.line([(cx - hw * .95, y0 - 3), (cx + hw * .95, y0 - 3)], w=7, passes=1)
        pen.closed(ellipse(cx, y0 + 5, hw * .8, Rh * .12, 12), fill=INK, w=2, passes=1)
        pen.closed(star(cx, y0 - Rh * .32, 8), fill="#ffd166", w=1.4, passes=1)
    elif role == "chef":  # toque
        y0 = top[1] + Rh * .25
        bob = -abs(flut(0)) * talk * Rh * .06               # the puffs bounce while he talks
        lean_ = -sway * Rh * .12
        pen.closed(ellipse(cx - hw * .45 + lean_, y0 - Rh * .75 + bob, Rh * .4, Rh * .35, 12), fill="#fff", w=2.4, passes=1)
        pen.closed(ellipse(cx + hw * .45 + lean_, y0 - Rh * .75 + bob * .6, Rh * .4, Rh * .35, 12), fill="#fff", w=2.4, passes=1)
        pen.closed(ellipse(cx + lean_ * 1.4, y0 - Rh * .95 + bob * 1.3, Rh * .45, Rh * .4, 12), fill="#fff", w=2.4, passes=1)
        pen.closed([(cx - hw * .75, y0), (cx + hw * .75, y0), (cx + hw * .75, y0 - Rh * .55),
                    (cx - hw * .75, y0 - Rh * .55)], fill="#fff", w=2.4, passes=1)
    elif role == "pirate":  # bandana with a knot
        cap = [hp(math.pi + .25 + k * (math.pi - .5) / 8) for k in range(9)]
        cap += [(cx + hw * .9, hy - Rh * .32), (cx - hw * .9, hy - Rh * .32)]
        pen.closed(cap, fill="#d62828", w=2.8, passes=1)
        kx, ky = cx + hw * .95, hy - Rh * .35
        for d in (-1, 1):
            fx, fy_ = -sway * Rh * .25 + flut(d) * Rh * .05, flut(d + 1) * Rh * .06
            pen.closed([(kx, ky), (kx + Rh * .45 + fx, ky + d * Rh * .2 + Rh * .15 + fy_),
                        (kx + Rh * .4 + fx, ky + d * Rh * .05 + Rh * .3 + fy_)], fill="#d62828", w=2.2, passes=1)
        pen.closed(ellipse(cx - hw * .98, hy + Rh * .3, 5, 5, 8), w=2, passes=1)  # gold earring
        pen.out[-1] = pen.out[-1].replace(f'stroke="{INK}"', 'stroke="#e0a800"')
    elif role == "wizard":  # pointy hat with a brim
        y0 = top[1] + Rh * .2
        tip = (cx + Rh * .5 - sway * Rh * .35 + flut(0) * Rh * .04, y0 - Rh * 1.6 + abs(sway) * Rh * .1)
        pen.closed([(cx - hw * .85, y0), (cx + hw * .85, y0), (cx + Rh * .2, y0 - Rh * .9), tip,
                    (cx - Rh * .15, y0 - Rh * .9)], fill="#5b3e96", w=2.6, passes=1)
        pen.closed(ellipse(cx, y0, hw * 1.25, Rh * .16, 14), fill="#5b3e96", w=2.6, passes=1)
        pen.closed(star(cx - Rh * .05, y0 - Rh * .5, 8), fill="#ffd166", w=1.4, passes=1)

    if role == "firefighter":  # red helmet with a long back brim and a front badge
        y0 = top[1] + Rh * .35
        pen.closed([hp(math.pi + .15 + k * (math.pi - .3) / 10) for k in range(11)] +
                   [(cx + hw * 1.0, y0), (cx - hw * 1.0, y0)], fill="#d62828", w=2.8, passes=1)
        pen.closed(ellipse(cx, y0 + 2, hw * 1.35, Rh * .12, 14), fill="#b01e1e", w=2.4, passes=1)
        pen.closed([(cx - 13, y0 - Rh * .55), (cx + 13, y0 - Rh * .55), (cx + 10, y0 - Rh * .2), (cx, y0 - Rh * .1),
                    (cx - 10, y0 - Rh * .2)], fill="#ffd166", w=1.8, passes=1)
    elif role == "royal":  # crown with five points and jewels
        y0 = top[1] + Rh * .2
        w = hw * .8
        pts = [(cx - w, y0)]
        for k in range(5):
            x0 = cx - w + k * 2 * w / 5
            pts += [(x0 + w / 5, y0 - Rh * .55), (x0 + 2 * w / 5, y0 - Rh * .22)]
        pts[-1] = (cx + w, y0 - Rh * .22)
        pen.closed(pts + [(cx + w, y0)], fill="#ffd166", w=2.6, passes=1)
        for k, col in enumerate(("#ef476f", "#118ab2", "#06d6a0")):
            pen.dot((cx + (k - 1) * w * .55, y0 - Rh * .12), 4.5, fill=col)
    elif role == "detective":  # deerstalker: a cap with peaks front and back, flaps tied on top
        y0 = top[1] + Rh * .32
        pen.closed([hp(math.pi + .25 + k * (math.pi - .5) / 10) for k in range(11)] +
                   [(cx + hw * .95, y0), (cx - hw * .95, y0)], fill="#8b6b4a", w=2.6, passes=1)
        for s_ in (-1, 1):
            pen.closed([(cx + s_ * hw * .7, y0 - 2), (cx + s_ * hw * 1.35, y0 + 6), (cx + s_ * hw * .9, y0 + 10)],
                       fill="#8b6b4a", w=2.2, passes=1)
        pen.closed(ellipse(cx, top[1] - 2, 8, 6, 8), fill="#6b4f35", w=1.8, passes=1)
    elif role == "doctor":  # head mirror on a band
        pen.line([hp(math.pi + .35), (cx, top[1] + Rh * .22), hp(-.35)], w=4, passes=1, color="#555")
        pen.closed(ellipse(cx + hw * .3, top[1] + Rh * .3, Rh * .2, Rh * .2, 12), fill="#dfe6ee", w=2.2, passes=1)
        pen.closed(ellipse(cx + hw * .3, top[1] + Rh * .3, Rh * .06, Rh * .06, 8), fill="#555", w=1, passes=1)
    elif role == "ninja":  # hood over the whole head, a window for the eyes, headband tails
        pen.closed([hp(2 * math.pi * i / 20) for i in range(20)], fill="#2b2d42", w=3.2, passes=1)
        fy0 = hy - Rh * .08
        pen.closed([(cx - hw * .82, fy0 - Rh * .3), (cx + hw * .82, fy0 - Rh * .3),
                    (cx + hw * .82, fy0 + Rh * .26), (cx - hw * .82, fy0 + Rh * .26)], fill=g["head_color"], w=2.2, passes=1)
        kx, ky = cx + hw * .95, fy0 - Rh * .45
        for d in (-1, 1):
            fx, fy_ = -sway * Rh * .3 + flut(d) * Rh * .06, flut(d + 2) * Rh * .08
            pen.line([(kx, ky), (kx + Rh * .4 + fx * .5, ky + d * Rh * .12 + Rh * .2 + fy_ * .5),
                      (kx + Rh * .65 + fx, ky + d * Rh * .2 + Rh * .35 + fy_)], w=5, passes=1, color="#d62828")

    # face, on the head
    fy = hy - Rh * .08
    n = g["eyes"]
    gap = Rh * (.75 if n == 2 else .62)
    er = Rh * (.32 if n == 1 else .24)
    lx, ly = pose.get("look", g["look"])
    emo = pose.get("emotion")
    eye_style = g["eye_style"]
    face_brows = g.get("brows", "flat")
    if v2 and pose.get("persona") is not None:      # the face of the push active now
        eye_style, face_brows, rest_mouth = expression_for(pose["persona"])
        if not pose.get("mouth") and role not in ("ninja",) and not (role == "wizard" and male):
            pose = dict(pose, mouth=rest_mouth)
    if v2:
        er = Rh * .25
        if emo == "surprised":
            eye_style = "big"
        elif emo == "laugh":
            eye_style = "happy"
    for i in range(0 if role == "cop" else n):
        ex = cx + (i - (n - 1) / 2) * gap
        ey = fy - (Rh * .12 if n == 3 and i == 1 else 0)
        st = "sleepy" if pose.get("blink") and eye_style != "happy" else eye_style
        if st == "big":
            pen.closed(ellipse(ex, ey, er * 1.15, er * 1.3, 12), fill="#fff", w=2.6, passes=1)
            pen.dot((ex + lx * er * .45, ey + ly * er * .5), er * .55)
            pen.dot((ex + lx * er * .45 - er * .2, ey + ly * er * .5 - er * .25), er * .18, fill="#fff")
            continue
        if st == "narrow":
            pen.closed(ellipse(ex, ey, er * 1.05, er * .55, 12), fill="#fff", w=2.6, passes=1)
            pen.dot((ex + lx * er * .5, ey + ly * er * .2), er * .38)
            continue
        if st == "halflid":
            pen.closed(ellipse(ex, ey, er, er * 1.05, 12), fill="#fff", w=2.6, passes=1)
            pen.dot((ex + lx * er * .45, ey + er * .2 + ly * er * .3), er * .45)
            lid = [(ex + er * 1.08 * math.cos(math.pi + k * math.pi / 8), ey + er * 1.12 * math.sin(math.pi + k * math.pi / 8))
                   for k in range(9)]
            pen.closed(lid + [(ex + er * 1.08, ey - er * .05), (ex - er * 1.08, ey - er * .05)], fill=g["head_color"], w=2.6, passes=1)
            continue
        if st in ("closed", "happy"):
            up = 1 if st == "happy" else -1
            pen.line([(ex - er, ey), (ex, ey - up * er * .55), (ex + er, ey)], w=3)
            continue
        if st == "dot":
            pen.dot((ex, ey), er * .45)
        elif st == "sleepy":
            pen.line([(ex - er, ey), (ex, ey + er * .5), (ex + er, ey)], w=2.6)
        else:
            pen.closed(ellipse(ex, ey, er, er * 1.1, 12), fill="#fff", w=2.6, passes=1)
            pen.dot((ex + lx * er * .45, ey + ly * er * .45), er * .45)
            pen.dot((ex + lx * er * .45 - er * .15, ey + ly * er * .45 - er * .18), er * .13, fill="#fff")

    if v2 and role != "ninja" or (v2 and role == "ninja"):   # brows carry the emotion
        shape = {"surprised": "high", "laugh": "high", "shrug": "worried"}.get(emo, face_brows)
        lift = pose.get("brow_lift", 0.0) + (er * .35 if emo == "surprised" else 0)
        ARCS = {"flat": (0, 0, 0), "flat_low": (.25, .25, 0), "high": (-.3, -.3, -.25), "angled": (.25, -.2, 0),
                "angry": (.45, -.3, 0), "worried": (-.35, .2, 0)}
        for k, s_ in enumerate((-1, 1)):
            sh_ = shape if shape != "raised_one" else ("high" if k == 0 else "flat_low")
            di, do, arch = ARCS[sh_]
            ex = cx + s_ * gap / 2
            by_ = fy - er * 1.55 - lift
            inner = (ex - s_ * er * .95, by_ + di * er)
            outer = (ex + s_ * er * .95, by_ + do * er)
            mid = ((inner[0] + outer[0]) / 2, (inner[1] + outer[1]) / 2 + arch * er)
            pen.line([inner, mid, outer], w=4.2, passes=1, color="#c9cde3" if role == "ninja" else "#1d1b19")
    if role == "cop":  # aviator sunglasses: teardrop lenses, thin bridge
        for s_ in (-1, 1):
            lc = (cx + s_ * Rh * .37, fy + Rh * .02)
            lens = []
            for k in range(14):
                a_ = 2 * math.pi * k / 14
                dx, dy = Rh * .3 * math.cos(a_), Rh * .24 * math.sin(a_)
                if dy > 0:  # drop the outer-bottom corner
                    dy *= 1 + .45 * max(0, s_ * dx / (Rh * .3))
                lens.append((lc[0] + dx, lc[1] + dy))
            pen.closed(lens, fill="#2b2d42", w=2.4, passes=1)
            pen.line([(lc[0] - Rh * .14, lc[1] - Rh * .05), (lc[0] - Rh * .02, lc[1] - Rh * .13)], w=2, passes=1, color="#fff")
            pen.line([(lc[0] + s_ * Rh * .3, lc[1] - Rh * .1), (cx + s_ * hw * .97, lc[1] - Rh * .14)], w=2, passes=1)
        pen.line([(cx - Rh * .1, fy - Rh * .12), (cx, fy - Rh * .16), (cx + Rh * .1, fy - Rh * .12)], w=2.4, passes=1)
    if role == "pirate":  # patch over the left eye, strap over the head
        px = cx - gap / 2
        pen.line([(cx - hw * .95, fy - Rh * .55), (px, fy), (cx + hw * .97, fy - Rh * .15)], w=2, passes=1)
        pen.closed(ellipse(px, fy, er * 1.15, er * 1.05, 12), fill=INK, w=2, passes=1)

    my, mw = hy + Rh * .45, Rh * .38
    if role == "ninja":   # the mask moves with her jaw: cloth over the nose, cheek folds, the mouth under the cloth
        mm = pose.get("mouth")
        my_, fold = hy + Rh * .52, "#9aa0c8"
        lift_ = talk * Rh * .07
        pen.line([(cx - Rh * .44, my_ - Rh * .22 - lift_), (cx, my_ - Rh * .3 - lift_ * 1.6), (cx + Rh * .44, my_ - Rh * .22 - lift_)],
                 w=3.4, passes=1, color=fold)
        for s_ in (-1, 1):
            pen.line([(cx + s_ * Rh * .58, my_ - Rh * .14), (cx + s_ * Rh * (.4 - .05 * talk), my_ + Rh * (.04 + .12 * talk))],
                     w=3.2, passes=1, color=fold)
        if mm == "o":
            pen.closed(ellipse(cx, my_ + 2, Rh * .11, Rh * .15, 10), fill="#0d0e18", w=2.6, passes=1)
            pen.line([(cx - Rh * .14, my_ - Rh * .12), (cx, my_ - Rh * .17), (cx + Rh * .14, my_ - Rh * .12)], w=2.4, passes=1, color=fold)
        elif mm in ("grin", "teeth"):
            pen.closed(ellipse(cx, my_ + 2, Rh * .24, Rh * .1, 12), fill="#0d0e18", w=2.6, passes=1)
            pen.line([(cx - Rh * .26, my_ - Rh * .1), (cx, my_ - Rh * .16), (cx + Rh * .26, my_ - Rh * .1)], w=2.4, passes=1, color=fold)
        elif mm == "smile":
            pen.line([(cx - Rh * .2, my_), (cx, my_ + Rh * .07), (cx + Rh * .2, my_)], w=3.2, passes=1, color=fold)
        else:
            pen.line([(cx - Rh * .16, my_ + 1), (cx + Rh * .16, my_ + 1)], w=3, passes=1, color=fold)
        if talk > .6:   # a breath stirs the cloth: two small puff marks beside the mouth
            for k in (0, 1):
                px_ = cx + Rh * (.62 + .14 * k)
                pen.line([(px_, my_ - 6 - k * 4), (px_ + 7, my_ - k * 4), (px_, my_ + 6 - k * 4)], w=2.6, passes=1, color="#e3e6f3")
    m = "none" if (role == "wizard" and male) or role == "ninja" else pose.get("mouth") or g["mouth"]
    if m == "smile":
        pen.line([(cx - mw, my), (cx, my + mw * .5), (cx + mw, my)])
    elif m == "frown":
        pen.line([(cx - mw, my + mw * .4), (cx, my), (cx + mw, my + mw * .4)])
    elif m == "flat":
        pen.line([(cx - mw * .7, my), (cx + mw * .7, my + 2)])
    elif m == "o":
        pen.closed(ellipse(cx, my + 3, mw * .3, mw * .4, 10), fill=INK, w=2.4, passes=1)
    elif m == "grin":
        pen.closed([(cx - mw, my), (cx + mw, my), (cx + mw * .5, my + mw * .65), (cx - mw * .5, my + mw * .65)],
                   fill=INK, w=2.6, passes=1)
        pen.closed(ellipse(cx, my + mw * .45, mw * .35, mw * .16, 8), fill="#ef476f", w=1.2, passes=1)
    elif m == "teeth":
        pen.closed([(cx - mw, my), (cx + mw, my), (cx + mw * .8, my + mw * .5), (cx - mw * .8, my + mw * .5)],
                   fill="#fff", w=2.6, passes=1)
        zig = [(cx - mw * .8 + k * mw * .2, my + (mw * .22 if k % 2 else 0)) for k in range(9)]
        pen.line(zig, w=1.8, passes=1)

    if g["blush"]:
        for s in (-1, 1):
            pen.out.append(f'<ellipse cx="{cx + s * Rh * .66:.1f}" cy="{my - 6:.1f}" rx="{Rh * .16:.1f}" '
                           f'ry="{Rh * .09:.1f}" fill="#ff6b8b" opacity=".45"/>')

    if role == "chef" and male:  # handlebar mustache
        for s_ in (-1, 1):
            pen.line([(cx, my - 3), (cx + s_ * mw * .55, my - 1), (cx + s_ * mw * .95, my - 5),
                      (cx + s_ * mw * .9, my - 10)], w=4.5, passes=1)
    if role == "wizard" and male:  # long white beard over the chin and chest
        beard = [(cx + hw * .8, hy + Rh * .1), (cx + hw * .7, hy + Rh * .9), (cx + Rh * .25, hy + Rh * 1.5),
                 (cx, hy + Rh * 1.85), (cx - Rh * .25, hy + Rh * 1.5), (cx - hw * .7, hy + Rh * .9),
                 (cx - hw * .8, hy + Rh * .1), (cx - Rh * .35, hy + Rh * .38), (cx, hy + Rh * .3),
                 (cx + Rh * .35, hy + Rh * .38)]
        pen.closed(beard, fill="#f4f1ea", w=2.8)
        for s_ in (-1, 1):
            pen.line([(cx, hy + Rh * .3), (cx + s_ * Rh * .3, hy + Rh * .32), (cx + s_ * Rh * .45, hy + Rh * .45)],
                     w=4, passes=1)
    if role == "detective":  # a pipe at the corner of the mouth
        px_ = cx + Rh * .32
        pen.line([(px_, my + 4), (px_ + Rh * .35, my + 10)], w=4, passes=1, color="#6b4f35")
        pen.closed([(px_ + Rh * .3, my + 2), (px_ + Rh * .48, my + 2), (px_ + Rh * .46, my + 20), (px_ + Rh * .32, my + 18)],
                   fill="#6b4f35", w=2, passes=1)
    if role in ("hero", "astronaut"):  # glass helmet with a collar ring
        hr = max(hw, Rh) * 1.3
        hc = (cx, hy - Rh * .05)
        pen.out.append(f'<circle cx="{hc[0]:.1f}" cy="{hc[1]:.1f}" r="{hr:.1f}" fill="#bfe9ff" opacity=".28"/>')
        pen.closed(ellipse(hc[0], hc[1], hr, hr, 20), w=3.2 if role == "hero" else 6)
        pen.line([(hc[0] - hr * .7, hc[1] - hr * .2), (hc[0] - hr * .55, hc[1] - hr * .55),
                  (hc[0] - hr * .2, hc[1] - hr * .75)], w=4, passes=1, color="#fff")
        pen.closed(ellipse(hc[0], hc[1] + hr * .92, hr * .62, Rh * .16, 14), fill="#c9ced6", w=2.6, passes=1)
    return "\n".join(pen.out)


# ---------- output ----------

def svg(body, w, h, extra=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'{extra}<rect width="100%" height="100%" fill="#fbf7ef"/>\n{body}\n</svg>\n')


def character(seed, cx, cy, R, boil=1, sex=None, role="none"):
    g = apply_role(genome(seed, sex), role, seed)
    if boil <= 1:
        return draw_character(g, cx, cy, R, seed * 7919)
    frames = []
    for f in range(boil):
        frames.append(f'<g class="f f{f}">{draw_character(g, cx, cy, R, seed * 7919 + f)}</g>')
    return "\n".join(frames)


def boil_css(n, fps=8):
    dur = n / fps
    rules = [f".f{{opacity:0;animation:b {dur:.2f}s steps(1) infinite}}",
             f"@keyframes b{{0%{{opacity:1}}{100 / n:.2f}%{{opacity:0}}}}"]
    rules += [f".f{i}{{animation-delay:{-i / fps:.3f}s}}" for i in range(n)]
    return "<style>" + "".join(rules) + "</style>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sheet", default="", help="COLSxROWS, e.g. 4x3")
    ap.add_argument("--boil", type=int, default=1, help="frames of line boil (animated SVG)")
    ap.add_argument("--sex", choices=["male", "female"], help="default: picked by the seed")
    ap.add_argument("--role", default="none", choices=["none", "any"] + ROLES,
                    help="dress the character; 'any' picks a role per seed")
    ap.add_argument("--out", default="doodle.svg")
    a = ap.parse_args()

    cell, ch, R = 300, 380, 95
    extra = boil_css(a.boil) if a.boil > 1 else ""
    if a.sheet:
        cols, rows = map(int, a.sheet.lower().split("x"))
        parts = [character(a.seed + i, (i % cols + .5) * cell, (i // cols + .5) * ch + 5, R, a.boil, a.sex, a.role)
                 for i in range(cols * rows)]
        doc = svg("\n".join(parts), cols * cell, rows * ch, extra)
    else:
        doc = svg(character(a.seed, cell / 2, ch / 2 + 5, R, a.boil, a.sex, a.role), cell, ch, extra)
    open(a.out, "w").write(doc)
    print(a.out)


if __name__ == "__main__":
    main()
