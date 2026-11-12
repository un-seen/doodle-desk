"""What a character sees, and a vision-language Qwen that speaks from it.

view(scene, t, who) renders the scene at time t exactly as the animation will draw it, then cuts
out the pixel columns the speaker's own body takes up (x1..x2) and joins the rest: the character
sees the TV, the other character, the sign, the sea, the bubbles already said, but not itself.

Seer loads Qwen3.5-4B with its vision tower (mlx-vlm, 4-bit) and writes a character's next line
from that view plus the script so far, with the character's persona neuron pushed on every token
(voices.Voices, the same recipe as the rig server).
"""
import io
import os
import re

import anim

FPS = anim.FPS


def view(scene, t, who, out_path, max_w=768):
    """Render the frame at t, drop the speaker's columns, save a PNG; returns (path, (x1, x2))."""
    import resvg_py
    from PIL import Image
    actors, _, things = anim.compile_scene(scene)
    svg = anim.frame_svg(scene, actors, max(0.0, t - .05), int(t * FPS), things)
    img = Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg)))).convert("RGB")
    a = actors[who]
    p = anim.pose_at(a, max(0.0, t - .05), actors, things)
    cx = 170 + p["x"] * (anim.W - 340)
    half = 1.25 * anim.R * a.g["size"]                 # body, arms and pill
    x1, x2 = int(max(0, cx - half)), int(min(img.width, cx + half))
    left, right = img.crop((0, 0, x1, img.height)), img.crop((x2, 0, img.width, img.height))
    seen = Image.new("RGB", (left.width + right.width + 6, img.height), (40, 40, 40))   # a thin seam where they stand
    seen.paste(left, (0, 0))
    seen.paste(right, (left.width + 6, 0))
    if seen.width > max_w:
        seen = seen.resize((max_w, int(seen.height * max_w / seen.width)))
    seen.save(out_path)
    return out_path, (x1, x2)


class Seer:
    def __init__(self, model_path, catalog):
        from mlx_vlm import load
        from voices import Voices
        self.model, self.processor = load(model_path)
        self.voices = Voices(self.model, catalog)

    def say(self, image, prompt_text, speaker, n=3, seed=0, max_tokens=40):
        """n candidate lines for `speaker`, continuing an answer that starts with "SPEAKER:"."""
        import mlx.core as mx
        from mlx_vlm import stream_generate
        tok = self.processor.tokenizer if hasattr(self.processor, "tokenizer") else self.processor
        msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt_text}]}]
        try:
            text = self.processor.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False,
                                                      enable_thinking=False)
        except TypeError:
            text = self.processor.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        text += f"{speaker.upper()}:"
        outs = []
        for k in range(n):
            mx.random.seed(seed + k)
            got = ""
            for r in stream_generate(self.model, self.processor, text, image=[image], max_tokens=max_tokens,
                                     temperature=.8, top_p=.95):
                got += r.text
                if "\n" in got.lstrip() or "(" in got or "<" in got:
                    break
            body = re.split(r"[\n(]|<think>|</?\w+>", got)[0]
            outs.append(re.sub(r"\s+", " ", body.replace('"', "").replace("“", "").replace("”", "")).strip())
        return outs
