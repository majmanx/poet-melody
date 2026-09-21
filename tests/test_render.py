import random

import numpy as np
import pytest

from poet_melody import generate
from poet_melody.render import adsr, oscillator, render, render_note, _stft_lowpass
from poet_melody.synth import Env, Osc, Patch


def test_oscillators_bounded():
    rng = random.Random(0)
    freq = np.full(4000, 220.0)
    for w in ("sine", "triangle", "saw", "square", "supersaw", "noise"):
        y = oscillator(w, freq, 22050, rng)
        assert y.shape == (4000,)
        assert np.isfinite(y).all()
        assert np.abs(y).max() <= 2.0


def test_adsr_shape():
    env = adsr(Env(0.01, 0.1, 0.5, 0.1), 2205, 4410, 22050)
    assert env.max() <= 1.0 + 1e-6
    assert 0.5 <= env[2000] <= 0.7          # decaying towards the sustain level
    assert abs(env[2204] - env[2205]) < 0.05  # continuous into the release
    assert env[-1] < 0.1


def test_lowpass_removes_highs():
    sr = 22050
    t = np.arange(sr) / sr
    x = (np.sin(2 * np.pi * 200 * t) + np.sin(2 * np.pi * 6000 * t)).astype(np.float32)
    y = _stft_lowpass(x, np.full(sr, 800.0, dtype=np.float32), 0.0, sr)
    spec = np.abs(np.fft.rfft(y[2048:-2048]))
    f = np.fft.rfftfreq(len(y[2048:-2048]), 1 / sr)
    assert spec[np.argmin(abs(f - 6000))] < 0.05 * spec[np.argmin(abs(f - 200))]


def test_render_note_and_full_render():
    patch = Patch("t", "lead", oscs=[Osc("saw")], cutoff=2000, filter_env_amount=1.0, lfo_rate=5, lfo_depth=10)
    y = render_note(patch, 60, 0.3, 100, 22050, random.Random(1))
    assert np.isfinite(y).all() and len(y) > 0.3 * 22050
    comp = generate("举头望明月，\n低头思故乡。", style="synthwave")
    audio = render(comp, sr=8000)
    assert audio.shape[1] == 2
    assert np.isfinite(audio).all()
    assert 0.5 < np.abs(audio).max() <= 1.0
    assert np.sqrt((audio ** 2).mean()) > 0.02
