"""Music theory primitives: pitch classes, scales/modes, chords, Roman numerals
and voice leading.

Everything here is pure Python and deterministic. Pitches are MIDI numbers
(60 = C4); pitch classes are integers 0..11 (0 = C).
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Keys conventionally spelled with flats.
FLAT_KEYS = {5, 10, 3, 8, 1}  # F, Bb, Eb, Ab, Db

NOTE_TO_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "Fb": 4, "E#": 5,
    "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11, "B#": 0,
}

# ---------------------------------------------------------------------------
# Scales and modes
# ---------------------------------------------------------------------------
SCALES = {
    # Church modes (classical / modal harmony)
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    # Minor-scale family (common-practice)
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "phrygian_dominant": [0, 1, 4, 5, 7, 8, 10],
    "lydian_dominant": [0, 2, 4, 6, 7, 9, 10],
    # Pentatonic / world (Chinese 宫商角徵羽 are the five modes of the anhemitonic pentatonic)
    "major_pentatonic": [0, 2, 4, 7, 9],   # 宫 gong
    "shang": [0, 2, 5, 7, 10],             # 商
    "jue": [0, 3, 5, 8, 10],               # 角
    "zhi": [0, 2, 5, 7, 9],                # 徵
    "minor_pentatonic": [0, 3, 5, 7, 10],  # 羽 yu
    "hirajoshi": [0, 2, 3, 7, 8],
    "in_sen": [0, 1, 5, 7, 10],
    # Symmetric / modern
    "blues": [0, 3, 5, 6, 7, 10],
    "whole_tone": [0, 2, 4, 6, 8, 10],
    "octatonic": [0, 2, 3, 5, 6, 8, 9, 11],
    "chromatic": list(range(12)),
}
SCALES["major"] = SCALES["ionian"]
SCALES["minor"] = SCALES["aeolian"]
SCALES["gong"] = SCALES["major_pentatonic"]
SCALES["yu"] = SCALES["minor_pentatonic"]

# Modes that behave as "major-ish" (major third above tonic) vs "minor-ish".
MAJOR_LIKE = {"ionian", "major", "lydian", "mixolydian", "lydian_dominant", "major_pentatonic",
              "gong", "zhi", "whole_tone", "phrygian_dominant"}
MINOR_LIKE = {"aeolian", "minor", "dorian", "phrygian", "locrian", "harmonic_minor",
              "melodic_minor", "minor_pentatonic", "yu", "shang", "jue", "hirajoshi",
              "in_sen", "blues", "octatonic"}

# ---------------------------------------------------------------------------
# Chord qualities (intervals in semitones from the root)
# ---------------------------------------------------------------------------
CHORD_QUALITIES = {
    "maj": [0, 4, 7],
    "min": [0, 3, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
    "power": [0, 7],
    "6": [0, 4, 7, 9],
    "m6": [0, 3, 7, 9],
    "69": [0, 4, 7, 9, 14],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "7": [0, 4, 7, 10],
    "dim7": [0, 3, 6, 9],
    "m7b5": [0, 3, 6, 10],
    "minmaj7": [0, 3, 7, 11],
    "aug7": [0, 4, 8, 10],
    "augmaj7": [0, 4, 8, 11],
    "7sus4": [0, 5, 7, 10],
    "add9": [0, 4, 7, 14],
    "madd9": [0, 3, 7, 14],
    "maj9": [0, 4, 7, 11, 14],
    "min9": [0, 3, 7, 10, 14],
    "9": [0, 4, 7, 10, 14],
    "7b9": [0, 4, 7, 10, 13],
    "7#9": [0, 4, 7, 10, 15],
    "min11": [0, 3, 7, 10, 14, 17],
    "11": [0, 4, 7, 10, 14, 17],
    "maj7#11": [0, 4, 7, 11, 18],
    "13": [0, 4, 7, 10, 14, 21],
    "maj13": [0, 4, 7, 11, 14, 21],
    "min13": [0, 3, 7, 10, 14, 21],
}

# Display suffix for chord symbols.
QUALITY_SYMBOL = {
    "maj": "", "min": "m", "dim": "dim", "aug": "aug", "sus2": "sus2", "sus4": "sus4",
    "power": "5", "6": "6", "m6": "m6", "69": "6/9", "maj7": "maj7", "min7": "m7", "7": "7",
    "dim7": "dim7", "m7b5": "m7b5", "minmaj7": "mMaj7", "aug7": "aug7", "augmaj7": "augMaj7",
    "7sus4": "7sus4", "add9": "add9", "madd9": "madd9", "maj9": "maj9", "min9": "m9",
    "9": "9", "7b9": "7b9", "7#9": "7#9", "min11": "m11", "11": "11", "maj7#11": "maj7#11",
    "13": "13", "maj13": "maj13", "min13": "m13",
}

# Roman numeral suffix -> (quality when upper-case, quality when lower-case)
_SUFFIX_QUALITY = {
    "": ("maj", "min"),
    "°": ("dim", "dim"), "o": ("dim", "dim"), "dim": ("dim", "dim"),
    "°7": ("dim7", "dim7"), "o7": ("dim7", "dim7"), "dim7": ("dim7", "dim7"),
    "ø": ("m7b5", "m7b5"), "ø7": ("m7b5", "m7b5"), "m7b5": ("m7b5", "m7b5"), "h7": ("m7b5", "m7b5"),
    "+": ("aug", "aug"), "aug": ("aug", "aug"), "+7": ("aug7", "aug7"), "aug7": ("aug7", "aug7"),
    "7": ("7", "min7"),
    "maj7": ("maj7", "minmaj7"), "M7": ("maj7", "minmaj7"), "Δ": ("maj7", "minmaj7"), "Δ7": ("maj7", "minmaj7"),
    "9": ("9", "min9"), "maj9": ("maj9", "min9"), "M9": ("maj9", "min9"),
    "add9": ("add9", "madd9"),
    "6": ("6", "m6"), "69": ("69", "69"), "6/9": ("69", "69"),
    "11": ("11", "min11"), "13": ("13", "min13"), "maj13": ("maj13", "min13"),
    "sus2": ("sus2", "sus2"), "sus4": ("sus4", "sus4"), "sus": ("sus4", "sus4"), "7sus4": ("7sus4", "7sus4"),
    "5": ("power", "power"),
    "maj7#11": ("maj7#11", "maj7#11"), "7b9": ("7b9", "7b9"), "7#9": ("7#9", "7#9"),
}

_DEGREE_RE = r"(?:VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)"
_ROMAN_RE = re.compile(
    rf"^(?P<acc>[b#]?)(?P<deg>{_DEGREE_RE})(?P<qual>[^/]*)(?:/(?P<sec>[b#]?{_DEGREE_RE}))?$"
)
_DEGREE_INDEX = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6}


def pc_name(pc: int, prefer_flats: bool = False) -> str:
    names = FLAT_NAMES if prefer_flats else SHARP_NAMES
    return names[pc % 12]


def midi_name(midi: int, prefer_flats: bool = False) -> str:
    return f"{pc_name(midi, prefer_flats)}{midi // 12 - 1}"


def scale_pcs(tonic: int, mode: str) -> List[int]:
    if mode not in SCALES:
        raise KeyError(f"unknown mode {mode!r}")
    return [(tonic + i) % 12 for i in SCALES[mode]]


def scale_pitches(tonic: int, mode: str, low: int = 36, high: int = 96) -> List[int]:
    pcs = set(scale_pcs(tonic, mode))
    return [p for p in range(low, high + 1) if p % 12 in pcs]


def is_major_like(mode: str) -> bool:
    return mode in MAJOR_LIKE


@dataclass
class Chord:
    root: int                       # pitch class
    quality: str                    # key into CHORD_QUALITIES
    numeral: str = ""               # the Roman numeral that produced it
    bass: Optional[int] = None      # pitch class of the bass note (slash chord)

    @property
    def intervals(self) -> List[int]:
        return CHORD_QUALITIES[self.quality]

    @property
    def pcs(self) -> List[int]:
        """Pitch classes, root first, in chord-stack order (duplicates removed)."""
        out: List[int] = []
        for i in self.intervals:
            pc = (self.root + i) % 12
            if pc not in out:
                out.append(pc)
        return out

    def voicing_pcs(self, max_voices: int = 4) -> List[int]:
        """Pitch classes to voice in the pad/keys. Extended chords drop the
        fifth first and then the root (the bass supplies it), the way jazz
        and neo-soul keyboard voicings do, so 9th/13th chords never become
        five-note clusters."""
        pcs = self.pcs
        if len(pcs) <= max_voices:
            return pcs
        fifth = self.fifth
        if fifth is not None and len(pcs) > max_voices:
            pcs = [pc for pc in pcs if pc != fifth]
        if len(pcs) > max_voices:
            pcs = pcs[1:]
        return pcs[:max_voices]

    @property
    def third(self) -> Optional[int]:
        for i in self.intervals:
            if i in (3, 4):
                return (self.root + i) % 12
        return None

    @property
    def fifth(self) -> Optional[int]:
        for i in self.intervals:
            if i in (6, 7, 8):
                return (self.root + i) % 12
        return None

    @property
    def is_minor(self) -> bool:
        return 3 in self.intervals and 4 not in self.intervals

    def symbol(self, prefer_flats: bool = False) -> str:
        s = pc_name(self.root, prefer_flats) + QUALITY_SYMBOL[self.quality]
        if self.bass is not None and self.bass != self.root:
            s += "/" + pc_name(self.bass, prefer_flats)
        return s

    def to_dict(self, prefer_flats: bool = False) -> dict:
        return {
            "symbol": self.symbol(prefer_flats),
            "numeral": self.numeral,
            "root": pc_name(self.root, prefer_flats),
            "quality": self.quality,
            "pcs": self.pcs,
        }


def parse_roman(numeral: str, tonic: int, mode: str) -> Chord:
    """Parse a Roman numeral (``ii7``, ``bVImaj7``, ``V7/V``, ``viiø7`` ...) relative
    to a tonic and mode.

    The scale degree is looked up in the *mode's* scale, so ``VI`` in aeolian is
    the flat sixth of the parallel major, while ``VI`` in ionian is the natural
    sixth. ``b``/``#`` shift the root a semitone. Upper case implies a major
    triad, lower case a minor triad, unless the suffix decides otherwise.
    """
    text = numeral.strip()
    m = _ROMAN_RE.match(text)
    if not m:
        raise ValueError(f"cannot parse Roman numeral {numeral!r}")
    scale = SCALES[mode]
    if len(scale) < 7:
        # Pentatonic etc.: use the parent heptatonic scale for chord roots.
        scale = SCALES["ionian"] if is_major_like(mode) else SCALES["aeolian"]

    def degree_root(acc: str, deg: str) -> int:
        idx = _DEGREE_INDEX[deg.lower()]
        root = scale[idx]
        if acc == "b":
            root -= 1
        elif acc == "#":
            root += 1
        return root

    deg = m.group("deg")
    root = degree_root(m.group("acc"), deg)
    if m.group("sec"):
        sec = m.group("sec")
        sm = re.match(rf"^(?P<acc>[b#]?)(?P<deg>{_DEGREE_RE})$", sec)
        assert sm
        target = degree_root(sm.group("acc"), sm.group("deg"))
        # Secondary chord: the numeral is re-interpreted in the key of the target degree.
        # Only the major-key interpretation is used (V/x, vii°/x, ii/x).
        rel = SCALES["ionian"][_DEGREE_INDEX[deg.lower()]]
        if m.group("acc") == "b":
            rel -= 1
        elif m.group("acc") == "#":
            rel += 1
        root = target + rel
    qual_suffix = m.group("qual")
    if qual_suffix not in _SUFFIX_QUALITY:
        raise ValueError(f"unknown chord suffix {qual_suffix!r} in {numeral!r}")
    upper, lower = _SUFFIX_QUALITY[qual_suffix]
    quality = upper if deg.isupper() else lower
    return Chord(root=(tonic + root) % 12, quality=quality, numeral=text)


def chord_from_symbol(symbol: str) -> Chord:
    """Parse an absolute chord symbol such as ``Fmaj7``, ``Bbm7b5`` or ``G7/B``."""
    m = re.match(r"^([A-G][b#]?)(.*?)(?:/([A-G][b#]?))?$", symbol.strip())
    if not m:
        raise ValueError(f"bad chord symbol {symbol!r}")
    root = NOTE_TO_PC[m.group(1)]
    suffix = m.group(2)
    inverse = {v: k for k, v in QUALITY_SYMBOL.items()}
    inverse.update({"m": "min", "M7": "maj7", "-7": "min7", "min7": "min7", "maj": "maj", "min": "min",
                    "°": "dim", "ø7": "m7b5", "ø": "m7b5", "+": "aug", "Δ7": "maj7", "Δ": "maj7"})
    if suffix not in inverse:
        raise ValueError(f"unknown chord suffix {suffix!r}")
    bass = NOTE_TO_PC[m.group(3)] if m.group(3) else None
    return Chord(root=root, quality=inverse[suffix], bass=bass)


# ---------------------------------------------------------------------------
# Voice leading
# ---------------------------------------------------------------------------

def _nearest_octave(pc: int, target: int, low: int, high: int) -> int:
    """MIDI pitch with pitch class ``pc`` closest to ``target`` inside [low, high]."""
    base = target - ((target - pc) % 12)
    candidates = [base, base + 12, base - 12]
    candidates = [c for c in candidates if low <= c <= high] or [min(max(base, low), high)]
    return min(candidates, key=lambda c: (abs(c - target), c))


def close_voicing(chord: Chord, low: int = 48, high: int = 72, max_voices: int = 4) -> List[int]:
    """Stack the chord's pitch classes in close position starting near ``low``."""
    pcs = chord.voicing_pcs(max_voices)
    root = low + ((pcs[0] - low) % 12)
    voicing = [root]
    for pc in pcs[1:]:
        prev = voicing[-1]
        nxt = prev + ((pc - prev) % 12 or 12)
        voicing.append(nxt)
    # Keep inside the range by dropping the whole stack an octave if needed.
    while voicing and voicing[-1] > high and voicing[0] - 12 >= low - 12:
        voicing = [v - 12 for v in voicing]
    return voicing


def voice_lead(prev: Optional[Sequence[int]], chord: Chord, low: int = 48, high: int = 76,
               max_voices: int = 4) -> List[int]:
    """Choose a voicing for ``chord`` that moves each voice as little as possible
    from ``prev`` (common-practice smooth voice leading, also what synth pads want).

    Returns MIDI pitches sorted ascending. Every pitch class of the chord (up to
    ``max_voices``) is present exactly once.
    """
    pcs = chord.voicing_pcs(max_voices)
    if not prev:
        return close_voicing(chord, low, high, max_voices)
    prev = sorted(prev)
    # Equalise the number of voices.
    if len(prev) < len(pcs):
        while len(prev) < len(pcs):
            prev = prev + [min(high, prev[-1] + 4)]
    elif len(prev) > len(pcs):
        prev = prev[: len(pcs)] if len(pcs) < 3 else prev[-len(pcs):]

    best = None
    for perm in itertools.permutations(pcs):
        voicing = [_nearest_octave(pc, target, low, high) for pc, target in zip(perm, prev)]
        motion = sum(abs(v - t) for v, t in zip(voicing, prev))
        # Penalise voice crossing and unisons (two voices on the same pitch).
        s = sorted(voicing)
        unisons = len(voicing) - len(set(voicing))
        spread = s[-1] - s[0]
        score = motion + 6 * unisons + (2 if spread > 19 else 0)
        if best is None or score < best[0]:
            best = (score, s)
    assert best is not None
    return best[1]


def spread_voicing(chord: Chord, low: int = 40, high: int = 84) -> List[int]:
    """Open "synth pad" voicing: root low, fifth, then upper structure an octave up."""
    pcs = chord.pcs
    root = low + ((pcs[0] - low) % 12)
    out = [root]
    fifth = chord.fifth
    if fifth is not None:
        out.append(root + ((fifth - root) % 12))
    upper = [pc for pc in pcs if pc not in (pcs[0], fifth)]
    anchor = root + 12
    for pc in upper:
        cand = anchor + ((pc - anchor) % 12)
        out.append(cand)
        anchor = cand
    out = [p for p in out if p <= high]
    return sorted(set(out))


def transpose(pitches: Iterable[int], semitones: int) -> List[int]:
    return [p + semitones for p in pitches]


def nearest_scale_pitch(pitch: int, allowed_pcs: Iterable[int]) -> int:
    allowed = set(p % 12 for p in allowed_pcs)
    for d in range(0, 7):
        for cand in (pitch - d, pitch + d):
            if cand % 12 in allowed:
                return cand
    return pitch


def interval_name(semitones: int) -> str:
    names = ["P1", "m2", "M2", "m3", "M3", "P4", "TT", "P5", "m6", "M6", "m7", "M7"]
    octs, rem = divmod(abs(semitones), 12)
    s = names[rem]
    return s + (f"+{octs}oct" if octs else "")
