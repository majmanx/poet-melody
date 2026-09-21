"""Style definitions: how each genre turns text affect into tempo, mode,
harmony options, arrangement patterns and drums.

A *style* is the "production aesthetic". The text decides the style when
``style="auto"`` (see :func:`choose_style`), or the caller forces one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .analysis import TextFeatures
from .progressions import HarmonyOptions


@dataclass(frozen=True)
class Style:
    name: str
    family: str                           # "classical" | "electronic" | "hybrid"
    tempo_range: Tuple[int, int]
    major_modes: Sequence[str]            # preferred modes for positive texts
    minor_modes: Sequence[str]            # preferred modes for negative texts
    melody_scale: str = "mode"            # "mode" | "pentatonic" | "blues"
    time_signatures: Sequence[Tuple[int, int]] = ((4, 4),)
    swing: float = 0.5                    # 0.5 = straight, ~0.62 = swung 8ths
    bars_per_chord: int = 1
    harmony: HarmonyOptions = field(default_factory=HarmonyOptions)
    library_ratio: float = 0.6            # chance to use a library progression vs. generated
    pad: str = "sustain"                  # sustain | swell | stab | none
    keys: str = "none"                    # none | arpeggio_up | arpeggio_updown | alberti | broken | comp | stab_offbeat | pluck16
    bass: str = "root_whole"              # root_whole | root_fifth | octaves8 | offbeat8 | rolling16 | walking | drone | root_13
    drums: str = "none"                   # none | four_floor | trance | lofi | backbeat
    sidechain: float = 0.0
    lead_octave_shift: int = 0
    ritardando: bool = False
    humanize: float = 0.0                 # timing jitter in beats
    description: str = ""


STYLES: Dict[str, Style] = {
    "classical": Style(
        "classical", "classical", (66, 100), ("ionian", "lydian"), ("aeolian", "harmonic_minor"),
        time_signatures=((4, 4), (3, 4)), harmony=HarmonyOptions(sevenths=0.15, secondary=0.25, mixture=0.1, cadence="authentic"),
        library_ratio=0.65, pad="swell", keys="alberti", bass="root_fifth", drums="none", ritardando=True, humanize=0.02,
        description="Common-practice harmony, Alberti / broken-chord piano figures, string swells, ritardando at the end.",
    ),
    "romantic": Style(
        "romantic", "classical", (56, 88), ("ionian", "lydian"), ("aeolian", "harmonic_minor"),
        time_signatures=((4, 4), (3, 4)), harmony=HarmonyOptions(sevenths=0.35, mixture=0.45, mediants=0.35, secondary=0.3, cadence="deceptive"),
        library_ratio=0.55, pad="swell", keys="broken", bass="root_fifth", drums="none", ritardando=True, humanize=0.03,
        description="Chromatic mediants, modal mixture, deceptive cadences, rubato feel.",
    ),
    "folk": Style(
        "folk", "classical", (72, 104), ("ionian", "mixolydian"), ("aeolian", "dorian"), melody_scale="pentatonic",
        time_signatures=((4, 4), (3, 4)), harmony=HarmonyOptions(sevenths=0.0, sus=0.3, cadence="plagal"),
        library_ratio=0.8, pad="sustain", keys="broken", bass="root_fifth", drums="none", ritardando=True, humanize=0.02,
        description="Pentatonic (宫/羽) melodies over simple triads and sus chords; plagal cadences.",
    ),
    "jazz": Style(
        "jazz", "hybrid", (88, 150), ("ionian", "lydian"), ("dorian", "aeolian"), melody_scale="mode",
        swing=0.64, harmony=HarmonyOptions(sevenths=0.95, extensions=0.5, secondary=0.35, tritone=0.35, cadence="authentic"),
        library_ratio=0.5, pad="none", keys="comp", bass="walking", drums="none", humanize=0.03,
        description="ii-V-I, extended chords, tritone substitutions, walking bass, swung eighths.",
    ),
    "neo_soul": Style(
        "neo_soul", "hybrid", (68, 92), ("ionian", "lydian"), ("dorian", "aeolian"),
        swing=0.58, harmony=HarmonyOptions(sevenths=1.0, extensions=0.8, mixture=0.3, cadence="plagal"),
        library_ratio=0.7, pad="sustain", keys="comp", bass="root_13", drums="lofi", humanize=0.04,
        description="Lush 9th/13th voicings, borrowed iv and bVII, laid-back drums.",
    ),
    "lofi": Style(
        "lofi", "electronic", (68, 86), ("ionian", "lydian"), ("dorian", "aeolian"),
        swing=0.6, harmony=HarmonyOptions(sevenths=0.95, extensions=0.6, mixture=0.25, cadence="plagal"),
        library_ratio=0.7, pad="sustain", keys="stab_offbeat", bass="root_13", drums="lofi", humanize=0.05,
        description="Warm detuned keys, seventh chords, swung lo-fi drums, tape wobble.",
    ),
    "pop": Style(
        "pop", "hybrid", (92, 128), ("ionian", "mixolydian"), ("aeolian",),
        harmony=HarmonyOptions(sevenths=0.1, cadence="none"), library_ratio=0.85,
        pad="sustain", keys="broken", bass="octaves8", drums="four_floor", sidechain=0.25,
        description="Four-chord loops (I-V-vi-IV and friends), steady pulse.",
    ),
    "synthwave": Style(
        "synthwave", "electronic", (84, 118), ("ionian",), ("aeolian",),
        harmony=HarmonyOptions(sevenths=0.05, sus=0.25, cadence="none"), library_ratio=0.85,
        pad="sustain", keys="arpeggio_up", bass="octaves8", drums="backbeat", sidechain=0.5,
        description="Aeolian i-VI-III-VII loops, supersaw pads, octave bass, gated-reverb drums.",
    ),
    "house": Style(
        "house", "electronic", (118, 126), ("ionian",), ("aeolian", "dorian"),
        swing=0.54, harmony=HarmonyOptions(sevenths=0.5, extensions=0.2, cadence="none"), library_ratio=0.8,
        pad="stab", keys="stab_offbeat", bass="offbeat8", drums="four_floor", sidechain=0.6,
        description="Dorian / aeolian two-chord vamps, off-beat bass, four-on-the-floor.",
    ),
    "trance": Style(
        "trance", "electronic", (132, 140), ("ionian",), ("aeolian",),
        harmony=HarmonyOptions(sevenths=0.0, cadence="none"), library_ratio=0.85,
        pad="sustain", keys="pluck16", bass="rolling16", drums="trance", sidechain=0.7, lead_octave_shift=0,
        description="Uplifting aeolian loops, rolling 16th bass, supersaw leads.",
    ),
    "ambient": Style(
        "ambient", "electronic", (56, 72), ("lydian", "ionian"), ("dorian", "aeolian"),
        bars_per_chord=2, harmony=HarmonyOptions(sevenths=0.9, extensions=0.5, sus=0.4, cadence="plagal"), library_ratio=0.7,
        pad="swell", keys="arpeggio_updown", bass="drone", drums="none", ritardando=True,
        description="Slow lydian / dorian colour, long swells, drones, lots of reverb.",
    ),
    "cinematic": Style(
        "cinematic", "hybrid", (60, 96), ("lydian", "ionian"), ("aeolian", "phrygian"),
        harmony=HarmonyOptions(sevenths=0.2, mixture=0.4, mediants=0.3, cadence="half"), library_ratio=0.6,
        pad="swell", keys="arpeggio_up", bass="octaves8", drums="none", ritardando=True,
        description="Phrygian bII, chromatic mediants, ostinato arpeggios, half cadences.",
    ),
}


def style_names() -> List[str]:
    return list(STYLES)


def choose_style(f: TextFeatures) -> str:
    """Pick a style from text affect. Returns the style name."""
    scores: Dict[str, float] = {}
    e, c = f.electronic, f.classical
    scores["classical"] = 1.0 * c + 0.3 * (1 - f.arousal) + (0.3 if f.language == "en" else 0.0) - 0.8 * e
    scores["folk"] = 1.1 * c + 0.2 * (1 - f.arousal) + (0.4 if f.language == "zh" else 0.0) - 0.8 * e + 0.2 * f.valence
    scores["romantic"] = 0.7 * c + 0.5 * f.tension + 0.3 * (1 - abs(f.valence)) - 0.6 * e
    scores["jazz"] = 0.3 + 0.5 * f.irregularity + 0.3 * f.arousal + 0.2 * f.tension - 0.3 * c
    scores["neo_soul"] = 0.35 + 0.5 * f.warmth + 0.2 * (1 - f.arousal) - 0.4 * c
    scores["lofi"] = 0.45 + 0.5 * f.warmth + 0.4 * (1 - f.arousal) + 0.3 * e - 0.4 * c
    scores["pop"] = 0.3 + 0.5 * f.valence + 0.3 * f.arousal
    scores["synthwave"] = 0.2 + 1.0 * e + 0.3 * f.arousal - 0.3 * f.valence
    scores["house"] = 0.9 * e + 0.8 * f.arousal - 0.3
    scores["trance"] = 0.8 * e + 1.0 * f.arousal - 0.5
    scores["ambient"] = 0.3 + 0.9 * (1 - f.arousal) + 0.3 * f.tension - 0.2 * e
    scores["cinematic"] = 0.2 + 0.6 * f.tension + 0.4 * abs(f.valence) - 0.2 * f.valence + 0.3 * f.arousal
    return max(scores, key=scores.get)
