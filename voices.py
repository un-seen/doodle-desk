"""Persona-neuron pushes for Qwen3.5-4B in MLX.

A push on neuron n of layer L at dose d adds a * W_down[:, n] to that layer's MLP output on
every token, with a = sign * d * median(|h_L|) / |W_down[:, n]|: the recipe of the neuron
write-up (https://hedwigai.com/blog/qwen-personality-neurons), so a dose means the same. W_down comes
from the 4-bit weights, dequantised.
"""
import json
import os
import re

import mlx.core as mx
import mlx.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = re.compile(r"L(\d+)N(\d+)([+-])")


class Pushed(nn.Module):
    """An MLP with an optional fixed vector added to its output."""

    def __init__(self, inner):
        super().__init__()
        self.inner = inner
        self.push = None

    def __call__(self, x):
        y = self.inner(x)
        return y if self.push is None else y + self.push.astype(y.dtype)


class Voices:
    def __init__(self, model, catalog, median_path=os.path.join(HERE, "median_norms.json")):
        lm = model.language_model if hasattr(model, "language_model") else model
        self.layers = lm.model.layers
        for layer in self.layers:
            if not isinstance(layer.mlp, Pushed):
                layer.mlp = Pushed(layer.mlp)
        self.catalog = {k: tuple(v) for k, v in catalog.items()}
        self.median = json.load(open(median_path))
        self.on = None

    def parse(self, voice):
        """(layer, neuron, sign) for a catalog name or a raw 'L14N8949+'."""
        if voice in self.catalog:
            return self.catalog[voice]
        m = RAW.fullmatch(voice or "")
        if not m:
            raise ValueError(f"unknown voice {voice!r}: use one of {sorted(self.catalog)} or L<layer>N<neuron><+|->")
        return int(m[1]), int(m[2]), 1 if m[3] == "+" else -1

    def vector(self, L, n, sign, dose):
        d = self.layers[L].mlp.inner.down_proj
        col = mx.dequantize(d.weight, d.scales, d.biases, d.group_size, d.bits)[:, n].astype(mx.float32)
        return sign * dose * self.median[L] * col / mx.linalg.norm(col)

    def set(self, voice=None, dose=0.0):
        """Turn one voice on (or none). Only one layer carries a push at a time."""
        self.clear()
        if voice and dose:
            L, n, sign = self.parse(voice)
            self.layers[L].mlp.push = self.vector(L, n, sign, dose)
            self.on = (voice, dose)

    def clear(self):
        for layer in self.layers:
            layer.mlp.push = None
        self.on = None
