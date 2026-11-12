# Doodle Desk

Doodle Desk makes cartoon episodes about today's news. Doodle characters stand in a scene, read a real headline on a TV and talk about it. Every part runs on one Apple silicon Mac. We made it on an M1 Mac mini with 8 GB of memory.

Episode 1: "AI Characters React to Today's News" on the hedwigai YouTube channel ([@hedwigai-app](https://www.youtube.com/@hedwigai-app)).

## What makes it different

- **The characters see the scene.** Before each line, the scene is drawn as it looks at that moment. The speaker's own pixel columns are cut out of the picture. Qwen3.5-4B, a vision-language model, reads that picture and writes the line. A character reacts to the TV, the sign and the other character, but never sees itself.
- **A neuron gives each character its personality.** No system prompt sets a personality. One MLP neuron of Qwen3.5-4B is pushed on every token the character says. The neurons and the push are explained in [Qwen3.5-4B's evil neuron, checked: 12 more found](https://hedwigai.com/blog/qwen-personality-neurons).
- **The push shows on the face, not the body.** A character's body (head, hair, colours) comes from its name and never changes. The face (eyes, brows, resting mouth) follows the push of the current line, so a character can move through many pushes and stay recognisable.
- **The news is real.** Each character follows RSS or Atom channels that you choose. The TV shows the chosen headline word for word. Headlines that name a person are skipped by default, so nobody real gets invented details. A line that calls a real story false is rejected.

## How a scene is made

1. `scene_writer.py` picks two characters and a setting. It fetches their channels (`news.py`) and asks Qwen3.5-4B, unpushed, for a plan: the headline, the props and the beats.
2. Each line is then written again with the speaker's neuron pushed (`voices.py`). With `--see`, it is written by the vision model from the speaker's own view (`views.py`).
3. `anim.py` turns the scene into frames. It draws SVG doodles (`doodle.py`), rasterises them with resvg and encodes an MP4 with ffmpeg. With `--tts`, every line is spoken by Qwen3-TTS (`tts_server.py`), and the mouths move with the sound.
4. `episode.py` joins several scenes with title cards, a jingle, captions (`.srt`) and chapters. `launch.py` writes the posting copy for YouTube, X, Bluesky and Reddit.

## Setup

You need an Apple silicon Mac, Python 3.12, ffmpeg and about 6 GB of free memory.

```bash
python3.12 -m venv ~/doodle-env
~/doodle-env/bin/pip install mlx-lm mlx-vlm mlx-audio resvg-py soundfile pillow numpy
brew install ffmpeg
```

Convert Qwen3.5-4B twice, once for text and once with its vision tower:

```bash
~/doodle-env/bin/mlx_lm.convert --hf-path Qwen/Qwen3.5-4B --mlx-path ~/models/qwen35-4b-4bit -q --q-bits 4
~/doodle-env/bin/python -m mlx_vlm.convert --hf-path Qwen/Qwen3.5-4B --mlx-path ~/models/qwen35-4b-vlm-4bit -q --q-bits 4
```

Start the voice worker. It downloads Qwen3-TTS 1.7B CustomVoice (6-bit) on the first run:

```bash
~/doodle-env/bin/python tts_server.py   # listens on 127.0.0.1:8091
```

## Make a scene

```bash
~/doodle-env/bin/python scene_writer.py --cast "King Toast,Inspector Hume" --setting night --see --out scenes/s1.json
~/doodle-env/bin/python anim.py scenes/s1.json --out build/s1 --render --tts http://127.0.0.1:8091
```

The video is `build/s1/scene.mp4`. Without `--tts`, the scene is silent and the speech stays in bubbles.

## Make an episode

```bash
./episode_write.sh ep2 "Officer Bolt,Captain Mira:beach" "Chef Basil,Dr. Ada:city"
~/doodle-env/bin/python episode.py episodes/ep2 --title "The Doodle Desk" --number 2
~/doodle-env/bin/python launch.py episodes/ep2
```

`episode.py` reads `jingle.wav` from the episode folder or from `episodes/`. A TV can show a chart from any program you run. Put `{"cmd": "...", "series": [...], "label": "..."}` in `episodes/<ep>/tvN.json` for scene N. In Episode 1 the charts are Google Trends series from the hedwigai shell's `trends` program.

`episode.py` calls `anim.py` with `--voice`, which expects a sound server that offers `/api/voice`. To use the TTS worker directly, change that call to `--tts http://127.0.0.1:8091`.

## Configure the cast

Everything about the cast lives in `cast.toml`.

- **Channels:** any RSS or Atom feed, under a short name.
- **Characters:** a name, a role (cop, hero, chef, pirate, wizard, doctor, firefighter, ninja, royal, astronaut, detective or none), a sex, the channels they follow, a voice (a neuron) and a dose.
- **Voices:** 13 named neurons of Qwen3.5-4B, or any neuron written as `L14N8949+`.
- **Looks:** `look = { hair = "bun", hair_color = "#c9c9cf", head = "egg" }` fixes a character's drawing.
- **Speech:** `speech = { speaker = "eric", instruct = "Speak slowly." }` overrides the Qwen3-TTS speaker and delivery.
- **Settings:** a list of words that keep a headline out of the scenes, a minimum headline length, and `skip_named_people`.

A dose of about 0.7 gives a clear voice in the text model. In `--see` mode the push runs at 0.7 times the dose, because the vision model drifts sooner.

## The pill on the characters

Each character carries a pill with its name, the model and the push. Put a 96 × 96 PNG at `assets/qwen.png` to show a model logo in it. The repository does not include one.

## Files

| File | What it does |
|---|---|
| `doodle.py` | Draws a character as SVG: body, costume, face, hair, reacting cloth |
| `anim.py` | Scene JSON to frames, speech, lip sync and MP4 |
| `scene_writer.py` | Seed, cast and headlines to a scene plan, then the pushed lines |
| `news.py` | Fetches and filters the headlines in `cast.toml` |
| `voices.py` | Persona-neuron pushes in MLX |
| `views.py` | A character's view of the scene, and the vision model that speaks from it |
| `tts_server.py` | Qwen3-TTS behind a small local HTTP endpoint |
| `episode.py` | Cards, scenes, captions and chapters joined into one episode |
| `launch.py` | Posting copy for YouTube, X, Bluesky and Reddit |
| `episodes/ep1` | The scenes, TV programs, captions and chapters of Episode 1 |

## Credits

- [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) and Qwen3-TTS, by the Qwen team (Apache 2.0).
- [MLX](https://github.com/ml-explore/mlx), [mlx-lm](https://github.com/ml-explore/mlx-lm), [mlx-vlm](https://github.com/Blaizzy/mlx-vlm) and [mlx-audio](https://github.com/Blaizzy/mlx-audio).
- [resvg](https://github.com/RazrFalcon/resvg) and ffmpeg.
- The headlines in Episode 1 come from GOV.UK, The Hindu, BBC News and Hacker News. The scene files keep only each headline and its link.

## Licence

Apache 2.0. See `LICENSE`.

Made by [hedwigai](https://hedwigai.com).
