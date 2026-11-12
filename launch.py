#!/usr/bin/env python3
"""The posting package for an episode: YouTube, X, Bluesky and Reddit copy, from episode_meta.json.

    python launch.py episodes/ep1/release

Reads episode_meta.json (episode.py) and writes launch.md next to it. The research behind the
choices (2026-11-12): on YouTube "ai cartoon" is searched twice as much as "ai animation", and
"ai characters talking to each other" / "ai characters react to" / "qwen3 tts" autocomplete;
interpretability terms barely register there, so they go in the description, not the title. On X,
local-model posts that name a Qwen model, a capability and the memory it needs travel furthest
(500-700K views for LM Studio's); r/LocalLLaMA and r/LocalLLM are where those builders talk.
"""
import json
import os
import sys

BLOG = "https://hedwigai.com/blog/qwen-personality-neurons"
CODE = "https://github.com/un-seen/doodle-desk"
SITE = "https://hedwigai.com"
# US Google searches a month (keywords volume, 2026-11-12): ai news 90.5K, qwen 74K, local llm 40.5K
# (competition 3/100), ai characters 33.1K (4/100), ai news today 12.1K, qwen 3.5 9.9K, local ai 9.9K,
# mlx 6.6K, qwen3 tts 3.6K, mechanistic interpretability 2.9K, ai cartoon 2.9K, cartoon news 1.3K.
TAGS = ["ai characters", "ai news", "qwen", "local llm", "qwen 3.5", "ai news today", "local ai",
        "qwen3 tts", "mlx", "mechanistic interpretability", "ai cartoon", "cartoon news", "qwen tts",
        "ai characters talking", "ai characters talking to each other", "mac mini ai", "run llm locally",
        "text to speech", "ai comedy", "ai generated cartoon", "activation steering", "persona vectors",
        "steering vectors", "llm personality", "doodle animation"]


def fit_list(head, items, limit):
    """head + one bullet per item, each item trimmed just enough for the whole post to fit."""
    for cut in range(80, 10, -2):
        trim = lambda i: i if len(i) <= cut else i[:cut].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"
        text = head + "\n" + "\n".join("• " + trim(i) for i in items)
        if len(text) <= limit:
            return text
    return text


def short_chapter(title):
    """'Reef Patrol: Chief Ember & Granny Pip on Famed ship…' -> 'Reef Patrol: Famed ship…' (≤ 70 chars)."""
    if ": " in title and " on " in title:
        head, rest = title.split(": ", 1)
        rest = rest.split(" on ", 1)[1]
        title = f"{head}: {rest}"
    return title if len(title) <= 70 else title[:67].rstrip() + "…"


def main():
    rel = sys.argv[1]
    m = json.load(open(os.path.join(rel, "episode_meta.json")))
    n, date = m["number"], m["date"]
    cast = []
    for sc in m["scenes"]:
        cast += [c for c in sc["cast"] if c not in cast]
    import tomllib
    cfg = tomllib.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cast.toml"), "rb"))
    cast_voice = {c["name"]: c.get("voice") for c in cfg.get("character", [])}
    best = max((l for sc in m["scenes"] for l in sc["lines"] if "—" not in l["text"]), key=lambda l: len(l["text"]))
    best_push = best.get("push") or cast_voice.get(best["who"]) or "no"

    chapters = "\n".join(f"{t} {short_chapter(c)}" for t, c in m["chapters"])
    sources = "\n".join(f"- {sc['source']}: {sc['headline']}\n  {sc['link']}" for sc in m["scenes"])
    stories = "; ".join(sc["headline"].rstrip(".") for sc in m["scenes"])

    yt_desc = f"""{len(cast)} AI cartoon characters watch real headlines from {date} on a TV and react. Each character sees the scene: we render the frame, cut out its own pixels, and Qwen writes its next line from that picture. Each one has a personality from a single pushed neuron inside the model, not from a prompt. The voices come from Qwen3-TTS, and all of it runs locally on an 8 GB Mac mini.

Chapters
{chapters}

How does each character know the news?
Each one follows real news channels (RSS feeds). The TV in each scene shows the headline exactly as published, and its chart is live search interest from the hedwigai shell's `trends` program, whose command you can see on screen.

Where does mechanistic interpretability come in?
Each personality is a single MLP neuron found by mechanistic interpretability work on Qwen3.5-4B, pushed on every token the character speaks. Nothing is fine-tuned and nothing is prompted.

How does a character "see" the scene?
Before every line we draw the scene as it looks at that moment and remove the pixel columns where that character stands. Qwen3.5-4B, a vision-language model running 4-bit on the Mac mini, reads that picture (the TV, the sign, the other character, what was just said) and writes the line.

Where does the personality come from?
It comes from a neuron. Each character has one neuron in Qwen3.5-4B that is pushed while it speaks: suspicious, wistful, flattering, curt and so on. The push can change from line to line, so the face changes with it while the body stays the same.
The neurons are explained here: {BLOG}

What runs where?
An M1 Mac mini with 8 GB runs everything: Qwen3.5-4B (4-bit, vision included, 2.9 GB) for the lines, Qwen3-TTS 1.7B (6-bit) for the voices, and a doodle renderer that draws every frame as SVG. A 2-minute episode is written, voiced and rendered in about 10 minutes.

Today's stories
{sources}

The code (Apache 2.0): {CODE}
Made with hedwigai: {SITE}

#AICartoon #AINews #Qwen"""

    titles = ["AI Characters React to Today's News (Local Qwen 3.5, Mac Mini)",
              f"AI Characters Watch the News and Talk About It | Doodle Desk Ep {n}",
              "AI News, Read by AI Characters: Qwen 3.5 + Qwen3 TTS Running Locally"]

    x_main = (f"We gave {len(cast)} AI cartoon characters today's news.\n\n"
              "Each one sees the scene: we cut its own pixels out of the frame, and Qwen3.5-4B writes its line from that picture. "
              "Its personality is one pushed neuron.\n\n"
              "It all runs on an 8 GB Mac mini.")
    x_replies = [
        fit_list(f"Episode {n}, {len(m['scenes'])} scenes, real headlines:", [sc["headline"] for sc in m["scenes"]], 280),
        "The stack, all on the Mac mini:\n• Qwen3.5-4B, 4-bit with vision (2.9 GB): the lines\n• Qwen3-TTS 1.7B: the voices\n"
        "• one neuron pushed per character: the personality\n• SVG doodles, rendered on the CPU",
        f"The code is open: {CODE}\nThe personality neurons: {BLOG}",
    ]
    bsky_main = (f"We gave {len(cast)} AI cartoon characters today's news. Each one sees the scene, minus its own pixels, "
                 "and Qwen writes its line from that picture. Its personality is a single pushed neuron. "
                 "All local on an 8 GB Mac mini.")
    reddit_title = "Qwen3.5-4B (vision) + Qwen3-TTS on an 8 GB M1 Mac mini: cartoon characters that see the scene and react to today's news"
    reddit_body = f"""I built a small pipeline where doodle characters react to real headlines, and all of it runs locally on an M1 Mac mini with 8 GB:

- **Lines**: Qwen3.5-4B, converted with mlx-vlm to 4-bit *with the vision tower* (2.9 GB). Before each line I render the frame, cut out the speaking character's own pixel columns, and give it that picture plus the script so far. It reacts to what is on the TV, the sign and the other character.
- **Personality**: no system prompt. One MLP neuron per character is pushed on every token, using the column of W_down for that neuron, scaled to the layer's median norm. Dose ~0.5 in vision mode; at 0.7 it drifted into emoji and "have fun!".
- **Voices**: Qwen3-TTS 1.7B CustomVoice (6-bit, mlx-audio), about 1.2x real time. The `instruct` line is built from the active push.
- **Picture**: SVG doodles, rasterised with resvg. A 2:30 episode takes about 10 minutes end to end.

What did not work: the 4B planner made up personal details about real people in the news, so headlines that name people are skipped. A "suspicious" character also called a real government report "false", so lines that deny the story are now filtered.

Episode {n}: [video link]. Code (Apache 2.0): {CODE}. The neuron write-up: {BLOG}"""

    alt = [
        "A doodle TV shows the headline 'Famed ship SS United States deliberately sunk off Florida coast to become a reef' with a search-interest chart; a granny character says the ocean now holds its own lighthouse.",
        "Ten pastel doodle characters (a cop, a pirate, a chef, a doctor, an astronaut, a wizard, a firefighter, a granny, a superhero and a ninja) on the title card of 'The Doodle Desk'.",
        "A ninja and a superhero in a city with a TV headline: '93% of paint splatters are valid Perl programs'.",
        "A police officer and a pirate on a beach with the TV headline about forever chemicals falling in England's rivers.",
    ]

    md = f"""# The Doodle Desk, Episode {n}: launch package

## YouTube (@hedwigai-app)
Upload `episode.mp4`, then set:
- **Title** (use YouTube's "Test & compare" with all three):
  1. {titles[0]}
  2. {titles[1]}
  3. {titles[2]}
- **Thumbnail**: `thumbnail.png`
- **Captions**: upload `episode.srt` as English. Don't leave it to auto-captions: uploaded captions are exact, they're indexed for search, and AI answer engines read them.
- **Category**: Science & Technology. **Language**: English. **Made for kids**: no. **Altered or synthetic content**: yes (AI voices and characters).
- **Tags** (first ones weigh most): {", ".join(TAGS)}
- **Description**:

```
{yt_desc}
```

- **Pinned comment**: "Every line was written by Qwen from what that character could see, with its own pixels cut out of the picture. Which character should get the next headline?"

## X (carousel first, video in the reply)
**Post 1**, the 4 images `carousel-1..4.png` with alt text:
```
{x_main}
```
**Reply 1**, the video `episode.mp4`:
```
{x_replies[0]}
```
**Reply 2**:
```
{x_replies[1]}
```
**Reply 3** (the link goes in a reply, not the first post):
```
{x_replies[2]}
```
Tag no one in post 1. Reply 2 is where to tag the people whose tools it uses (mlx-vlm and mlx-audio) and @Alibaba_Qwen, if you want their reach.

## Bluesky (images first, video in the reply)
**Post 1**, 4 images with alt text:
```
{bsky_main}
```
**Reply**, the video, then a reply with the links: {CODE} and {BLOG}

## Reddit
r/LocalLLaMA (flair: Other or Resources); a shorter version fits r/LocalLLM.
**Title**: {reddit_title}
```
{reddit_body}
```

## Alt text for the images
""" + "\n".join(f"{i + 1}. {a}" for i, a in enumerate(alt)) + f"""

## The line to quote when someone asks what it is
"{best['text']}" ({best['who']}, {best_push} push)
"""
    for name, text, limit in [("x post 1", x_main, 280), *[(f"x reply {i + 1}", r, 280) for i, r in enumerate(x_replies)],
                              ("bluesky post 1", bsky_main, 300), ("youtube title", titles[0], 100)]:
        print(f"{name}: {len(text)}/{limit}" + ("  TOO LONG" if len(text) > limit else ""))
    open(os.path.join(rel, "launch.md"), "w").write(md)
    print(os.path.join(rel, "launch.md"))


if __name__ == "__main__":
    main()
