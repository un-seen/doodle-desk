#!/usr/bin/env python3
"""Scene seed + live headlines + persona voices -> a doodle scene JSON for anim.py.

    python scene_writer.py --seed 7 --out scenes/seed7.json
    python scene_writer.py --cast "Officer Bolt,Captain Mira" --setting beach --out scenes/a.json

1. The seed (or --cast/--setting) picks two characters from cast.toml and a setting.
2. news.py fetches the latest headlines from each character's channels.
3. Plan, unpushed: Qwen picks one headline, places props (the TV or newsstand shows that
   headline word for word), and writes the beats with draft lines that name things on screen.
4. Voice, pushed: every line is rewritten as a script continuation with the speaker's
   persona neuron pushed on every token (voices.py), so personality comes from the push,
   not from the prompt. The draft is kept next to each line.
"""
import argparse
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import anim  # noqa: E402
import news  # noqa: E402

ACTIONS = ["walk_to", "run_to", "jump", "wave", "point", "cheer", "shrug", "dance", "surprised", "laugh", "say"]
NEWS_PROPS = ["tv", "newsstand"]
LOOKS = {
    "cop": "a police officer in a navy uniform, peaked cap and aviator sunglasses",
    "hero": "a superhero in a glass space helmet and a cape",
    "chef": "a chef in a white coat and a tall chef's hat",
    "pirate": "a pirate with a red bandana, an eyepatch and a striped shirt",
    "wizard": "a wizard in a pointed purple hat and a starry robe",
    "doctor": "a doctor in a white coat with a stethoscope and a head mirror",
    "firefighter": "a firefighter in a red helmet and a yellow coat with reflective stripes",
    "ninja": "a ninja in a black hood with only the eyes showing and a red sash",
    "royal": "a monarch with a gold crown, a robe with white fur trim and a gold chain",
    "astronaut": "an astronaut in a white spacesuit with a glass helmet and a backpack",
    "detective": "a detective in a deerstalker hat and a trench coat, with a pipe",
    "none": "an ordinary doodle person",
}
ALIASES = {"tv": ["tv", "television", "screen", "telly", "news"], "newsstand": ["newsstand", "kiosk", "paper", "news"],
           "palm tree": ["palm"], "coconuts": ["coconut"], "clouds": ["cloud"], "buildings": ["building"],
           "windows": ["window"], "stars": ["star"], "sign": ["sign"], "bench": ["bench"], "lamp": ["lamp"]}


def look(c):
    base = LOOKS.get(c["role"], LOOKS["none"])
    if c["role"] == "wizard":
        base += " with a long white beard" if c["sex"] == "male" else " with long hair"
    if c["role"] == "chef" and c["sex"] == "male":
        base += " and a curly mustache"
    return f'{base} ({c["sex"]})'


def mentions(text, name):
    t = text.lower()
    return any(re.search(r"\b" + re.escape(w), t) for w in [name] + ALIASES.get(name, []))


# ---------- step 1-2: cast, setting, headlines ----------

def pick(cfg, seed, cast_names, setting):
    r = random.Random(seed)
    chars = cfg["character"]
    if cast_names:
        by = {c["name"]: c for c in chars}
        cast = [by[n.strip()] for n in cast_names.split(",")]
    else:
        cast = r.sample(chars, 2)
    return [dict(c) for c in cast], setting or r.choice(list(anim.SET_PIECES))


def gather(cfg, cast, exclude=()):
    pool, seen = [], set(exclude)
    for c in cast:
        for ch, items in news.headlines(c.get("channels", []), cfg).items():
            for it in items[:3]:
                if it["title"] in seen:
                    continue
                seen.add(it["title"])
                if cfg.get("settings", {}).get("skip_named_people", True) and news.names_a_person(it["summary"]):
                    it = it | {"summary": ""}          # the summary names someone: keep the headline only
                pool.append(it | {"reader": c["name"]})
    return pool


# ---------- step 3: plan ----------

def plan_prompt(cast, setting, pool):
    heads = "\n".join(f'{i + 1}. [{it["channel"]}, read by {it["reader"]}] {it["title"]}'
                      + (f' -- {it["summary"][:140]}' if it["summary"] else "") for i, it in enumerate(pool))
    things = ", ".join(anim.SET_PIECES[setting])
    example = {
        "title": "Reef Patrol", "news": 2,
        "props": [{"kind": "tv", "x": 0.5}, {"kind": "sign", "x": 0.3, "text": "No diving"}],
        "beats": [
            {"t": 0.4, "who": "A", "do": "walk_to", "to": "tv"},
            {"t": 0.8, "who": "B", "do": "say", "text": "The TV says a whole ship sank on purpose!"},
            {"t": 3.2, "who": "A", "do": "point", "to": "sea"},
            {"t": 3.4, "who": "A", "do": "say", "text": "Then why is that sign saying no diving?"},
            {"t": 6.0, "who": "B", "do": "surprised"},
            {"t": 6.2, "who": "B", "do": "say", "text": "Because the fish own it now."},
            {"t": 8.6, "who": "A", "do": "laugh"}]}
    return (
        "You plan tiny cartoon scenes built on a real news headline. Answer with JSON only.\n\n"
        f"Setting: {anim.SET_TEXT[setting]}.\n"
        f"Things on screen anyone can name, point at or walk to: {things}.\n"
        f"Props you may add (x from 0.25 to 0.75): tv (shows the chosen headline), newsstand (shows the "
        f"chosen headline), sign (a short text you write, at most 4 words), bench, lamp.\n\n"
        "Characters:\n" + "\n".join(f'- {c["name"]}: {look(c)}' for c in cast) +
        f"\n\nToday's headlines:\n{heads}\n\n"
        "Rules:\n"
        "- Pick ONE headline (\"news\": its number). The scene is about it; the characters react to it in the "
        "setting. Put a tv or a newsstand in the props so the headline is on screen.\n"
        "- Every line reacts to a specific fact in the chosen headline: say the number, the place or the thing "
        "it reports, and what the character thinks of it. Small talk that ignores the story is not allowed.\n"
        "- At least one line names something on screen (the tv, the sign, the sea, the sun...).\n"
        f"- Each beat: t (seconds), who (a character name), do (one of {', '.join(ACTIONS)}). "
        "walk_to, run_to, point and wave take \"to\": a character or a thing on screen.\n"
        "- The people in the headline are real: never invent facts, motives or private lives for them. "
        "The jokes come from the two characters, their outfits, the setting and the props.\n"
        "- say takes \"text\": one line, at most 12 words. 9 to 14 beats, about 14 to 20 seconds, "
        "about 3 seconds between lines, the last line lands a joke.\n\n"
        "Example (A and B stand for the names):\n" + json.dumps(example) + "\n\nNow write the scene as JSON."
    )


def validate_plan(raw, cast, setting, pool):
    names = [c["name"] for c in cast]
    try:
        k = int(raw.get("news", 1)) - 1
    except (TypeError, ValueError):
        k = 0
    item = pool[k if 0 <= k < len(pool) else 0]

    props = []
    for p in raw.get("props", [])[:3]:
        kind = str(p.get("kind", "")).lower()
        if kind not in anim.PROP_KINDS or any(q["kind"] == kind for q in props):
            continue
        q = {"kind": kind, "x": round(min(.75, max(.25, float(p.get("x", .5)))), 2)}
        if kind in NEWS_PROPS:
            q["text"] = item["title"]                       # word for word, never the model's paraphrase
        elif kind == "sign":
            q["text"] = " ".join(str(p.get("text", "")).split()[:4]) or "Keep calm"
        props.append(q)
    if not any(p["kind"] in NEWS_PROPS for p in props):
        props.insert(0, {"kind": "tv", "x": .5, "text": item["title"]})
    news_x = next(p["x"] for p in props if p["kind"] in NEWS_PROPS)
    for p in props:                                          # keep props apart
        if p["kind"] not in NEWS_PROPS and abs(p["x"] - news_x) < .3:
            p["x"] = round(news_x - .3 if news_x > .5 else news_x + .3, 2)

    things = set(anim.SET_PIECES[setting]) | {p["kind"] for p in props}
    beats = []
    for b in raw.get("beats", []):
        if b.get("who") not in names or b.get("do") not in ACTIONS:
            continue
        nb = {"t": round(min(25, max(0, float(b.get("t", 0)))), 2), "who": b["who"], "do": b["do"]}
        to = b.get("to")
        if to in names and to != b["who"] or to in things:
            nb["to"] = to
        if b["do"] == "say":
            text = " ".join(str(b.get("text", "")).split()[:14])
            if not text:
                continue
            nb["text"] = text
        if b["do"] in ("walk_to", "run_to") and "to" not in nb:
            nb["to"] = [n for n in names if n != b["who"]][0]
        beats.append(nb)
    beats.sort(key=lambda b: b["t"])
    says = [b for b in beats if b["do"] == "say"]
    if len(says) < 3 or len(beats) < 6:
        raise ValueError(f"too few usable beats ({len(beats)}, {len(says)} lines)")
    facts = content_words(item["title"] + " " + item.get("summary", ""))
    on_news = sum(bool(content_words(b["text"]) & facts) for b in says)
    if on_news < max(2, (len(says) + 1) // 2):
        raise ValueError(f"only {on_news} of {len(says)} lines touch the headline")
    news_kind_ = next((p["kind"] for p in props if p["kind"] in NEWS_PROPS), "tv")
    if not any(b["do"] in ("point", "walk_to") and b.get("to") == news_kind_ for b in beats):
        first = says[0]                      # the first speaker points at the news as they speak
        beats.append({"t": first["t"], "who": first["who"], "do": "point", "to": news_kind_})
        other = [n for n in names if n != first["who"]][0]
        if not any(b["who"] == other and b["do"] in ("surprised", "shrug", "laugh") for b in beats):
            beats.append({"t": round(first["t"] + 1.2, 2), "who": other, "do": "surprised"})
        beats.sort(key=lambda b: b["t"])
        says = [b for b in beats if b["do"] == "say"]
    # Ground the lines in what is on screen: a line that names nothing gets something to talk
    # about (the news prop first, then what a character last walked to or pointed at).
    news_kind = next(p["kind"] for p in props if p["kind"] in NEWS_PROPS)
    grounded = sum(any(mentions(b["text"], th) for th in things) for b in says)
    r = random.Random(len(beats))
    last_thing = None
    for b in beats:
        if b.get("to") in things:
            last_thing = b["to"]
        if b["do"] != "say" or grounded >= 2 or any(mentions(b["text"], th) for th in things):
            continue
        b["about"] = news_kind if not any(x.get("about") == news_kind for x in says) \
            else (last_thing if last_thing and last_thing != news_kind else r.choice(sorted(anim.SET_PIECES[setting])))
        grounded += 1
    for c, x in zip(cast, (.12, .88)):
        c["x"] = x
    return {"title": str(raw.get("title", ""))[:40], "setting": setting, "news": item,
            "cast": [{k: c[k] for k in ("name", "role", "sex", "x", "voice", "dose", "speech") if k in c} for c in cast],
            "props": props, "beats": sorted(beats, key=lambda b: b["t"])}


# ---------- step 4: voices ----------

def voice_prompt(scene, cast, b, script):
    me = next(c for c in cast if c["name"] == b["who"])
    others = [c for c in cast if c is not me]
    things = ", ".join(list(anim.SET_PIECES[scene["setting"]]) + [p["kind"] for p in scene["props"]])
    shown = "; ".join(f'the {p["kind"]} shows "{p["text"]}"' for p in scene["props"] if p.get("text"))
    lines = "\n".join(f"{w.upper()}: {t}" for w, t in script)
    reads = "; ".join(h["title"] for h in me.get("_reads", [])[:2])
    return (f"CARTOON SCRIPT. {anim.SET_TEXT[scene['setting']].capitalize()}. On screen: {things}. {shown}.\n"
            f"{me['name'].upper()} is {look(me)}" + (f", who has been reading: {reads}" if reads else "") + ".\n"
            + "".join(f"{o['name'].upper()} is {look(o)}.\n" for o in others)
            + f"Today's story: {scene['news']['title']}\n"
            "(The characters react to the story; they never add facts about the real people in it.)\n\n"
            f"{lines}\n"
            f"(Next, {me['name']} says"
            + (f", about the {b['about']} right there" if b.get("about") else "")
            + f", reacting to the story in their own words, roughly: {b['text']})\n"
            f'{me["name"].upper()}:' + (" " + opener(b) if opener(b) else ""))


def see_prompt(scene, cast, b, script):
    """The words that go with the picture: who you are, the script so far, what you mean to say."""
    me = next(c for c in cast if c["name"] == b["who"])
    others = [c for c in cast if c is not me]
    lines = "\n".join(f"{w.upper()}: {t}" for w, t in script) or "(nobody has spoken yet)"
    return (f"This picture is what {me['name']} sees right now in a cartoon; {me['name']} is not in it "
            f"(the dark seam is where {me['name']} stands). {me['name']} is {look(me)}. "
            + "".join(f"{o['name']} is {look(o)}. " for o in others)
            + "Read the TV, look at what is around, and react to it.\n\n"
            f"Script so far:\n{lines}\n\n"
            f"Write {me['name']}'s next line only: one sentence, at most 14 words, about what is on the TV or "
            f"in the picture. The moment is about this (use your own words, do not repeat it): {b['text']}")


def opener(b):
    """No forced opener: starting lines with "The TV" made them about the TV, not the news."""
    return ""


def speak(model, tok, prompt, n, seed, start=""):
    import mlx.core as mx
    from mlx_lm import stream_generate
    from mlx_lm.sample_utils import make_sampler
    outs = []
    for k in range(n):
        mx.random.seed(seed + k)
        text = ""
        for r in stream_generate(model, tok, prompt, max_tokens=40, sampler=make_sampler(temp=.8, top_p=.95)):
            text += r.text
            if "\n" in text.lstrip() or "(" in text or "<" in text:
                break
        body = re.split(r"[\n(]|<think>|</?\w+>", text)[0]
        body = re.sub(r"\s+", " ", body.replace('"', "").replace("“", "").replace("”", "")).strip()
        if start:
            body = start + ("" if body[:1] in (",", ".", "!", "?", "'") else " ") + body
        outs.append(body.strip())
    return outs


STOP = {"the", "a", "an", "and", "of", "to", "is", "it", "in", "on", "that", "this", "i", "you", "we", "just"}
COMMON = STOP | {"with", "from", "for", "are", "was", "were", "has", "have", "had", "will", "would", "what", "about",
                 "they", "them", "their", "there", "here", "into", "over", "after", "says", "said", "more", "than",
                 "your", "yours", "mine", "that's", "it's", "this", "these", "those", "just", "like", "very", "much",
                 "news", "story", "today", "look", "well", "really", "maybe", "still", "even", "only", "some",
                 "could", "should", "does", "doing", "going", "make", "made", "know", "think", "right", "want"}


def content_words(text):
    """The words that carry a story: longer than three letters, not function words; plurals folded."""
    out = set()
    for w in re.sub(r"[^a-z0-9 ]", " ", text.lower()).split():
        if (len(w) > 3 or w.isdigit()) and w not in COMMON:
            if w.endswith("ies") and len(w) > 4:
                w = w[:-3] + "y"
            elif w.endswith("s") and not w.endswith("ss") and len(w) > 4:
                w = w[:-1]
            out.add(w)
    return out


def copies_prompt(c, avoid_text):
    """True when the line lifts four words in a row from the character descriptions."""
    w = re.sub(r"[^a-z ]", " ", c.lower()).split()
    src = " " + " ".join(re.sub(r"[^a-z ]", " ", avoid_text.lower()).split()) + " "
    return any(" " + " ".join(w[i:i + 4]) + " " in src for i in range(len(w) - 3))


def loops(c):
    """True when a content word comes three or more times (a push stuck on a word)."""
    w = [x for x in re.sub(r"[^a-z ]", " ", c.lower()).split() if x not in STOP]
    return any(w.count(x) >= 3 for x in set(w))


# A character may doubt or joke, but never tell viewers that a real story is false: captions are
# indexed and clips travel without their context.
DENIES = re.compile(r"\b(false|fake|lie|lies|lying|liar|hoax|made[- ]up|not true|untrue|never (happened|drop|fell|rose|did))\b", re.I)


def parrots(c, sources, n=5):
    """True when the line repeats n words in a row from the headline or an earlier line."""
    w = re.sub(r"[^a-z0-9 ]", " ", c.lower()).split()
    srcs = [" " + " ".join(re.sub(r"[^a-z0-9 ]", " ", x.lower()).split()) + " " for x in sources]
    return any(" " + " ".join(w[i:i + n]) + " " in src for i in range(len(w) - n + 1) for src in srcs)


def choose(cands, draft, things, about=None, said=(), avoid_text="", news_title=""):
    """Keep a line that is a line: not empty, not too long, not said before, not stuck, not lifted
    from the descriptions, naming what the draft named."""
    need = [th for th in things if mentions(draft, th)] + ([about] if about else [])
    norm = lambda x: re.sub(r"\W+", " ", x.lower()).strip()
    old = {norm(x) for x in said}
    ok = [c for c in cands if 3 <= len(c.split()) <= 16 and norm(c) not in old
          and not loops(c) and not copies_prompt(c, avoid_text) and not parrots(c, [news_title, *said])
          and "[" not in c and not re.search(r"[\U0001F000-\U0001FFFF\u2600-\u27BF]", c)
          and not DENIES.search(c)]
    fresh = [c for c in ok if not parrots(c, [draft])]   # prefer lines that are not the plan word for word
    ok = fresh or ok
    named = [c for c in ok if all(mentions(c, th) for th in need)]
    pool = named or ok or [draft]
    facts = content_words(draft) | content_words(news_title)
    score = lambda c: (len(content_words(c) & facts), c.rstrip()[-1:] in ".!?", -len(c.split()))
    best = max(pool, key=score)
    if not content_words(best) & facts and content_words(draft) & content_words(news_title):
        return draft                         # every candidate drifted off the story: keep the draft
    return best


def retime(beats):
    """Give each line its reading time: push later beats back when a longer line needs it."""
    shift, free = 0.0, 0.0
    for b in beats:
        b["t"] = round(b["t"] + shift, 2)
        if b["do"] == "say":
            if b["t"] < free:
                shift += free - b["t"]
                b["t"] = round(free, 2)
            free = b["t"] + max(1.8, len(b["text"].split()) / anim.READ_WPS + 1.0) - .3
    return beats


def revoice(a, cfg):
    """Rewrite the lines of an existing scene from their drafts, same plan, same timing."""
    import mlx.core as mx
    from mlx_lm import load
    scene = json.load(open(a.revoice))
    by = {c["name"]: c for c in cfg["character"]}
    cast = [dict(by.get(c["name"], {}), **c) for c in scene["cast"]]
    for c in cast:
        c["_reads"] = []
        c.setdefault("voice", None)
        c.setdefault("dose", 1.0)
    for b in scene["beats"]:
        if b["do"] == "say" and b.get("draft"):
            b["text"] = b["draft"]
    things = list(anim.SET_PIECES[scene["setting"]]) + [p["kind"] for p in scene["props"]]
    script = []
    if a.see:
        from views import Seer, view
        seer = Seer(os.path.expanduser(a.vision_model), cfg.get("voices", {}))
        voices = seer.voices
        view_dir = os.path.splitext(os.path.abspath(a.out))[0] + "_views"
        os.makedirs(view_dir, exist_ok=True)
    else:
        from voices import Voices
        model, tok = load(a.model)
        voices = Voices(model, cfg.get("voices", {}))
    looks = " ".join(look(c) for c in cast)
    for i, b in enumerate(scene["beats"]):
        if b["do"] != "say":
            continue
        me = next(c for c in cast if c["name"] == b["who"])
        voices.set(me.get("voice"), float(me.get("dose", 1.0)) * (a.see_dose if a.see else 1.0))
        if a.see:
            img, cols = view(scene, b["t"], b["who"], os.path.join(view_dir, f"line{i:02d}.png"))
            b["view"], b["view_cut"] = os.path.relpath(img, os.path.dirname(os.path.abspath(a.out))), cols
            cands = seer.say(img, see_prompt(scene, cast, b, script), b["who"], a.candidates, a.seed * 1000 + i * 10)
        else:
            cands = speak(model, tok, voice_prompt(scene, cast, b, script), a.candidates, a.seed * 1000 + i * 10)
        draft = b["text"]
        b["text"] = choose(cands, draft, things, None, [t for _, t in script], looks, scene["news"]["title"])
        b["draft"] = draft
        b["candidates"] = cands
        b["persona"] = me.get("voice")          # the push this line was said under (the face shows it)
        script.append((b["who"], b["text"]))
        print(f'  {b["who"]} [{me.get("voice")}]: {b["text"]}   (draft: {draft})', file=sys.stderr)
    voices.clear()
    scene["beats"] = retime(scene["beats"])
    json.dump(scene, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(a.out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cast", default="", help='two names from cast.toml, "A,B"')
    ap.add_argument("--setting", default="", choices=[""] + list(anim.SET_PIECES))
    ap.add_argument("--config", default=os.path.join(HERE, "cast.toml"))
    ap.add_argument("--model", default=os.path.expanduser("~/models/qwen35-4b-4bit"))
    ap.add_argument("--candidates", type=int, default=6)
    ap.add_argument("--revoice", default="", help="a scene JSON: keep its plan, write its lines again (from the drafts)")
    ap.add_argument("--see", action="store_true", help="each line is written by the vision model from the speaker's view")
    ap.add_argument("--vision-model", default="~/models/qwen35-4b-vlm-4bit")
    ap.add_argument("--see-dose", type=float, default=0.7, help="pushes in --see mode run at this fraction of the dose")
    ap.add_argument("--exclude", default="", help="JSON file: a list of headline titles not to use (earlier scenes)")
    ap.add_argument("--model-name", default="Qwen3.5-4B", help="shown on the character pills")
    ap.add_argument("--tv", default="", help='JSON file {"cmd", "series", "label"}: a hedwigai program the TV runs')
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import mlx.core as mx
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler
    from voices import Voices

    cfg = news.load_config(a.config)
    if a.revoice:
        return revoice(a, cfg)
    cast, setting = pick(cfg, a.seed, a.cast, a.setting)
    exclude = json.load(open(a.exclude)) if a.exclude and os.path.exists(a.exclude) else []
    pool = gather(cfg, cast, exclude)
    if not pool:
        raise SystemExit("no usable headlines on these characters' channels")
    for c in cast:
        c["_reads"] = [it for it in pool if it["reader"] == c["name"]]
        c.setdefault("voice", None)
        c.setdefault("dose", 1.0)
    print(f"cast: {[c['name'] for c in cast]}, setting: {setting}, {len(pool)} headlines", file=sys.stderr)

    model, tok = load(a.model)
    voices = Voices(model, cfg.get("voices", {}))

    # plan, unpushed
    voices.clear()
    text = tok.apply_chat_template([{"role": "user", "content": plan_prompt(cast, setting, pool)}],
                                   add_generation_prompt=True, tokenize=False, enable_thinking=False)
    scene, last = None, None
    for k in range(5):
        mx.random.seed(a.seed * 101 + k)
        out = generate(model, tok, prompt=text, max_tokens=1500, sampler=make_sampler(temp=.8, top_p=.95))
        m = re.search(r"\{.*\}", out, re.S)
        try:
            scene = validate_plan(json.loads(m.group(0)), cast, setting, pool)
            break
        except Exception as e:
            last = e
            print(f"plan try {k + 1}: {e}", file=sys.stderr)
    if scene is None:
        raise SystemExit(f"no valid plan: {last}")
    print(f"headline: {scene['news']['title']}", file=sys.stderr)

    # voices, pushed per speaker
    things = list(anim.SET_PIECES[setting]) + [p["kind"] for p in scene["props"]]
    script = []
    seer = None
    if a.see:                                 # each character speaks from what it sees
        import gc
        from views import Seer, view
        voices.clear()
        del model, tok
        gc.collect()
        mx.clear_cache()
        seer = Seer(os.path.expanduser(a.vision_model), cfg.get("voices", {}))
        voices = seer.voices
        view_dir = os.path.splitext(os.path.abspath(a.out))[0] + "_views"
        os.makedirs(view_dir, exist_ok=True)
    for i, b in enumerate(scene["beats"]):
        if b["do"] != "say":
            continue
        me = next(c for c in cast if c["name"] == b["who"])
        voices.set(me.get("voice"), float(me.get("dose", 1.0)))
        if seer:
            img, cols = view(scene, b["t"], b["who"], os.path.join(view_dir, f"line{i:02d}.png"))
            b["view"], b["view_cut"] = os.path.relpath(img, os.path.dirname(os.path.abspath(a.out))), cols
            cands = seer.say(img, see_prompt(scene, cast, b, script), b["who"], a.candidates, a.seed * 1000 + i * 10)
        else:
            cands = speak(model, tok, voice_prompt(scene, cast, b, script), a.candidates, a.seed * 1000 + i * 10,
                          start=opener(b))
        looks = " ".join(look(c) for c in cast)
        b["draft"], b["text"] = b["text"], choose(cands, b["text"], things, None, [t for _, t in script], looks,
                                                  scene["news"]["title"])
        b["voice"] = f'{me.get("voice")} @ {me.get("dose")}'
        b["persona"] = me.get("voice")
        script.append((b["who"], b["text"]))
        print(f'  {b["who"]} [{b["voice"]}]: {b["text"]}   (draft: {b["draft"]})', file=sys.stderr)
    voices.clear()
    scene["beats"] = retime(scene["beats"])
    scene["model"] = a.model_name
    for c in scene["cast"]:                   # the push behind the personality, for the pill
        if c.get("voice"):
            L, n, sign = voices.parse(c["voice"])
            c["neuron"] = f"L{L}N{n}{'+' if sign > 0 else '-'}"
    if a.tv:
        prog = json.load(open(a.tv))
        for p in scene["props"]:
            if p["kind"] == "tv":
                p["program"] = prog

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(scene, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(a.out)


if __name__ == "__main__":
    main()
