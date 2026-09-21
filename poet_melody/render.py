"""Offline audio renderer (numpy): subtractive synthesis of a Composition.

Signal path per note: oscillators (polyBLEP saw/square, sine, triangle,
supersaw, noise) -> ADSR-modulated low-pass filter (STFT-domain, so the
envelope can sweep without per-sample Python loops) -> amplitude ADSR ->
soft drive.  Per-track: delay, chorus, convolution reverb with a synthetic
stereo impulse response, panning.  Mix bus: sidechain pump (for grooves),
soft clipper, normalisation, 16-bit stereo WAV.
"""
from __future__ import annotations

import math
import random
import wave
from typing import Dict, List, Optional, Tuple

import numpy as np

from .score import Composition, Note, Timeline, Track
from .styles import STYLES
from .synth import Env, Osc, Patch
from .midi import DRUM_NOTES

TWO_PI = 2.0 * math.pi

# Mix-bus trims per role (the lead carries the text, so it sits on top).
ROLE_TRIM = {"pad": 0.55, "keys": 0.8, "bass": 0.9, "lead": 1.25, "drums": 0.75}


# ---------------------------------------------------------------------------
# Oscillators
# ---------------------------------------------------------------------------

def _phase(freq: np.ndarray, sr: int, phase0: float) -> np.ndarray:
    return (phase0 + np.cumsum(freq / sr)) % 1.0


def _polyblep(t: np.ndarray, dt: np.ndarray) -> np.ndarray:
    out = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    out[m] = x + x - x * x - 1.0
    m2 = t > 1.0 - dt
    x = (t[m2] - 1.0) / dt[m2]
    out[m2] = x * x + x + x + 1.0
    return out


def oscillator(wave_: str, freq: np.ndarray, sr: int, rng: random.Random, pw: float = 0.5) -> np.ndarray:
    n = len(freq)
    if wave_ == "noise":
        return np.asarray(np.random.default_rng(rng.randrange(1 << 30)).standard_normal(n) * 0.5, dtype=np.float32)
    if wave_ == "supersaw":
        # 7 detuned saws, JP-8000 style, mixed with a slight centre emphasis.
        offs = [-0.11, -0.06, -0.02, 0.0, 0.02, 0.06, 0.11]
        acc = np.zeros(n, dtype=np.float32)
        for o in offs:
            acc += oscillator("saw", freq * (2.0 ** (o / 12.0 * 0.5)), sr, rng) * (0.5 if o else 1.0)
        return acc / 3.5
    t = _phase(freq, sr, rng.random())
    dt = np.maximum(freq / sr, 1e-6)
    if wave_ == "sine":
        return np.sin(TWO_PI * t).astype(np.float32)
    if wave_ == "triangle":
        return (2.0 * np.abs(2.0 * t - 1.0) - 1.0).astype(np.float32)
    if wave_ == "saw":
        y = 2.0 * t - 1.0 - _polyblep(t, dt)
        return y.astype(np.float32)
    if wave_ == "square":
        y = np.where(t < pw, 1.0, -1.0) + _polyblep(t, dt) - _polyblep((t + 1.0 - pw) % 1.0, dt)
        return y.astype(np.float32)
    raise ValueError(f"unknown wave {wave_!r}")


# ---------------------------------------------------------------------------
# Envelopes and filter
# ---------------------------------------------------------------------------

def adsr(env: Env, n_on: int, n_total: int, sr: int, curve: float = 2.0) -> np.ndarray:
    """Envelope with ``n_on`` samples of gate then release; total ``n_total`` samples."""
    a = max(1, int(env.attack * sr))
    d = max(1, int(env.decay * sr))
    r = max(1, int(env.release * sr))
    out = np.zeros(n_total, dtype=np.float32)
    t = np.arange(n_total)
    # Gate phase
    att = np.minimum(1.0, t / a)
    dec = env.sustain + (1.0 - env.sustain) * np.exp(-np.maximum(0, t - a) / (d / curve))
    gate = np.where(t < a, att, dec)
    out[:n_on] = gate[:n_on]
    level_at_release = gate[min(n_on, n_total) - 1] if n_on > 0 else 0.0
    rel = level_at_release * np.exp(-np.arange(n_total - n_on) / (r / curve))
    out[n_on:] = rel[: n_total - n_on]
    return out


def _stft_lowpass(x: np.ndarray, cutoff: np.ndarray, resonance: float, sr: int,
                  frame: int = 1024, hop: int = 256) -> np.ndarray:
    """Time-varying resonant low-pass via short-time Fourier magnitude shaping."""
    n = len(x)
    if n < frame:
        pad = frame - n
        x = np.concatenate([x, np.zeros(pad, dtype=np.float32)])
        cutoff = np.concatenate([cutoff, np.full(pad, cutoff[-1] if len(cutoff) else 1000.0)])
    win = np.hanning(frame).astype(np.float32)
    total = len(x)
    n_frames = 1 + math.ceil((total - frame) / hop)
    padded = np.concatenate([x, np.zeros(n_frames * hop + frame - total, dtype=np.float32)])
    idx = np.arange(frame)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = padded[idx] * win
    spec = np.fft.rfft(frames, axis=1)
    freqs = np.fft.rfftfreq(frame, 1.0 / sr)
    centres = np.minimum(len(cutoff) - 1, hop * np.arange(n_frames) + frame // 2)
    fc = np.maximum(40.0, cutoff[centres])[:, None]
    ratio = freqs[None, :] / fc
    mag = 1.0 / np.sqrt(1.0 + ratio ** 4)                       # 12 dB/oct
    if resonance > 0:
        peak = 1.0 + 6.0 * resonance * np.exp(-((ratio - 1.0) / 0.18) ** 2)
        mag = mag * peak
    spec *= mag
    out_frames = np.fft.irfft(spec, n=frame, axis=1) * win
    out = np.zeros(len(padded), dtype=np.float32)
    norm = np.zeros(len(padded), dtype=np.float32)
    np.add.at(out, idx, out_frames.astype(np.float32))
    np.add.at(norm, idx, (win * win)[None, :].repeat(n_frames, axis=0))
    out /= np.maximum(norm, 1e-3)
    return out[:n]


# ---------------------------------------------------------------------------
# Voice rendering
# ---------------------------------------------------------------------------

def midi_to_hz(p: float) -> float:
    return 440.0 * 2.0 ** ((p - 69) / 12.0)


def render_note(patch: Patch, pitch: float, dur_s: float, velocity: int, sr: int, rng: random.Random,
                prev_pitch: Optional[float] = None) -> np.ndarray:
    n_on = max(1, int(dur_s * sr))
    n_total = n_on + int((patch.amp_env.release + 0.02) * sr)
    t = np.arange(n_total) / sr
    base = midi_to_hz(pitch)
    freq = np.full(n_total, base, dtype=np.float64)
    if patch.glide > 0 and prev_pitch is not None and prev_pitch != pitch:
        g = np.exp(-t / max(patch.glide, 1e-3))
        freq = midi_to_hz(prev_pitch) * g + base * (1 - g)
    if patch.lfo_rate > 0 and patch.lfo_target == "pitch" and patch.lfo_depth > 0:
        fade = np.clip((t - patch.lfo_delay) / 0.4, 0, 1)
        freq = freq * 2.0 ** (patch.lfo_depth / 1200.0 * fade * np.sin(TWO_PI * patch.lfo_rate * t + rng.random() * TWO_PI))
    sig = np.zeros(n_total, dtype=np.float32)
    voices = max(1, patch.unison)
    for o in patch.oscs:
        f_o = freq * 2.0 ** o.octave * 2.0 ** (o.detune / 1200.0)
        if voices > 1:
            for v in range(voices):
                spread = (v / (voices - 1) - 0.5) * patch.unison_detune
                sig += oscillator(o.wave, f_o * 2.0 ** (spread / 1200.0), sr, rng, o.pulse_width) * (o.level / math.sqrt(voices))
        else:
            sig += oscillator(o.wave, f_o, sr, rng, o.pulse_width) * o.level
    if patch.noise > 0:
        sig += oscillator("noise", freq, sr, rng) * patch.noise
    vel = velocity / 127.0
    # Filter envelope + key tracking + velocity + optional cutoff LFO.
    fenv = adsr(patch.filter_env, n_on, n_total, sr)
    cutoff = patch.cutoff * 2.0 ** (patch.filter_env_amount * fenv) * 2.0 ** (patch.key_tracking * (pitch - 60) / 12.0)
    cutoff = cutoff * (0.6 + 0.6 * vel)
    if patch.lfo_rate > 0 and patch.lfo_target == "cutoff":
        cutoff = cutoff * 2.0 ** (patch.lfo_depth * np.sin(TWO_PI * patch.lfo_rate * t))
    cutoff = np.minimum(cutoff, sr * 0.45)
    if not (patch.cutoff >= sr * 0.45 and patch.filter_env_amount == 0):
        sig = _stft_lowpass(sig, cutoff.astype(np.float32), patch.resonance, sr)
    amp = adsr(patch.amp_env, n_on, n_total, sr)
    if patch.lfo_rate > 0 and patch.lfo_target == "amp":
        amp = amp * (1.0 - patch.lfo_depth * 0.5 * (1 + np.sin(TWO_PI * patch.lfo_rate * t)))
    sig = sig * amp * (0.35 + 0.65 * vel)
    if patch.drive > 0:
        k = 1.0 + 6.0 * patch.drive
        sig = np.tanh(sig * k) / math.tanh(k * 0.8)
    return sig.astype(np.float32)


# ---------------------------------------------------------------------------
# Drums
# ---------------------------------------------------------------------------

def _drum(kind: str, sr: int, rng: random.Random, style: str) -> np.ndarray:
    g = np.random.default_rng(rng.randrange(1 << 30))
    if kind == "kick":
        n = int(0.45 * sr)
        t = np.arange(n) / sr
        f = 42 + 140 * np.exp(-t / 0.035)
        ph = np.cumsum(f / sr)
        y = np.sin(TWO_PI * ph) * np.exp(-t / 0.18)
        click = g.standard_normal(n) * np.exp(-t / 0.004) * 0.4
        y = np.tanh((y + click) * 1.8)
    elif kind == "snare":
        n = int(0.3 * sr)
        t = np.arange(n) / sr
        tone = np.sin(TWO_PI * 185 * t) * np.exp(-t / 0.06) * 0.6
        noise = g.standard_normal(n) * np.exp(-t / (0.12 if style != "synthwave" else 0.25))
        noise = noise - np.concatenate([[0], noise[:-1]]) * 0.6  # crude high-pass
        y = tone + noise * 0.8
        if style == "synthwave":  # gated reverb feel
            y[int(0.18 * sr):] *= 0.05
    elif kind == "clap":
        n = int(0.25 * sr)
        t = np.arange(n) / sr
        env = np.zeros(n)
        for k in range(3):
            env += np.exp(-np.maximum(0, t - 0.01 * k) / 0.008) * (t >= 0.01 * k)
        env += np.exp(-np.maximum(0, t - 0.03) / 0.09) * (t >= 0.03)
        noise = g.standard_normal(n)
        noise = noise - np.concatenate([[0], noise[:-1]]) * 0.7
        y = noise * env * 0.7
    elif kind in ("hat", "ohat", "ride"):
        n = int((0.06 if kind == "hat" else 0.35) * sr)
        t = np.arange(n) / sr
        noise = g.standard_normal(n)
        for _ in range(2):
            noise = noise - np.concatenate([[0], noise[:-1]]) * 0.85
        y = noise * np.exp(-t / (0.02 if kind == "hat" else 0.12)) * 0.5
        if kind == "ride":
            y += np.sin(TWO_PI * 3200 * t) * np.exp(-t / 0.2) * 0.1
    else:
        return np.zeros(1, dtype=np.float32)
    return y.astype(np.float32)


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------

def _fft_convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    X = np.fft.rfft(x, size)
    H = np.fft.rfft(ir, size)
    return np.fft.irfft(X * H, size)[:n].astype(np.float32)


def _reverb_ir(seconds: float, sr: int, rng: random.Random) -> Tuple[np.ndarray, np.ndarray]:
    n = int(seconds * sr)
    g = np.random.default_rng(rng.randrange(1 << 30))
    t = np.arange(n) / sr
    env = np.exp(-6.9 * t / seconds)                      # -60 dB at ``seconds``
    pre = int(0.012 * sr)
    l = g.standard_normal(n) * env
    r = g.standard_normal(n) * env
    # darken the tail: simple one-pole low-pass, implemented with an FIR average
    kern = np.ones(8) / 8.0
    l = np.convolve(l, kern, mode="same")
    r = np.convolve(r, kern, mode="same")
    l[:pre] = 0
    r[:pre] = 0
    norm = math.sqrt(np.sum(l * l)) + 1e-9
    return (l / norm * 0.9).astype(np.float32), (r / norm * 0.9).astype(np.float32)


def _delay(x: np.ndarray, time_s: float, feedback: float, sr: int, taps: int = 8) -> np.ndarray:
    d = int(time_s * sr)
    if d <= 0:
        return np.zeros_like(x)
    out = np.zeros(len(x) + d * taps, dtype=np.float32)
    g = 1.0
    for k in range(1, taps + 1):
        g *= feedback
        if g < 0.01:
            break
        out[k * d: k * d + len(x)] += x * g
    return out


def _chorus(x: np.ndarray, depth: float, sr: int, rng: random.Random) -> np.ndarray:
    """Cheap chorus: two slowly modulated short delays mixed in."""
    n = len(x)
    t = np.arange(n) / sr
    out = np.zeros(n, dtype=np.float32)
    for rate, base in ((0.31, 0.012), (0.47, 0.019)):
        d = base + 0.004 * np.sin(TWO_PI * rate * t + rng.random() * TWO_PI)
        src = np.arange(n) - d * sr
        src = np.clip(src, 0, n - 1)
        i0 = np.floor(src).astype(int)
        frac = (src - i0).astype(np.float32)
        i1 = np.minimum(i0 + 1, n - 1)
        out += x[i0] * (1 - frac) + x[i1] * frac
    return x * (1 - 0.5 * depth) + out * 0.5 * depth


def _sidechain_curve(n: int, tl: Timeline, depth: float, sr: int, start_beat: float, end_beat: float) -> np.ndarray:
    curve = np.ones(n, dtype=np.float32)
    b = math.floor(start_beat)
    while b < end_beat:
        s = int(tl.seconds(b) * sr)
        length = int(0.22 * sr)
        if s < n:
            seg = np.arange(min(length, n - s)) / sr
            curve[s: s + len(seg)] *= 1.0 - depth * np.exp(-seg / 0.06)
        b += 1
    return curve


# ---------------------------------------------------------------------------
# Track / composition rendering
# ---------------------------------------------------------------------------

def render_track(track: Track, patch: Optional[Patch], comp: Composition, sr: int, rng: random.Random,
                 total_samples: int) -> Tuple[np.ndarray, np.ndarray]:
    tl = comp.timeline
    dry = np.zeros(total_samples, dtype=np.float32)
    if track.role == "drums":
        cache: Dict[int, np.ndarray] = {}
        inv = {v: k for k, v in DRUM_NOTES.items()}
        for n in track.notes:
            kind = inv.get(n.pitch, "hat")
            if n.pitch not in cache:
                cache[n.pitch] = _drum(kind, sr, rng, comp.style)
            s = int(tl.seconds(n.start) * sr)
            y = cache[n.pitch] * (n.velocity / 127.0)
            end = min(total_samples, s + len(y))
            if s < total_samples:
                dry[s:end] += y[: end - s]
        # A touch of room on the drums.
        l_ir, r_ir = _reverb_ir(0.6 if comp.style != "synthwave" else 1.2, sr, rng)
        wet_l = _fft_convolve(dry, l_ir)[:total_samples]
        wet_r = _fft_convolve(dry, r_ir)[:total_samples]
        mix = 0.12 if comp.style != "synthwave" else 0.25
        return dry * (1 - mix) + wet_l * mix, dry * (1 - mix) + wet_r * mix
    assert patch is not None
    prev_pitch: Optional[float] = None
    notes = sorted(track.notes, key=lambda n: n.start)
    for n in notes:
        s0 = tl.seconds(n.start)
        s1 = tl.seconds(n.start + n.duration)
        y = render_note(patch, n.pitch, max(0.02, s1 - s0), n.velocity, sr, rng, prev_pitch)
        prev_pitch = n.pitch
        s = int(s0 * sr)
        end = min(total_samples, s + len(y))
        if s < total_samples:
            dry[s:end] += y[: end - s]
    sig = dry
    if patch.chorus > 0:
        sig = _chorus(sig, patch.chorus, sr, rng)
    if patch.delay_mix > 0 and patch.delay_time > 0:
        d = _delay(sig, patch.delay_time * 60.0 / comp.bpm, patch.delay_feedback, sr)[:total_samples]
        sig = sig + d * patch.delay_mix
    left = sig * math.cos((patch.pan + track.pan + 1) * math.pi / 4)
    right = sig * math.sin((patch.pan + track.pan + 1) * math.pi / 4)
    if patch.reverb_mix > 0:
        l_ir, r_ir = _reverb_ir(patch.reverb_size, sr, rng)
        wl = _fft_convolve(sig, l_ir)[:total_samples]
        wr = _fft_convolve(sig, r_ir)[:total_samples]
        m = patch.reverb_mix
        left = left * (1 - m * 0.6) + wl * m
        right = right * (1 - m * 0.6) + wr * m
    return left, right


def render(comp: Composition, sr: int = 44100, seed: Optional[int] = None) -> np.ndarray:
    """Render a composition to a float32 stereo array of shape (n, 2) in -1..1."""
    rng = random.Random(comp.seed if seed is None else seed)
    st = STYLES.get(comp.style)
    tail = 3.5
    total_s = comp.total_seconds + tail
    total = int(total_s * sr)
    mix_l = np.zeros(total, dtype=np.float32)
    mix_r = np.zeros(total, dtype=np.float32)
    patches = {role: Patch(**{**d, "oscs": [Osc(**o) for o in d["oscs"]],
                              "filter_env": Env(**d["filter_env"]), "amp_env": Env(**d["amp_env"])})
               for role, d in comp.patches.items()}
    sidechain = st.sidechain if st else 0.0
    sc_curve = None
    if sidechain > 0 and comp.track("drums") is not None:
        drums = comp.track("drums")
        assert drums is not None
        sc_curve = _sidechain_curve(total, comp.timeline, sidechain, sr, 0.0, max(n.start for n in drums.notes))
    for tr in comp.tracks:
        patch = patches.get(tr.role)
        l, r = render_track(tr, patch, comp, sr, rng, total)
        # Per-track peak normalisation (downwards only) so the role trims below
        # define the balance regardless of how many voices a track stacks.
        peak = max(float(np.max(np.abs(l))), float(np.max(np.abs(r))), 1e-6)
        if peak > 1.0:
            l, r = l / peak, r / peak
        gain = tr.level * ROLE_TRIM.get(tr.role, 1.0)
        if sc_curve is not None and tr.role in ("pad", "bass", "keys"):
            l, r = l * sc_curve, r * sc_curve
        mix_l += l * gain
        mix_r += r * gain
    out = np.stack([mix_l, mix_r], axis=1)
    peak = float(np.max(np.abs(out))) or 1.0
    out = out / peak * 0.85
    out = np.tanh(out * 1.15) / math.tanh(1.15)
    # Fade in/out to avoid clicks.
    fade = int(0.01 * sr)
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return out.astype(np.float32)


def write_wav(audio: np.ndarray, path: str, sr: int = 44100) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2 if pcm.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
