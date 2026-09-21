"""Text-driven melody generation.

Each singable unit (a CJK character or an English syllable) becomes one note.

* **Rhythm** – syllables are spread over the bars of their line on an eighth
  or sixteenth grid; the phrase-final syllable is lengthened and followed by a
  breath (rest). Energetic texts get denser grids.
* **Contour** – every line follows a phrase arc (statements rise to a peak near
  the golden ratio and fall; questions rise at the end; exclamations start
  high). Lines alternate antecedent (open ending on 2nd/5th) and consequent
  (closed ending on root/3rd) like a classical period.
* **Leitmotif** – every syllable carries a deterministic pitch "signature"
  derived from its text, so the same word recurs with the same melodic shape.
* **Constraints** – chord tones on strong beats, scale tones elsewhere, no
  leaps larger than an octave, leaps recovered by a step in the opposite
  direction, melodic tritones/sevenths avoided (classical voice leading
  rules), all tie-broken by a seeded random generator.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .analysis import Line, token_seed
from .score import ChordEvent, Note
from .theory import SCALES, is_major_like


@dataclass
class LinePlan:
    line: Line
    bars: int
    onsets: List[float]        # beats relative to the line start
    durations: List[float]


def plan_rhythm(line: Line, beats_per_bar: int, arousal: float, irregularity: float,
                rng: random.Random, min_bars: int = 1) -> LinePlan:
    """Decide how many bars a line occupies and where its syllables fall."""
    n = len(line.syllables)
    # Beats per syllable: slow texts ~1 beat, energetic ~0.5 beat.
    base = 1.05 - 0.6 * arousal
    tail = 1.0 if arousal < 0.5 else 0.5          # breath at the end of the phrase
    bars = max(min_bars, math.ceil((n * base + tail) / beats_per_bar))
    grid = 0.5 if arousal < 0.6 else 0.25
    total = bars * beats_per_bar
    avail = total - tail
    while n * grid > avail:
        if grid > 0.25:
            grid = 0.25
        else:
            bars += 1
            total = bars * beats_per_bar
            avail = total - tail
    slots = int(round(avail / grid))
    # Evenly spaced positions snapped to the grid ...
    positions = sorted({min(slots - 1, int(round(i * slots / n))) for i in range(n)})
    while len(positions) < n:  # collisions after rounding: fill the nearest free slot
        free = [s for s in range(slots) if s not in positions]
        positions.append(min(free, key=lambda s: min(abs(s - p) for p in positions)))
        positions.sort()
    # ... then jittered towards syncopation for irregular / energetic texts.
    jitter = 0.1 + 0.35 * irregularity + 0.2 * arousal
    for i in range(1, n):
        if rng.random() < jitter:
            cand = positions[i] + rng.choice((-1, 1))
            lo = positions[i - 1] + 1
            hi = positions[i + 1] - 1 if i + 1 < n else slots - 1
            if lo <= cand <= hi:
                positions[i] = cand
    positions[0] = 0
    onsets = [p * grid for p in positions]
    durations: List[float] = []
    for i, on in enumerate(onsets):
        nxt = onsets[i + 1] if i + 1 < n else avail
        dur = nxt - on
        if i + 1 < n:
            dur = min(dur, 2.0)
        else:
            dur = min(max(dur, 1.0), 3.0)   # phrase-final lengthening
        durations.append(dur)
    return LinePlan(line, bars, onsets, durations)


def phrase_arc(x: float, line: Line, antecedent: bool) -> float:
    """Normalised contour (0..1) for position x in [0, 1] within a line."""
    if line.ends_with_question:
        return 0.25 + 0.75 * x ** 1.5
    if line.ends_with_exclamation:
        return 1.0 - 0.7 * x
    if line.ends_with_ellipsis:
        return 0.4 - 0.3 * x + 0.15 * math.sin(6.0 * x)
    peak = 0.62 if not antecedent else 0.5
    y = 1.0 - ((x - peak) / max(peak, 1e-6)) ** 2
    return max(0.0, y)


def signature(token: str) -> float:
    """Deterministic leitmotif offset (semitones, -3..3) for a syllable/word."""
    s = token_seed(token)
    r = random.Random(s)
    return r.choice([-3, -2, -2, -1, -1, 0, 0, 0, 1, 1, 2, 2, 3])


@dataclass
class MelodyConfig:
    center: int = 67                 # MIDI pitch around which the melody lives
    span: int = 12                   # +/- semitones of comfortable range
    melody_scale: str = "mode"       # mode | pentatonic | blues
    arousal: float = 0.4
    valence: float = 0.0
    tension: float = 0.3
    temperature: float = 0.6         # randomness in candidate scoring
    repeat_penalty: float = 0.8


def _melody_pcs(tonic: int, mode: str, melody_scale: str) -> List[int]:
    if melody_scale == "pentatonic":
        base = SCALES["major_pentatonic"] if is_major_like(mode) else SCALES["minor_pentatonic"]
    elif melody_scale == "blues":
        base = SCALES["blues"]
    else:
        base = SCALES[mode]
    return [(tonic + i) % 12 for i in base]


def _chord_at(chords: Sequence[ChordEvent], beat: float) -> Optional[ChordEvent]:
    for c in chords:
        if c.start <= beat < c.start + c.duration:
            return c
    return chords[-1] if chords else None


def generate_melody(plans: Sequence[Tuple[LinePlan, float, bool, bool]], chords: Sequence[ChordEvent],
                    tonic: int, mode: str, beats_per_bar: int, cfg: MelodyConfig,
                    rng: random.Random) -> List[Note]:
    """Realise notes for planned lines.

    ``plans`` items are ``(plan, line_start_beat, antecedent, is_final_line)``.
    """
    scale_pcs = _melody_pcs(tonic, mode, cfg.melody_scale)
    lo, hi = cfg.center - cfg.span, cfg.center + cfg.span
    notes: List[Note] = []
    prev_pitch: Optional[int] = None
    prev_interval = 0
    prev_interval_sign = 1
    repeats = 0
    amplitude = 5.0 + 7.0 * cfg.arousal
    strong_beats = {0, 2} if beats_per_bar == 4 else {0}

    for plan, line_start, antecedent, is_final in plans:
        n = len(plan.onsets)
        line_rng = random.Random(rng.random())
        base_offset = line_rng.choice([-2, -1, 0, 0, 1, 2])
        for i, (rel, dur) in enumerate(zip(plan.onsets, plan.durations)):
            beat = line_start + rel
            chord = _chord_at(chords, beat)
            chord_pcs = chord.pcs if chord else [tonic]
            x = i / max(1, n - 1) if n > 1 else 0.5
            arc = phrase_arc(x, plan.line, antecedent)
            token = plan.line.syllables[i]
            target = cfg.center + base_offset + (arc - 0.4) * amplitude + signature(token) * 0.6
            pos_in_bar = (beat % beats_per_bar)
            strong = int(round(pos_in_bar * 4)) / 4 in strong_beats
            last = i == n - 1
            first = i == 0

            allowed = set(scale_pcs) | set(chord_pcs) if strong or last else set(scale_pcs)
            candidates = [p for p in range(lo, hi + 1) if p % 12 in allowed]
            best: Optional[Tuple[float, int]] = None
            for p in candidates:
                score = -abs(p - target)
                in_chord = p % 12 in chord_pcs
                if strong:
                    score += 3.0 if in_chord else -1.0
                else:
                    score += 0.8 if in_chord else 0.0
                if prev_pitch is not None:
                    d = abs(p - prev_pitch)
                    if d > 12:
                        continue
                    if d > 7:
                        score -= 4.0
                    elif d > 4:
                        score -= 1.5
                    if d in (6, 10, 11):
                        score -= 2.5                  # melodic tritone / sevenths
                    if d == 0:
                        score -= cfg.repeat_penalty * (1 + repeats)
                    if not in_chord and d > 2:
                        score -= 2.0                  # non-chord tones must be approached by step
                    if prev_interval > 4 and d <= 2 and (p - prev_pitch) * prev_interval_sign < 0:
                        score += 2.0                  # leap recovery
                    if first and d <= 4:
                        score += 0.5
                else:
                    if not in_chord:
                        score -= 2.0
                # Phrase endings.
                if last:
                    deg = (p - tonic) % 12
                    if antecedent and not is_final:
                        if deg in (7, 2):
                            score += 2.5              # open: dominant / supertonic
                    else:
                        if chord and p % 12 == chord.root:
                            score += 2.5 if is_final else 1.5
                        elif chord and p % 12 == (chord.pcs[1] if len(chord.pcs) > 1 else chord.root):
                            score += 1.0
                        if is_final and p % 12 == tonic:
                            score += 3.0
                if p > cfg.center + 10 or p < cfg.center - 9:
                    score -= 3.0
                score += line_rng.random() * cfg.temperature
                if best is None or score > best[0]:
                    best = (score, p)
            assert best is not None
            pitch = best[1]
            if prev_pitch is not None:
                iv = pitch - prev_pitch
                repeats = repeats + 1 if iv == 0 else 0
                prev_interval = abs(iv)
                prev_interval_sign = 1 if iv > 0 else -1
            else:
                prev_interval, prev_interval_sign, repeats = 0, 1, 0
            prev_pitch = pitch
            vel = 62 + int(34 * cfg.arousal) + (8 if strong else 0) + int(8 * arc) + line_rng.randint(-4, 4)
            notes.append(Note(start=beat, duration=dur, pitch=pitch, velocity=max(30, min(127, vel)), lyric=token))
        prev_interval = 0
    return notes
