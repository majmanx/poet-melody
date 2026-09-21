"""Mandarin tones for 依字行腔 (setting words so the melody follows speech tones).

The tone table covers U+4E00..U+9FFF (one digit per code point, generated from
pypinyin's most common reading): 1 阴平 high-level, 2 阳平 rising, 3 上声
low-dipping, 4 去声 falling, 5 neutral, 0 unknown.

Each tone is modelled as a (start, end) pitch height in 0..1. Two consecutive
syllables suggest a melodic direction: the next note should move the way the
tone heights move, otherwise the word is "sung upside down" (倒字) and can be
misheard. Phrase-final tones also suggest whether a phrase feels open (rising
T1/T2) or closed (falling/low T3/T4), which we map onto cadences.
"""
from __future__ import annotations

import os
from typing import List, Optional, Sequence, Tuple

_TABLE: Optional[str] = None
_START, _END = 0x4E00, 0x9FFF

# (start height, end height)
TONE_SHAPE = {
    1: (0.85, 0.85),
    2: (0.45, 0.85),
    3: (0.30, 0.15),
    4: (0.90, 0.30),
    5: (0.50, 0.50),
}
TONE_NAMES = {0: "?", 1: "阴平", 2: "阳平", 3: "上声", 4: "去声", 5: "轻声"}


def _load() -> str:
    global _TABLE
    if _TABLE is None:
        path = os.path.join(os.path.dirname(__file__), "data", "tones_4e00_9fff.txt")
        try:
            with open(path, "r", encoding="ascii") as fh:
                _TABLE = fh.read().strip()
        except OSError:
            _TABLE = ""
    return _TABLE


def tone_of(ch: str) -> int:
    """Tone number 1..5 for a CJK character, 0 when unknown (or not CJK)."""
    if len(ch) != 1:
        return 0
    cp = ord(ch)
    if not (_START <= cp <= _END):
        return 0
    table = _load()
    idx = cp - _START
    if idx >= len(table):
        return 0
    return int(table[idx])


def tones_of(syllables: Sequence[str]) -> List[int]:
    return [tone_of(s) if len(s) == 1 else 0 for s in syllables]


def tone_height(tone: int) -> Optional[Tuple[float, float]]:
    return TONE_SHAPE.get(tone)


# Perceived register of each tone (mean height), used for between-syllable direction.
TONE_LEVEL = {1: 0.85, 2: 0.62, 3: 0.22, 4: 0.60, 5: 0.50}


def tone_direction(prev_tone: int, next_tone: int) -> int:
    """Preferred melodic direction from one syllable to the next:
    +1 up, -1 down, 0 no preference (unknown, level, or two rising tones)."""
    a, b = TONE_LEVEL.get(prev_tone), TONE_LEVEL.get(next_tone)
    if a is None or b is None:
        return 0
    diff = b - a
    if diff > 0.2:
        return 1
    if diff < -0.2:
        return -1
    return 0


def phrase_openness(final_tone: int) -> Optional[bool]:
    """True = the phrase-final tone feels open/rising (T1, T2), False = closed
    (T3, T4), None = unknown/neutral."""
    if final_tone in (1, 2):
        return True
    if final_tone in (3, 4):
        return False
    return None


def describe(syllables: Sequence[str]) -> str:
    return " ".join(f"{s}{t if t else ''}" for s, t in zip(syllables, tones_of(syllables)))
