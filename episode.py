#!/usr/bin/env python3
"""A doodle episode: title card, a card before each scene, the scenes (voiced), an end card.

    python episode.py episodes/ep1 --title "The Doodle Desk" --number 1

The episode folder holds scene1.json ... sceneN.json (scene_writer.py, see episode_write.sh),
optionally tvN.json (a hedwigai program for scene N's TV: {"cmd", "series", "label"}) and
jingle.wav (the cards' music, from sonic-forge). Scenes render with anim.py --voice, so the
sound server and the TTS worker must be up. Output: <folder>/episode.mp4.
"""
import argparse
import datetime as dt
import glob
import json
import math
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import anim as A  # noqa: E402
import doodle as D  # noqa: E402

W, H, FPS = A.W, A.H, A.FPS
PAPER = "#fbf7ef"
CHANNEL_NAMES = {"bbc_world": "BBC News", "bbc_science": "BBC News", "guardian_world": "The Guardian",
                 "aljazeera": "Al Jazeera", "npr": "NPR", "the_hindu": "The Hindu", "gov_uk": "GOV.UK",
                 "us_federal_register": "Federal Register", "ecb": "European Central Bank", "nasa": "NASA",
                 "hacker_news": "Hacker News"}


def run(cmd):
    print("+", " ".join(cmd[:6]), "...", flush=True)
    subprocess.run(cmd, check=True)


# ---------- cards ----------

def lineup(names_roles, y_feet, scale, t, boil, x0=None, x1=None):
    """Characters standing in a row (their real doodles), with a small bob each."""
    out = []
    n = len(names_roles)
    x0 = 120 if x0 is None else x0
    x1 = W - 120 if x1 is None else x1
    for i, c in enumerate(names_roles):
        a = A.Actor(c | {"x": .5})
        cx = x0 + (x1 - x0) * (i + .5) / n
        bob = 4 * math.sin(t * 3 + i)
        anc = D.anchors(a.g, A.R * scale)
        cy = y_feet - anc["feet"] + bob
        arms = [[28, -12], [28, -12]]
        if (int(t * 2) + i) % 4 == 0:      # someone waves now and then
            arms[1] = [125, 25 + 30 * math.sin(t * 18)]
        out.append(D.draw_character(a.g, cx, cy, A.R * scale, a.seed * 7919 + boil,
                                    pose={"arms": arms, "blink": (t + i) % 3.1 < .12}))
        out.append(f'<text x="{cx:.0f}" y="{y_feet + 26:.0f}" font-family="{A.FONT}" font-size="{14 if n > 6 else 18}" '
                   f'text-anchor="middle" fill="{D.INK}">{A.esc(c["name"])}</text>')
    return "\n".join(out)


def card_svg(kind, t, f, ep, scene=None, k=0):
    boil = f // A.BOIL_EVERY % 3
    pen = D.Pen(random.Random(900 + boil), shake=1.4)
    parts = [f'<rect width="{W}" height="{H}" fill="{PAPER}"/>']
    pop = A.smooth(0, .35, t)
    if kind == "intro":
        parts.append(f'<text x="{W / 2}" y="{120 + 20 * (1 - pop):.0f}" font-family="{A.FONT}" font-size="72" '
                     f'text-anchor="middle" fill="{D.INK}" opacity="{pop:.2f}">{A.esc(ep["title"])}</text>')
        parts.append(f'<text x="{W / 2}" y="172" font-family="{A.FONT}" font-size="26" text-anchor="middle" '
                     f'fill="#4a4f57" opacity="{pop:.2f}">Episode {ep["number"]} · {A.esc(ep["date"])} · today\'s news, as the cast saw it</text>')
        pen.line([(W / 2 - 300, 196), (W / 2 + 300, 200)], w=3, passes=2)
        half = (len(ep["cast"]) + 1) // 2           # two rows so nobody overlaps
        parts.append(lineup(ep["cast"][:half], 420, .52, t, boil, 160, W - 160))
        parts.append(lineup(ep["cast"][half:], 655, .52, t + .7, boil, 160, W - 160))
    elif kind == "scene":
        cast = [c for c in scene["cast"]]
        parts.append(f'<text x="{W / 2}" y="150" font-family="{A.FONT}" font-size="30" text-anchor="middle" '
                     f'fill="#4a4f57" opacity="{pop:.2f}">Scene {k}</text>')
        parts.append(f'<text x="{W / 2}" y="{215 + 16 * (1 - pop):.0f}" font-family="{A.FONT}" font-size="58" '
                     f'text-anchor="middle" fill="{D.INK}" opacity="{pop:.2f}">{A.esc(scene.get("title") or "")}</text>')
        src = CHANNEL_NAMES.get(scene["news"].get("channel"), scene["news"].get("channel", ""))
        parts.append(f'<text x="{W / 2}" y="262" font-family="{A.FONT}" font-size="20" text-anchor="middle" '
                     f'fill="#6b717a" opacity="{pop:.2f}">from {A.esc(src)}: {A.esc(scene["news"]["title"][:90])}</text>')
        parts.append(lineup(cast, 590, .75, t, boil, 380, 900))
    else:  # outro
        parts.append(f'<text x="{W / 2}" y="140" font-family="{A.FONT}" font-size="54" text-anchor="middle" '
                     f'fill="{D.INK}" opacity="{pop:.2f}">That was the news.</text>')
        lines = [f"Lines written by {ep['model']}, each character's personality a neuron push",
                 "Voices: Qwen3-TTS · the TVs ran hedwigai shell programs",
                 "Headlines from " + ", ".join(ep["sources"]),
                 "Drawn, voiced and rendered on a Mac mini"]
        for i, l in enumerate(lines):
            op = A.smooth(.3 + i * .25, .6 + i * .25, t)
            parts.append(f'<text x="{W / 2}" y="{210 + i * 36}" font-family="{A.FONT}" font-size="22" text-anchor="middle" '
                         f'fill="#4a4f57" opacity="{op:.2f}">{A.esc(l)}</text>')
        if A.HEDWIGAI_LOGO:
            parts.append(f'<image href="{A.HEDWIGAI_LOGO}" x="{W / 2 - 60}" y="370" width="120" height="105" opacity="{pop:.2f}"/>')
        parts.append(f'<text x="{W / 2}" y="510" font-family="Georgia, serif" font-style="italic" font-size="34" '
                     f'text-anchor="middle" fill="{D.INK}" opacity="{pop:.2f}">hedwigai</text>')
        parts.append(lineup(ep["cast"], 668, .3, t, boil, 90, W - 90))
    parts.append(pen.out and "\n".join(pen.out) or "")
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">' + "\n".join(parts) + "</svg>"


def render_card(out_dir, kind, seconds, ep, jingle, scene=None, k=0, music_from=0.0):
    os.makedirs(os.path.join(out_dir, "svg"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "png"), exist_ok=True)
    n = int(seconds * FPS)
    jobs = []
    for f in range(n):
        sp = os.path.join(out_dir, "svg", f"{f:05d}.svg")
        with open(sp, "w") as fh:
            fh.write(card_svg(kind, f / FPS, f, ep, scene, k))
        jobs.append((sp, os.path.join(out_dir, "png", f"{f:05d}.png")))
    from multiprocessing import Pool
    with Pool(os.cpu_count()) as pool:
        pool.map(A.render_png, jobs, chunksize=4)
    mp4 = os.path.join(out_dir, "card.mp4")
    fade = max(.3, min(1.0, seconds * .3))
    run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(out_dir, "png", "%05d.png"),
         "-ss", f"{music_from:.2f}", "-i", jingle,
         "-filter_complex", f"[1:a]atrim=0:{seconds:.2f},afade=t=out:st={seconds - fade:.2f}:d={fade:.2f},volume=0.5[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", mp4])
    return mp4


# ---------- captions and chapters (for search: YouTube indexes uploaded captions) ----------

def stamp(t, srt=True):
    h, m, sec = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{int(sec):02d},{int((sec % 1) * 1000):03d}" if srt else f"{m}:{int(sec):02d}"


def write_captions_and_chapters(folder, starts, scenes, ep):
    cues, chapters, k = [], [("0:00", "Intro")], 0
    for seg, t0, dur in starts:
        part = os.path.basename(os.path.dirname(seg))      # intro, card1.., scene1.., outro
        if part.startswith("card"):
            k += 1
            sc = scenes[k - 1]
            names = " & ".join(c["name"] for c in sc["cast"])
            chapters.append((stamp(t0, False), f"{sc.get('title') or 'Scene ' + str(k)}: {names} on {sc['news']['title']}"))
        elif seg.endswith("scene.mp4"):
            lines = json.load(open(os.path.join(os.path.dirname(seg), "lines.json")))
            for l in lines:
                cues.append((t0 + l["t"], t0 + l["t"] + max(1.2, l["dur"]), f'{l["who"]}: {l["text"]}'))
        elif part == "outro":
            chapters.append((stamp(t0, False), "Credits"))
    with open(os.path.join(folder, "episode.srt"), "w") as fh:
        for i, (a_, b_, text) in enumerate(cues, 1):
            fh.write(f"{i}\n{stamp(a_)} --> {stamp(b_)}\n{text}\n\n")
    meta = {"title": ep["title"], "number": ep["number"], "date": ep["date"], "chapters": chapters,
            "scenes": [{"title": sc.get("title"), "cast": [c["name"] for c in sc["cast"]], "setting": sc["setting"],
                        "headline": sc["news"]["title"], "source": CHANNEL_NAMES.get(sc["news"].get("channel"), sc["news"].get("channel")),
                        "link": sc["news"].get("link"),
                        "tv": next((p.get("program", {}).get("cmd") for p in sc["props"] if p.get("program")), None),
                        "lines": [{"who": b["who"], "text": b["text"], "push": b.get("persona")} for b in sc["beats"] if b["do"] == "say"]}
                       for sc in scenes]}
    json.dump(meta, open(os.path.join(folder, "episode_meta.json"), "w"), indent=1, ensure_ascii=False)


# ---------- the episode ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--title", default="The Doodle Desk")
    ap.add_argument("--number", type=int, default=1)
    ap.add_argument("--date", default=dt.date.today().strftime("%A, %-d %B %Y"))
    a = ap.parse_args()

    folder = os.path.abspath(a.folder)
    scenes = sorted(glob.glob(os.path.join(folder, "scene*.json")), key=lambda p: int(re.findall(r"\d+", os.path.basename(p))[0]))
    jingle = os.path.join(folder, "jingle.wav")
    if not os.path.exists(jingle):
        jingle = os.path.join(os.path.dirname(folder), "jingle.wav")
    build = os.path.join(folder, "build")
    os.makedirs(build, exist_ok=True)

    cast, sources, model, loaded = [], [], "Qwen3.5-4B", []
    for i, path in enumerate(scenes, 1):
        sc = json.load(open(path))
        tv = os.path.join(folder, f"tv{i}.json")
        if os.path.exists(tv):              # this scene's TV runs a hedwigai program
            prog = json.load(open(tv))
            if not any(p["kind"] == "tv" for p in sc["props"]):
                for p in sc["props"]:
                    if p["kind"] == "newsstand":
                        p["kind"] = "tv"
                        break
            for p in sc["props"]:
                if p["kind"] == "tv":
                    p["program"] = prog
            json.dump(sc, open(path, "w"), indent=1, ensure_ascii=False)
        if any(p["kind"] == "sign" for p in sc["props"]):   # room for the TV, the sign and two people
            for p in sc["props"]:
                p["x"] = {"tv": .4, "newsstand": .4, "sign": .78}.get(p["kind"], p["x"])
            for c, x in zip(sc["cast"], (.08, .93)):
                c["x"] = x
            json.dump(sc, open(path, "w"), indent=1, ensure_ascii=False)
        loaded.append(sc)
        model = sc.get("model", model)
        for c in sc["cast"]:
            if c["name"] not in [x["name"] for x in cast]:
                cast.append({k: c[k] for k in ("name", "role", "sex") if k in c})
        src = CHANNEL_NAMES.get(sc["news"].get("channel"), sc["news"].get("channel"))
        if src not in sources:
            sources.append(src)
    ep = {"title": a.title, "number": a.number, "date": a.date, "cast": cast, "sources": sources, "model": model}

    segments = [render_card(os.path.join(build, "intro"), "intro", 4.5, ep, jingle)]
    for i, (path, sc) in enumerate(zip(scenes, loaded), 1):
        segments.append(render_card(os.path.join(build, f"card{i}"), "scene", 2.4, ep, jingle, sc, i, music_from=3.6))
        out = os.path.join(build, f"scene{i}")
        run([sys.executable, os.path.join(HERE, "anim.py"), path, "--out", out, "--render", "--voice"])
        segments.append(os.path.join(out, "scene.mp4"))
    segments.append(render_card(os.path.join(build, "outro"), "outro", 6.0, ep, jingle))

    # join: same picture size and rate everywhere; audio resampled to 48 kHz stereo; short fades
    ins, chains, starts, clock = [], [], [], 0.0
    for k, seg in enumerate(segments):
        ins += ["-i", seg]
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", seg],
                                   capture_output=True, text=True).stdout.strip())
        starts.append((seg, clock, dur))
        clock += dur
        chains.append(f"[{k}:v]fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.25,fade=t=out:st={dur - .25:.2f}:d=0.25[v{k}];"
                      f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{dur:.3f}[a{k}]")
    joined = "".join(f"[v{k}][a{k}]" for k in range(len(segments)))
    filt = ";".join(chains) + f";{joined}concat=n={len(segments)}:v=1:a=1[v][a]"
    write_captions_and_chapters(folder, starts, loaded, ep)
    final = os.path.join(folder, "episode.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", filt, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-c:a", "aac", "-b:a", "160k", final])
    print(final)


if __name__ == "__main__":
    main()
