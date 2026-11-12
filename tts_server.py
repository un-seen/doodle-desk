#!/usr/bin/env python3
"""Qwen3-TTS on Apple silicon (MLX), kept loaded behind a tiny local HTTP endpoint.

    python tts_server.py [--port 8091] [--model mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit]

POST /tts  {"text", "speaker", "instruct", "language", "out"}  -> writes a mono WAV to `out`
           and answers {"ok": true, "seconds": ..., "sample_rate": ...}
GET  /speakers -> the model's preset speakers

sonic-forge's /api/voice calls this for voices with "engine": "qwen" (QWEN_TTS_URL), so the
animation keeps one voice API. Requests run one at a time: the model is not shared across threads.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import soundfile as sf

LOCK = threading.Lock()
MODEL = None


def speakers():
    cfg = MODEL.config
    for obj in (cfg, getattr(cfg, "talker_config", None)):
        if obj is not None and isinstance(getattr(obj, "spk_id", None), dict):
            return sorted(obj.spk_id)
    return []


def speakable(text):
    """Spell out acronyms (TV -> T.V.): the model tends to skip a bare all-caps word."""
    import re
    return re.sub(r"\b([A-Z]{2,4})\b", lambda m: ".".join(m.group(1)) + ".", text)


def synth(req):
    text = speakable((req.get("text") or "").strip())
    if not text:
        raise ValueError("empty text")
    kw = dict(text=text, speaker=req.get("speaker") or "ryan", language=req.get("language") or "English")
    if req.get("instruct"):
        kw["instruct"] = req["instruct"]
    t = time.time()
    with LOCK:
        parts = list(MODEL.generate_custom_voice(**kw))
    audio = np.concatenate([np.array(p.audio, dtype=np.float32) for p in parts])
    sr = int(getattr(MODEL, "sample_rate", 24000))
    sf.write(req["out"], audio, sr, subtype="PCM_16")
    return {"ok": True, "seconds": round(len(audio) / sr, 3), "sample_rate": sr, "took": round(time.time() - t, 2)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/speakers":
            return self._send(200, {"speakers": speakers()})
        self._send(404, {"ok": False})

    def do_POST(self):
        if self.path != "/tts":
            return self._send(404, {"ok": False})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._send(200, synth(req))
        except Exception as e:  # report, keep serving
            self._send(400, {"ok": False, "log": str(e)})

    def log_message(self, *a):
        pass


def main():
    global MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--model", default="mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit")
    a = ap.parse_args()
    from mlx_audio.tts.utils import load_model
    t = time.time()
    MODEL = load_model(a.model)
    print(f"loaded {a.model} in {time.time() - t:.1f}s; speakers {speakers()}", flush=True)
    HTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
