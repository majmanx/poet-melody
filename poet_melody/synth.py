"""Timbre design: map text affect + style to synthesizer patches.

A :class:`Patch` is a compact, engine-agnostic description of a subtractive
synth voice (oscillators -> filter -> amplifier, with envelopes, an LFO and
send effects). The bundled renderer (:mod:`poet_melody.render`) and the web
player both understand it, and the ``recipe`` text tells a human how to
rebuild it in any hardware or software synth.

Design rules (all continuous, so nearby texts produce nearby sounds):

* warmth   -> sine/triangle content and lower filter cutoff
* arousal  -> faster attacks, shorter releases, more filter-envelope bite
* tension  -> wider detune, resonance, slow cutoff LFO
* valence  -> brightness (cutoff) and reverb size (dark texts get bigger rooms)
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from .analysis import TextFeatures
from .styles import Style


@dataclass
class Osc:
    wave: str = "saw"          # sine | triangle | saw | square | supersaw | noise
    octave: int = 0
    detune: float = 0.0        # cents
    level: float = 1.0
    pulse_width: float = 0.5


@dataclass
class Env:
    attack: float = 0.01
    decay: float = 0.2
    sustain: float = 0.8
    release: float = 0.3


@dataclass
class Patch:
    name: str
    role: str
    oscs: List[Osc] = field(default_factory=lambda: [Osc()])
    unison: int = 1
    unison_detune: float = 0.0     # cents spread across unison voices
    cutoff: float = 2000.0         # Hz
    resonance: float = 0.1         # 0..1
    filter_env_amount: float = 0.0  # octaves added at the envelope peak
    filter_env: Env = field(default_factory=lambda: Env(0.01, 0.3, 0.0, 0.3))
    amp_env: Env = field(default_factory=Env)
    key_tracking: float = 0.3      # cutoff follows pitch (0..1)
    lfo_rate: float = 0.0          # Hz
    lfo_depth: float = 0.0         # cents (pitch), octaves (cutoff) or 0..1 (amp)
    lfo_target: str = "pitch"      # pitch | cutoff | amp
    lfo_delay: float = 0.0         # seconds before vibrato fades in
    drive: float = 0.0             # 0..1 soft saturation
    noise: float = 0.0             # breath / air level
    glide: float = 0.0             # seconds
    reverb_mix: float = 0.2
    reverb_size: float = 2.0       # seconds
    delay_time: float = 0.0        # beats (0 = off)
    delay_feedback: float = 0.3
    delay_mix: float = 0.0
    chorus: float = 0.0            # 0..1
    pan: float = 0.0
    level: float = 0.8
    recipe: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def _recipe(p: Patch) -> str:
    osc = " + ".join(
        f"{o.wave}{'' if o.octave == 0 else f' {o.octave:+d}oct'}{'' if not o.detune else f' {o.detune:+.0f}c'}"
        for o in p.oscs)
    uni = f", unison x{p.unison} ({p.unison_detune:.0f}c)" if p.unison > 1 else ""
    lfo = f"; LFO {p.lfo_rate:.2f}Hz -> {p.lfo_target} ({p.lfo_depth:g})" if p.lfo_rate else ""
    fx = f"; reverb {p.reverb_mix:.0%} ({p.reverb_size:.1f}s)"
    if p.delay_mix:
        fx += f", delay {p.delay_time:g} beat fb {p.delay_feedback:.0%} mix {p.delay_mix:.0%}"
    if p.chorus:
        fx += f", chorus {p.chorus:.0%}"
    fe, ae = p.filter_env, p.amp_env
    return (f"{osc}{uni}; LPF {p.cutoff:.0f}Hz Q {p.resonance:.2f} env +{p.filter_env_amount:.1f}oct "
            f"(A{fe.attack:.2f} D{fe.decay:.2f} S{fe.sustain:.2f} R{fe.release:.2f}); "
            f"amp A{ae.attack:.2f} D{ae.decay:.2f} S{ae.sustain:.2f} R{ae.release:.2f}"
            f"{lfo}{fx}")


def design_patches(f: TextFeatures, style: Style, rng: random.Random) -> Dict[str, Patch]:
    """Return patches keyed by role: pad, keys, bass, lead (drums are synthesised directly)."""
    warm, ar, ten, val = f.warmth, f.arousal, f.tension, f.valence
    bright = 0.5 + 0.5 * val
    # Shared affect-driven numbers.
    pad_cut = _lerp(900, 4200, 0.6 * bright + 0.4 * (1 - warm))
    lead_cut = _lerp(1500, 6500, 0.5 * bright + 0.5 * ar)
    reverb_size = _lerp(1.4, 5.0, 0.5 * (1 - ar) + 0.5 * (1 - bright))
    detune = _lerp(4, 22, ten)
    res = _lerp(0.05, 0.45, 0.5 * ten + 0.5 * ar)
    att_pad = _lerp(1.2, 0.15, ar)
    rel_pad = _lerp(2.5, 0.6, ar)

    fam = style.family
    name = style.name
    patches: Dict[str, Patch] = {}

    # ---- PAD ---------------------------------------------------------------
    if name in ("classical", "romantic", "cinematic", "folk"):
        pad = Patch("Chamber Strings" if warm > 0.5 else "Glass Strings", "pad",
                    oscs=[Osc("saw", 0, -detune * 0.5, 0.6), Osc("saw", 0, detune * 0.5, 0.6), Osc("triangle", -1, 0, 0.35)],
                    cutoff=_lerp(1400, 3200, bright), resonance=0.05,
                    amp_env=Env(att_pad * 0.8, 0.5, 0.85, rel_pad), filter_env_amount=0.4,
                    filter_env=Env(att_pad, 1.0, 0.6, rel_pad),
                    lfo_rate=5.2, lfo_depth=5, lfo_target="pitch", lfo_delay=0.6,
                    reverb_mix=0.35, reverb_size=reverb_size, chorus=0.3, level=0.55)
    elif name == "ambient":
        pad = Patch("Slow Aurora", "pad",
                    oscs=[Osc("sine", 0, 0, 0.7), Osc("triangle", 0, detune, 0.5), Osc("saw", 1, -detune, 0.2)],
                    cutoff=_lerp(700, 2400, bright), resonance=0.15,
                    amp_env=Env(_lerp(3.0, 1.2, ar), 1.0, 0.9, 4.0), filter_env_amount=0.8,
                    filter_env=Env(4.0, 2.0, 0.5, 4.0), lfo_rate=0.08, lfo_depth=0.6, lfo_target="cutoff",
                    reverb_mix=0.55, reverb_size=reverb_size + 2.0, chorus=0.5, level=0.55)
    elif name in ("synthwave", "trance"):
        pad = Patch("Neon Supersaw" if name == "synthwave" else "Uplift Supersaw", "pad",
                    oscs=[Osc("supersaw", 0, 0, 0.8), Osc("square", -1, 0, 0.25, 0.4)], unison=7,
                    unison_detune=_lerp(12, 28, ten), cutoff=_lerp(1800, 5000, bright), resonance=0.12,
                    amp_env=Env(_lerp(0.6, 0.05, ar), 0.4, 0.8, _lerp(1.4, 0.5, ar)),
                    filter_env_amount=0.5, filter_env=Env(0.4, 1.2, 0.5, 1.0),
                    reverb_mix=0.3, reverb_size=reverb_size, chorus=0.6, level=0.5)
    elif name == "house":
        pad = Patch("Deep Chord", "pad", oscs=[Osc("saw", 0, -8, 0.5), Osc("saw", 0, 8, 0.5), Osc("sine", -1, 0, 0.4)],
                    cutoff=_lerp(700, 1800, bright), resonance=0.25,
                    amp_env=Env(0.01, 0.35, 0.0, 0.3), filter_env_amount=1.2, filter_env=Env(0.005, 0.25, 0.0, 0.3),
                    reverb_mix=0.25, reverb_size=1.6, chorus=0.4, level=0.5)
    else:  # lofi, jazz, neo_soul, pop
        pad = Patch("Tape Pad", "pad", oscs=[Osc("triangle", 0, -detune * 0.4, 0.6), Osc("saw", 0, detune * 0.4, 0.35), Osc("sine", -1, 0, 0.3)],
                    cutoff=pad_cut * 0.6, resonance=0.08, amp_env=Env(att_pad, 0.5, 0.8, rel_pad),
                    lfo_rate=0.35, lfo_depth=7, lfo_target="pitch", reverb_mix=0.3, reverb_size=reverb_size, chorus=0.35, level=0.45)
    patches["pad"] = pad

    # ---- KEYS ----------------------------------------------------------------
    if name in ("classical", "romantic"):
        keys = Patch("Felt Piano", "keys", oscs=[Osc("triangle", 0, 0, 0.7), Osc("saw", 0, 0, 0.3), Osc("sine", 1, 0, 0.25)],
                     cutoff=_lerp(1800, 4200, bright), resonance=0.05, filter_env_amount=1.8,
                     filter_env=Env(0.002, 0.35, 0.1, 0.4), amp_env=Env(0.003, 1.4, 0.15, 0.6), key_tracking=0.6,
                     reverb_mix=0.25, reverb_size=reverb_size * 0.8, level=0.6)
    elif name == "folk":
        keys = Patch("Zither Pluck", "keys", oscs=[Osc("triangle", 0, 0, 0.6), Osc("saw", 1, 3, 0.3), Osc("sine", 0, 0, 0.3)],
                     cutoff=_lerp(2500, 5500, bright), resonance=0.1, filter_env_amount=2.0,
                     filter_env=Env(0.001, 0.25, 0.0, 0.3), amp_env=Env(0.002, 1.1, 0.0, 0.5), key_tracking=0.7,
                     reverb_mix=0.3, reverb_size=reverb_size, delay_time=0.75, delay_feedback=0.2, delay_mix=0.12, level=0.55)
    elif name in ("lofi", "jazz", "neo_soul"):
        keys = Patch("Dusty Rhodes", "keys", oscs=[Osc("sine", 0, 0, 0.8), Osc("triangle", 1, 0, 0.35), Osc("sine", 2, 0, 0.12)],
                     cutoff=_lerp(1200, 2600, bright), resonance=0.1, filter_env_amount=1.2,
                     filter_env=Env(0.002, 0.5, 0.2, 0.5), amp_env=Env(0.004, 1.8, 0.35, 0.7), key_tracking=0.5,
                     lfo_rate=4.2 if name != "lofi" else 0.3, lfo_depth=0.25 if name != "lofi" else 5,
                     lfo_target="amp" if name != "lofi" else "pitch", drive=0.25,
                     reverb_mix=0.28, reverb_size=reverb_size * 0.7, chorus=0.3, level=0.6)
    elif name == "house":
        keys = Patch("Organ Stab", "keys", oscs=[Osc("saw", 0, -6, 0.5), Osc("saw", 0, 6, 0.5), Osc("square", 1, 0, 0.2, 0.3)],
                     cutoff=_lerp(1400, 3600, bright), resonance=0.3, filter_env_amount=1.5,
                     filter_env=Env(0.002, 0.18, 0.0, 0.2), amp_env=Env(0.002, 0.25, 0.0, 0.2),
                     reverb_mix=0.2, reverb_size=1.4, delay_time=0.75, delay_feedback=0.3, delay_mix=0.15, level=0.55)
    elif name == "trance":
        keys = Patch("Crystal Pluck", "keys", oscs=[Osc("saw", 0, -7, 0.5), Osc("saw", 0, 7, 0.5), Osc("square", 1, 0, 0.2)],
                     cutoff=_lerp(1500, 3000, bright), resonance=0.35, filter_env_amount=2.5,
                     filter_env=Env(0.001, 0.12, 0.0, 0.15), amp_env=Env(0.001, 0.2, 0.0, 0.15),
                     reverb_mix=0.3, reverb_size=2.4, delay_time=0.75, delay_feedback=0.4, delay_mix=0.3, level=0.5)
    else:  # synthwave, cinematic, ambient, pop
        keys = Patch("Arp Pluck", "keys", oscs=[Osc("saw", 0, -5, 0.5), Osc("square", 0, 5, 0.4, 0.35), Osc("sine", 1, 0, 0.15)],
                     cutoff=_lerp(1200, 3200, bright), resonance=0.25, filter_env_amount=2.0,
                     filter_env=Env(0.002, 0.22, 0.05, 0.25), amp_env=Env(0.002, 0.45, 0.1, 0.3),
                     reverb_mix=0.3, reverb_size=reverb_size, delay_time=0.75, delay_feedback=0.35, delay_mix=0.25, level=0.5)
    patches["keys"] = keys

    # ---- BASS ----------------------------------------------------------------
    if fam == "classical":
        bass = Patch("Cello Section", "bass", oscs=[Osc("saw", 0, -4, 0.6), Osc("saw", 0, 4, 0.6), Osc("sine", 0, 0, 0.4)],
                     cutoff=_lerp(500, 1200, bright), resonance=0.05, amp_env=Env(0.12, 0.3, 0.85, 0.6),
                     lfo_rate=5.0, lfo_depth=4, lfo_target="pitch", lfo_delay=0.4, reverb_mix=0.2, reverb_size=reverb_size, level=0.6)
    elif name in ("lofi", "neo_soul"):
        bass = Patch("Sub Round", "bass", oscs=[Osc("sine", 0, 0, 0.9), Osc("triangle", 0, 0, 0.3)],
                     cutoff=500, resonance=0.05, amp_env=Env(0.01, 0.4, 0.7, 0.25), drive=0.2, reverb_mix=0.0, level=0.7)
    elif name == "jazz":
        bass = Patch("Upright", "bass", oscs=[Osc("triangle", 0, 0, 0.8), Osc("sine", 0, 0, 0.5), Osc("saw", 0, 0, 0.15)],
                     cutoff=900, resonance=0.05, filter_env_amount=1.0, filter_env=Env(0.002, 0.2, 0.0, 0.2),
                     amp_env=Env(0.005, 0.9, 0.2, 0.15), reverb_mix=0.1, level=0.65)
    elif name == "house":
        bass = Patch("Acid Sub", "bass", oscs=[Osc("saw", 0, 0, 0.7), Osc("sine", 0, 0, 0.5)],
                     cutoff=_lerp(300, 800, ar), resonance=0.45, filter_env_amount=2.0, filter_env=Env(0.001, 0.15, 0.0, 0.15),
                     amp_env=Env(0.002, 0.2, 0.3, 0.1), drive=0.3, level=0.65)
    elif name == "trance":
        bass = Patch("Rolling Saw", "bass", oscs=[Osc("saw", 0, 0, 0.8), Osc("square", 0, 0, 0.3, 0.4), Osc("sine", -1, 0, 0.3)],
                     cutoff=_lerp(400, 900, ar), resonance=0.3, filter_env_amount=1.6, filter_env=Env(0.001, 0.09, 0.0, 0.1),
                     amp_env=Env(0.001, 0.12, 0.4, 0.05), drive=0.2, level=0.6)
    elif name == "ambient":
        bass = Patch("Drone Sub", "bass", oscs=[Osc("sine", 0, 0, 0.8), Osc("triangle", 1, 3, 0.2)],
                     cutoff=400, resonance=0.0, amp_env=Env(2.0, 1.0, 0.9, 3.0), reverb_mix=0.2, reverb_size=reverb_size, level=0.55)
    else:  # synthwave, cinematic, pop
        bass = Patch("Analog Bass", "bass", oscs=[Osc("square", 0, 0, 0.6, 0.45), Osc("saw", 0, 0, 0.5), Osc("sine", -1, 0, 0.3)],
                     cutoff=_lerp(500, 1300, ar), resonance=0.25, filter_env_amount=1.4, filter_env=Env(0.002, 0.18, 0.0, 0.2),
                     amp_env=Env(0.002, 0.3, 0.6, 0.12), drive=0.15, level=0.65)
    patches["bass"] = bass

    # ---- LEAD ----------------------------------------------------------------
    vib_rate = _lerp(4.6, 6.2, ar)
    if fam == "classical" and name != "folk":
        lead = Patch("Oboe d'Amore" if warm > 0.5 else "Silver Flute", "lead",
                     oscs=[Osc("triangle", 0, 0, 0.6), Osc("saw" if warm > 0.5 else "sine", 0, 0, 0.45), Osc("sine", 1, 0, 0.15)],
                     cutoff=_lerp(1800, 3800, bright), resonance=0.1, noise=0.03,
                     amp_env=Env(_lerp(0.12, 0.03, ar), 0.2, 0.85, 0.35), filter_env_amount=0.3, filter_env=Env(0.1, 0.3, 0.7, 0.3),
                     lfo_rate=vib_rate, lfo_depth=12, lfo_target="pitch", lfo_delay=0.35,
                     reverb_mix=0.3, reverb_size=reverb_size, level=0.7)
    elif name == "folk":
        lead = Patch("Bamboo Flute", "lead", oscs=[Osc("sine", 0, 0, 0.7), Osc("triangle", 0, 0, 0.35), Osc("sine", 2, 0, 0.06)],
                     cutoff=_lerp(2200, 4500, bright), resonance=0.12, noise=0.06,
                     amp_env=Env(0.06, 0.15, 0.85, 0.3), lfo_rate=vib_rate, lfo_depth=18, lfo_target="pitch", lfo_delay=0.3,
                     glide=0.03, reverb_mix=0.35, reverb_size=reverb_size, level=0.7)
    elif name in ("synthwave", "trance"):
        lead = Patch("Retro Lead" if name == "synthwave" else "Anthem Supersaw", "lead",
                     oscs=[Osc("saw", 0, 0, 0.6), Osc("square", 0, -7, 0.4, 0.35), Osc("saw", 1, 5, 0.25)],
                     unison=5 if name == "trance" else 2, unison_detune=_lerp(10, 22, ten),
                     cutoff=lead_cut, resonance=0.2, filter_env_amount=1.0, filter_env=Env(0.01, 0.4, 0.5, 0.3),
                     amp_env=Env(0.01, 0.2, 0.8, 0.3), lfo_rate=vib_rate, lfo_depth=10, lfo_target="pitch", lfo_delay=0.25,
                     glide=0.04, drive=0.2, reverb_mix=0.3, reverb_size=reverb_size,
                     # Echoes of a fast sung line smear against the next chord, so the
                     # dotted-eighth delay backs off as the text gets denser.
                     delay_time=0.75, delay_feedback=0.3, delay_mix=_lerp(0.3, 0.12, ar), level=0.6)
    elif name in ("lofi", "neo_soul", "jazz"):
        lead = Patch("Muted Horn" if name == "jazz" else "Soft Square", "lead",
                     oscs=[Osc("square", 0, 0, 0.5, 0.3), Osc("triangle", 0, 0, 0.5), Osc("sine", -1, 0, 0.2)],
                     cutoff=_lerp(1100, 2600, bright), resonance=0.15, filter_env_amount=0.6, filter_env=Env(0.03, 0.3, 0.5, 0.3),
                     amp_env=Env(0.03, 0.3, 0.75, 0.35), lfo_rate=vib_rate * 0.9, lfo_depth=9, lfo_target="pitch", lfo_delay=0.3,
                     glide=0.05, drive=0.2, reverb_mix=0.25, reverb_size=reverb_size * 0.8, delay_time=1.0 if name == "lofi" else 0,
                     delay_feedback=0.25, delay_mix=0.15 if name == "lofi" else 0, level=0.65)
    elif name == "ambient":
        lead = Patch("Distant Voice", "lead", oscs=[Osc("sine", 0, 0, 0.8), Osc("triangle", 0, 4, 0.3), Osc("sine", 1, 0, 0.1)],
                     cutoff=_lerp(1200, 2600, bright), resonance=0.1, amp_env=Env(0.4, 0.5, 0.8, 1.5),
                     lfo_rate=4.5, lfo_depth=8, lfo_target="pitch", lfo_delay=0.6, glide=0.08,
                     reverb_mix=0.5, reverb_size=reverb_size + 1.5, delay_time=1.5, delay_feedback=0.5, delay_mix=0.35, level=0.6)
    else:  # house, pop, cinematic
        lead = Patch("Glass Lead", "lead", oscs=[Osc("saw", 0, -4, 0.5), Osc("triangle", 0, 4, 0.5), Osc("sine", 1, 0, 0.2)],
                     cutoff=lead_cut * 0.8, resonance=0.15, filter_env_amount=0.8, filter_env=Env(0.02, 0.3, 0.5, 0.3),
                     amp_env=Env(0.02, 0.25, 0.8, 0.35), lfo_rate=vib_rate, lfo_depth=9, lfo_target="pitch", lfo_delay=0.3,
                     glide=0.03, reverb_mix=0.3, reverb_size=reverb_size, delay_time=0.5, delay_feedback=0.3, delay_mix=0.2, level=0.65)
    patches["lead"] = lead

    for p in patches.values():
        for attr in ("cutoff", "resonance", "filter_env_amount", "unison_detune", "reverb_size", "reverb_mix", "lfo_rate", "lfo_depth"):
            setattr(p, attr, round(getattr(p, attr), 3))
        for env in (p.filter_env, p.amp_env):
            env.attack, env.decay, env.sustain, env.release = (round(env.attack, 3), round(env.decay, 3),
                                                               round(env.sustain, 3), round(env.release, 3))
        for o in p.oscs:
            o.detune = round(o.detune, 2)
        p.recipe = _recipe(p)
    return patches
