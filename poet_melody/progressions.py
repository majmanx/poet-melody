"""Chord progression library and a functional-harmony generator.

Progressions are written as Roman numerals *relative to the mode they are
tagged with* (see :func:`poet_melody.theory.parse_roman`). Upper case = major
triad, lower case = minor triad, suffixes add sevenths/extensions.

Two sources of harmony are available:

* :data:`LIBRARY` – curated progressions from classical practice (cadences,
  Pachelbel, the Andalusian and circle-of-fifths progressions), jazz
  (ii–V–I, tritone substitutions), pop, lo-fi, neo-soul and the loops that
  define synthwave, house, trance and ambient music.
* :func:`generate_functional` – builds *new* progressions from
  tonic/subdominant/dominant function grammar, with optional modal mixture,
  chromatic mediants, secondary dominants and tritone substitutions.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .theory import Chord, is_major_like, parse_roman


@dataclass(frozen=True)
class Progression:
    name: str
    style: str
    mode: str                     # the mode the numerals are written in
    numerals: Sequence[str]
    tags: Sequence[str] = ()      # "bright", "dark", "tense", "resolved", "cadence", ...
    weight: float = 1.0

    def chords(self, tonic: int, mode: Optional[str] = None) -> List[Chord]:
        return [parse_roman(n, tonic, mode or self.mode) for n in self.numerals]


def _p(name, style, mode, numerals, tags=(), weight=1.0):
    return Progression(name, style, mode, tuple(numerals.split()), tuple(tags), weight)


LIBRARY: List[Progression] = [
    # ---- Classical / common practice ------------------------------------
    _p("authentic cadence", "classical", "ionian", "I IV V I", ("bright", "resolved", "cadence")),
    _p("I vi IV V (50s)", "classical", "ionian", "I vi IV V", ("bright",)),
    _p("Pachelbel canon", "classical", "ionian", "I V vi iii IV I IV V", ("bright", "flowing"), 1.4),
    _p("ii V I", "classical", "ionian", "I ii V7 I", ("bright", "resolved")),
    _p("plagal", "classical", "ionian", "I IV I V", ("bright", "hymn")),
    _p("circle of fifths (major)", "classical", "ionian", "I IV vii° iii vi ii V I", ("flowing", "baroque"), 1.2),
    _p("deceptive", "classical", "ionian", "I IV V vi", ("tense", "bittersweet")),
    _p("half cadence", "classical", "ionian", "I vi ii V", ("tense", "open")),
    _p("minor authentic", "classical", "aeolian", "i iv V i", ("dark", "resolved", "cadence")),
    _p("Andalusian", "classical", "aeolian", "i VII VI V", ("dark", "tense", "spanish"), 1.2),
    _p("lament bass", "classical", "aeolian", "i V VI V", ("dark", "grief")),
    _p("circle of fifths (minor)", "classical", "aeolian", "i iv VII III VI ii° V i", ("dark", "flowing", "baroque"), 1.2),
    _p("minor i VI III VII", "classical", "aeolian", "i VI III VII", ("dark", "epic")),
    _p("Picardy", "classical", "aeolian", "i iv V I", ("dark", "resolved", "hope")),
    # ---- Romantic / chromatic ------------------------------------------
    _p("chromatic mediant", "romantic", "ionian", "I III IV iv", ("bittersweet", "colour"), 1.2),
    _p("borrowed bVI bVII", "romantic", "ionian", "I bVI bVII I", ("epic", "colour")),
    _p("minor iv", "romantic", "ionian", "I IV iv I", ("bittersweet",)),
    _p("Neapolitan", "romantic", "aeolian", "i bII V i", ("dark", "tense", "colour")),
    _p("romantic minor", "romantic", "aeolian", "i VI iv V", ("dark", "longing")),
    _p("major to relative minor", "romantic", "ionian", "I V vi IV iv I", ("bittersweet",)),
    # ---- Jazz ---------------------------------------------------------
    _p("ii V I", "jazz", "ionian", "ii7 V7 Imaj7 Imaj7", ("resolved",), 1.3),
    _p("I vi ii V", "jazz", "ionian", "Imaj7 vi7 ii7 V7", ("flowing",), 1.2),
    _p("iii VI ii V", "jazz", "ionian", "iii7 VI7 ii7 V7", ("flowing", "colour")),
    _p("tritone sub", "jazz", "ionian", "ii7 bII7 Imaj7 Imaj7", ("colour", "tense")),
    _p("backdoor", "jazz", "ionian", "Imaj7 iv7 bVII7 Imaj7", ("bittersweet", "colour")),
    _p("minor ii V i", "jazz", "aeolian", "iiø7 V7 i7 i7", ("dark", "resolved"), 1.2),
    _p("minor blues turn", "jazz", "aeolian", "i7 iv7 VII7 IIImaj7", ("dark", "flowing")),
    _p("Coltrane-ish mediants", "jazz", "ionian", "Imaj7 bIII7 bVImaj7 bII7", ("colour", "tense")),
    # ---- Neo-soul / R&B -----------------------------------------------
    _p("neo I iii vi ii", "neo_soul", "ionian", "Imaj9 iii7 vi9 ii9", ("bright", "smooth"), 1.2),
    _p("neo ii V I bIII", "neo_soul", "ionian", "ii9 V13 Imaj9 bIIImaj7", ("smooth", "colour")),
    _p("neo iv bVII", "neo_soul", "ionian", "iv9 bVIImaj7 Imaj9 Imaj9", ("bittersweet", "smooth")),
    _p("neo IV iii", "neo_soul", "ionian", "IVmaj9 iii7 vi9 V9", ("bright", "smooth")),
    _p("neo minor", "neo_soul", "aeolian", "i9 iv9 VImaj7 V7", ("dark", "smooth")),
    # ---- Pop ----------------------------------------------------------
    _p("axis I V vi IV", "pop", "ionian", "I V vi IV", ("bright",), 1.4),
    _p("vi IV I V", "pop", "ionian", "vi IV I V", ("bittersweet",), 1.2),
    _p("I vi IV V", "pop", "ionian", "I vi IV V", ("bright",)),
    _p("I IV vi V", "pop", "ionian", "I IV vi V", ("bright",)),
    _p("IV I V vi", "pop", "ionian", "IV I V vi", ("bittersweet",)),
    _p("pop minor", "pop", "aeolian", "i VI III VII", ("dark",), 1.2),
    _p("pop minor VI VII", "pop", "aeolian", "VI VII i i", ("dark", "epic")),
    # ---- Lo-fi ---------------------------------------------------------
    _p("lofi ii V I vi", "lofi", "ionian", "ii7 V7 Imaj7 vi7", ("smooth",), 1.3),
    _p("lofi I IV iii vi", "lofi", "ionian", "Imaj9 IVmaj9 iii7 vi9", ("bright", "smooth"), 1.2),
    _p("lofi iv bVII", "lofi", "ionian", "iv7 bVII7 Imaj7 Imaj7", ("bittersweet",)),
    _p("lofi vi ii I V", "lofi", "ionian", "vi9 ii9 Imaj9 V9", ("smooth",)),
    _p("lofi minor", "lofi", "aeolian", "i7 iv7 VImaj7 V7", ("dark", "smooth")),
    _p("lofi dorian", "lofi", "dorian", "i7 IV7 i7 IV7", ("modal", "smooth")),
    # ---- Synthwave ------------------------------------------------------
    _p("synthwave i VI III VII", "synthwave", "aeolian", "i VI III VII", ("dark", "epic"), 1.4),
    _p("synthwave VI VII i", "synthwave", "aeolian", "VI VII i i", ("dark", "epic"), 1.2),
    _p("synthwave i VII VI VII", "synthwave", "aeolian", "i VII VI VII", ("dark", "driving"), 1.2),
    _p("synthwave i III VII VI", "synthwave", "aeolian", "i III VII VI", ("dark",)),
    _p("synthwave VI IV i V", "synthwave", "aeolian", "VI iv i V", ("dark", "tense")),
    _p("synthwave major", "synthwave", "ionian", "I V vi IV", ("bright", "nostalgic")),
    _p("synthwave sus", "synthwave", "aeolian", "i VIsus2 III VIIsus2", ("dark", "airy")),
    # ---- House / techno ------------------------------------------------
    _p("house i VII VI VII", "house", "aeolian", "i VII VI VII", ("driving",), 1.3),
    _p("house i VI VII", "house", "aeolian", "i i VI VII", ("driving",)),
    _p("house dorian", "house", "dorian", "i IV i IV", ("modal", "driving"), 1.2),
    _p("house dorian 7ths", "house", "dorian", "i7 IV7 i7 VII", ("modal", "smooth")),
    _p("house deep", "house", "aeolian", "i7 iv7 i7 VImaj7", ("smooth", "deep")),
    _p("house major", "house", "ionian", "Imaj7 vi7 IVmaj7 V7", ("bright", "smooth")),
    # ---- Trance ---------------------------------------------------------
    _p("trance i VI VII", "trance", "aeolian", "i VI VII VII", ("epic", "driving"), 1.3),
    _p("trance i VI III VII", "trance", "aeolian", "i VI III VII", ("epic",), 1.2),
    _p("trance VI VII i III", "trance", "aeolian", "VI VII i III", ("epic", "uplifting")),
    _p("trance i VII VI", "trance", "aeolian", "i VII VI VI", ("driving",)),
    _p("trance i iv VI V", "trance", "aeolian", "i iv VI V", ("tense", "epic")),
    # ---- Ambient --------------------------------------------------------
    _p("ambient I IV", "ambient", "ionian", "Imaj7 IVmaj7 Imaj7 IVmaj7", ("bright", "still"), 1.3),
    _p("ambient sus", "ambient", "ionian", "Isus2 Isus4 Iadd9 Isus2", ("still", "airy")),
    _p("ambient lydian", "ambient", "lydian", "Imaj7#11 II Imaj7#11 II", ("wonder", "airy"), 1.2),
    _p("ambient I iii IV", "ambient", "ionian", "Imaj7 iii7 IVmaj7 Imaj7", ("bright", "still")),
    _p("ambient minor", "ambient", "aeolian", "i9 VImaj7 i9 iv9", ("dark", "still"), 1.2),
    _p("ambient dorian", "ambient", "dorian", "i7 IV i7 IV", ("modal", "still")),
    # ---- Cinematic ------------------------------------------------------
    _p("cinematic phrygian", "cinematic", "aeolian", "i bII i VII", ("dark", "tense"), 1.2),
    _p("cinematic i VI iv V", "cinematic", "aeolian", "i VI iv V", ("dark", "epic")),
    _p("cinematic VI VII i", "cinematic", "aeolian", "VI VII i i", ("epic",), 1.2),
    _p("cinematic i III iv VII", "cinematic", "aeolian", "i III iv VII", ("dark",)),
    _p("cinematic major", "cinematic", "ionian", "I bVI IV I", ("epic", "colour")),
    _p("cinematic lydian", "cinematic", "lydian", "I II I II", ("wonder", "bright")),
    # ---- Folk / pentatonic (Chinese 民乐 colour) -------------------------
    _p("folk I vi IV I", "folk", "ionian", "I vi IV I", ("bright", "simple"), 1.2),
    _p("folk I IV I V", "folk", "ionian", "I IV I V", ("bright", "simple")),
    _p("folk vi I IV vi", "folk", "ionian", "vi I IV vi", ("bittersweet", "simple")),
    _p("folk I ii vi V", "folk", "ionian", "I ii vi V", ("bright",)),
    _p("folk minor i VII", "folk", "aeolian", "i VII i VI", ("dark", "simple"), 1.2),
    _p("folk minor i III VII i", "folk", "aeolian", "i III VII i", ("dark", "simple")),
    _p("folk sus", "folk", "ionian", "Isus2 I IVadd9 Isus2", ("airy", "simple")),
]


def library_for(style: str, mode: Optional[str] = None) -> List[Progression]:
    out = [p for p in LIBRARY if p.style == style]
    if mode is not None:
        want_major = is_major_like(mode)
        out = [p for p in out if is_major_like(p.mode) == want_major]
    return out


def all_styles() -> List[str]:
    seen: List[str] = []
    for p in LIBRARY:
        if p.style not in seen:
            seen.append(p.style)
    return seen


def pick_progression(style: str, mode: str, rng: random.Random, tags: Sequence[str] = (),
                     exclude: Sequence[str] = ()) -> Progression:
    """Weighted random choice of a library progression matching style and mode
    family, boosted by mood ``tags`` (e.g. ``["tense"]`` for questioning texts)."""
    pool = [p for p in library_for(style, mode) if p.name not in exclude]
    if not pool:
        pool = library_for(style) or LIBRARY
    weights = []
    for p in pool:
        w = p.weight
        for t in tags:
            if t in p.tags:
                w *= 1.8
        weights.append(w)
    return rng.choices(pool, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Functional harmony generator
# ---------------------------------------------------------------------------
# Function vocabulary per mode family. "T" tonic, "S" subdominant (pre-dominant),
# "D" dominant. Numerals are relative to ionian / aeolian.
_FUNCTIONS: Dict[str, Dict[str, List[str]]] = {
    "major": {
        "T": ["I", "I", "vi", "iii"],
        "S": ["IV", "ii", "IV", "ii"],
        "D": ["V", "V7", "vii°"],
    },
    "minor": {
        "T": ["i", "i", "III", "VI"],
        "S": ["iv", "ii°", "VI", "iv"],
        "D": ["V", "V7", "VII"],
    },
}
# Colour substitutions used by the "modern"/romantic dials.
_MIXTURE = {"major": {"S": ["iv", "bVI", "bVII", "ii°"], "T": ["bIII", "bVI"]},
            "minor": {"S": ["IV", "ii"], "T": ["I"], "D": ["v"]}}
_MEDIANTS = {"major": ["III", "bIII", "bVI", "VI"], "minor": ["III", "VI", "I", "bII"]}

_TRANSITIONS = {
    "T": [("S", 0.5), ("D", 0.3), ("T", 0.2)],
    "S": [("D", 0.6), ("T", 0.25), ("S", 0.15)],
    "D": [("T", 0.75), ("S", 0.1), ("D", 0.15)],
}


@dataclass
class HarmonyOptions:
    length: int = 4
    sevenths: float = 0.0          # probability that a triad becomes a seventh chord
    extensions: float = 0.0        # probability of 9ths on sevenths
    mixture: float = 0.0           # modal mixture (borrowed chords)
    mediants: float = 0.0          # chromatic mediant substitutions
    secondary: float = 0.0         # secondary dominants before S/T chords
    tritone: float = 0.0           # tritone substitution of V7
    cadence: str = "authentic"     # authentic | plagal | deceptive | half | picardy | none
    sus: float = 0.0               # sus2/sus4 colour on tonic chords


def _add_seventh(numeral: str, family: str, rng: random.Random, opts: HarmonyOptions) -> str:
    if any(ch in numeral for ch in "7°ø+") or "sus" in numeral:
        return numeral
    if rng.random() >= opts.sevenths:
        return numeral
    deg = numeral.lstrip("b#")
    upper = deg[0].isupper()
    ext = rng.random() < opts.extensions
    if numeral == "V":
        return "V9" if ext else "V7"
    if upper:
        if numeral in ("VII", "bVII") and family == "major":
            return numeral + "7"          # borrowed bVII works as a dominant-type chord
        return numeral + ("maj9" if ext else "maj7")
    return numeral + ("9" if ext else "7")


def generate_functional(mode: str, rng: random.Random, opts: Optional[HarmonyOptions] = None) -> List[str]:
    """Generate a Roman numeral progression from harmonic-function grammar."""
    opts = opts or HarmonyOptions()
    family = "major" if is_major_like(mode) else "minor"
    funcs = _FUNCTIONS[family]
    n = max(2, opts.length)
    states: List[str] = ["T"]
    while len(states) < n:
        cur = states[-1]
        nxt = rng.choices([s for s, _ in _TRANSITIONS[cur]], weights=[w for _, w in _TRANSITIONS[cur]])[0]
        states.append(nxt)
    # Force the ending according to the requested cadence.
    if n >= 2:
        if opts.cadence == "authentic":
            states[-2:] = ["D", "T"]
        elif opts.cadence == "plagal":
            states[-2:] = ["S", "T"]
        elif opts.cadence == "deceptive":
            states[-2:] = ["D", "T"]
        elif opts.cadence == "half":
            states[-2:] = ["S", "D"] if n >= 3 else ["T", "D"]
        elif opts.cadence == "picardy":
            states[-2:] = ["D", "T"]
    numerals: List[str] = []
    for i, st in enumerate(states):
        choices = list(funcs[st])
        if rng.random() < opts.mixture and st in _MIXTURE[family]:
            choices = _MIXTURE[family][st]
        numeral = rng.choice(choices)
        if numerals and len(set(choices)) > 1:
            tries = 0
            while numeral == numerals[-1] and tries < 6:      # avoid static repeats
                numeral = rng.choice(choices)
                tries += 1
        if i == 0:
            numeral = "I" if family == "major" else "i"   # start on the tonic
        if st == "T" and i not in (0,) and rng.random() < opts.mediants:
            numeral = rng.choice(_MEDIANTS[family])
        numerals.append(numeral)
    # Cadence specifics.
    tonic = "I" if family == "major" else "i"
    if opts.cadence == "deceptive":
        numerals[-1] = "vi" if family == "major" else "VI"
    elif opts.cadence == "picardy":
        numerals[-1] = "I"
    elif opts.cadence in ("authentic", "plagal"):
        numerals[-1] = tonic
    if opts.cadence in ("authentic", "deceptive", "picardy", "half"):
        # A real dominant with a leading tone in both families.
        dom_index = -1 if opts.cadence == "half" else -2
        if numerals[dom_index] in ("VII", "vii°", "v", "bVII"):
            numerals[dom_index] = "V"
    # Secondary dominants: insert V7/x before a diatonic S or T chord (not the tonic).
    if opts.secondary > 0 and n >= 4:
        out: List[str] = []
        for i, numeral in enumerate(numerals):
            if (i > 1 and numeral in ("ii", "IV", "vi", "iii", "iv", "VI", "III")
                    and rng.random() < opts.secondary and len(out) and out[-1] != f"V7/{numeral}"):
                out[-1] = f"V7/{numeral}"
            out.append(numeral)
        numerals = out
    # Sevenths and extensions (a Picardy third stays a plain major triad).
    numerals = [_add_seventh(x, family, rng, opts) if not (opts.cadence == "picardy" and i == len(numerals) - 1) else x
                for i, x in enumerate(numerals)]
    # Tritone substitution of a dominant seventh that resolves to the tonic.
    if opts.tritone > 0:
        for i in range(len(numerals) - 1):
            if numerals[i] in ("V7", "V9") and numerals[i + 1].startswith(("I", "i")) and rng.random() < opts.tritone:
                numerals[i] = "bII7"
    # Sus colour on tonic chords (not the final one).
    if opts.sus > 0:
        for i in range(len(numerals) - 1):
            if numerals[i] in ("I", "i") and rng.random() < opts.sus:
                numerals[i] = "Isus2" if family == "major" else "isus2"
    return numerals
