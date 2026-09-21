"""Text-driven melody generation.

Each singable unit (a CJK character or an English syllable) becomes one note.

* **Rhythm** – syllables are spread over the bars of their line on an eighth
  or sixteenth grid; the phrase-final syllable is lengthened and followed by a
  breath (rest). Energetic texts get denser grids; "still" imagery slows them.
* **Contour** – every line follows a phrase arc (statements rise to a peak near
  the golden ratio and fall; questions rise at the end; exclamations start
  high). Endings are *open* (2nd/5th degree), *semi* (chord tone, not the
  root), *closed* (root/3rd) or *final* (tonic), like a classical period.
* **依字行腔 (tones)** – for Chinese, the melodic direction between syllables
  follows the Mandarin tone registers (a 去声 falling to a 阴平 must rise, a
  阴平 to 上声 must fall); rising 阳平 gets an appoggiatura from below,
  falling 去声 a short falling tail. Violations (倒字) are penalised.
* **Leitmotif** – every syllable carries a deterministic pitch "signature"
  derived from its text, so the same word recurs with the same melodic shape;
  a section's *head motif* (its first intervals) can be recalled in later
  sections of the same form letter (A ... A').
* **Word painting** – rise/fall/still/flow/far/home/night/light imagery bends
  the arc, register, leap policy and rhythm of its line.
* **Constraints** – chord tones on strong beats, scale tones elsewhere, no
  leaps larger than an octave, leaps recovered by a step in the opposite
  direction, melodic tritones/sevenths avoided (classical voice leading
  rules), all tie-broken by a seeded random generator.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .analysis import Line, token_seed
from .score import ChordEvent, Note
from .theory import SCALES, is_major_like
from .tones import TONE_LEVEL, tone_direction, tones_of


@dataclass
class LinePlan:
    line: Line
    bars: int
    onsets: List[float]        # beats relative to the line start
    durations: List[float]


def plan_rhythm(line: Line, beats_per_bar: int, arousal: float, irregularity: float,
                rng: random.Random, min_bars: int = 1, stretch: float = 1.0) -> LinePlan:
    """Decide how many bars a line occupies and where its syllables fall.
    ``stretch`` > 1 slows the line (word painting for stillness)."""
    n = len(line.syllables)
    # Beats per syllable: slow texts ~1 beat, energetic ~0.5 beat.
    base = (1.05 - 0.6 * arousal) * stretch
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


def phrase_arc(x: float, line: Line, ending: str) -> float:
    """Normalised contour (0..1) for position x in [0, 1] within a line."""
    if line.ends_with_question:
        return 0.25 + 0.75 * x ** 1.5
    if line.ends_with_exclamation:
        return 1.0 - 0.7 * x
    if line.ends_with_ellipsis:
        return 0.4 - 0.3 * x + 0.15 * math.sin(6.0 * x)
    peak = 0.5 if ending == "open" else 0.62
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
    tone_weight: float = 3.0         # strength of the 依字行腔 constraint (0 disables)
    ornament_prob: float = 0.5       # probability of tone ornaments (zh only)


@dataclass
class PhrasePlan:
    """One line of text ready to be sung."""
    plan: LinePlan
    start: float                     # absolute beat
    ending: str                      # open | semi | closed | final
    tonic: int                       # pitch class of the section's key
    mode: str
    devices: Sequence[str] = ()      # word-painting keys
    register_shift: int = 0          # semitones added to the centre for this line
    velocity_shift: int = 0
    motif: Optional[Sequence[int]] = None   # intervals to recall at the start of the line
    tones: Optional[Sequence[int]] = None   # Mandarin tones, 0 = unknown


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


def _scale_step_below(pitch: int, allowed: Sequence[int]) -> int:
    for d in range(1, 4):
        if (pitch - d) % 12 in allowed:
            return pitch - d
    return pitch - 2


class MelodyState:
    """Carries the melodic thread across lines and sections."""

    def __init__(self) -> None:
        self.prev_pitch: Optional[int] = None
        self.prev_interval = 0
        self.prev_sign = 1
        self.repeats = 0
        self.prev_nonchord = False      # the previous note was a non-chord tone (must resolve by step)


def _avoid_notes(scale_pcs: Sequence[int], chord_pcs: Sequence[int]) -> set:
    """Scale tones a semitone away from a chord tone that is *not* in the scale
    (the b7 against a major V in minor, the natural 6 against a borrowed iv ...).
    Singing them over that chord is the classic wrong-note clash."""
    scale = set(scale_pcs)
    out = set()
    for ct in chord_pcs:
        if ct in scale:
            continue
        for s_ in ((ct - 1) % 12, (ct + 1) % 12):
            if s_ in scale:
                out.add(s_)
    return out


def _stability(pc: int, chord_pcs: Sequence[int]) -> float:
    """How restful a chord tone is: root/fifth > third > seventh > extensions."""
    if pc not in chord_pcs:
        return 0.0
    idx = chord_pcs.index(pc)
    return (1.0, 0.85, 1.0, 0.55, 0.35, 0.3)[idx] if idx < 6 else 0.3


def sing_line(phrase: PhrasePlan, chords: Sequence[ChordEvent], beats_per_bar: int, cfg: MelodyConfig,
              rng: random.Random, state: MelodyState) -> List[Note]:
    plan, line = phrase.plan, phrase.plan.line
    tonic, mode = phrase.tonic, phrase.mode
    scale_pcs = _melody_pcs(tonic, mode, cfg.melody_scale)
    devices = set(phrase.devices)
    center = cfg.center + phrase.register_shift + (-3 if "night" in devices else 0) + (2 if "light" in devices else 0)
    lo, hi = center - cfg.span, center + cfg.span
    amplitude = 4.0 + 5.0 * cfg.arousal
    strong_beats = {0, 2} if beats_per_bar == 4 else {0}
    tones = list(phrase.tones) if phrase.tones else tones_of(line.syllables)
    zh = any(t for t in tones)
    n = len(plan.onsets)
    line_rng = random.Random(rng.random())
    base_offset = line_rng.choice([-2, -1, 0, 0, 1, 2])
    notes: List[Note] = []
    prev_tone = 0

    for i, (rel, dur) in enumerate(zip(plan.onsets, plan.durations)):
        beat = phrase.start + rel
        chord = _chord_at(chords, beat)
        chord_pcs = chord.pcs if chord else [tonic]
        x = i / max(1, n - 1) if n > 1 else 0.5
        arc = phrase_arc(x, line, phrase.ending)
        if "rise" in devices:
            arc = 0.6 * arc + 0.4 * x
        if "fall" in devices:
            arc = 0.6 * arc + 0.4 * (1 - x)
        token = line.syllables[i]
        tone = tones[i] if i < len(tones) else 0
        target = center + base_offset + (arc - 0.4) * amplitude + signature(token) * 0.4
        if tone:
            target += (TONE_LEVEL[tone] - 0.55) * 4.0      # high tones sit higher, 上声 lower
        pos_in_bar = beat % beats_per_bar
        strong = int(round(pos_in_bar * 4)) / 4 in strong_beats
        last = i == n - 1
        first = i == 0
        want_dir = tone_direction(prev_tone, tone) if (zh and cfg.tone_weight > 0 and not first) else 0
        motif_iv = None
        if phrase.motif and i < len(phrase.motif) + 1 and i > 0 and state.prev_pitch is not None:
            motif_iv = phrase.motif[i - 1]

        avoid = _avoid_notes(scale_pcs, chord_pcs)
        allowed = (set(scale_pcs) - avoid) | set(chord_pcs) if strong or last else (set(scale_pcs) - avoid)
        candidates = [p for p in range(lo, hi + 1) if p % 12 in allowed]
        best: Optional[Tuple[float, int]] = None
        for p in candidates:
            score = -abs(p - target)
            in_chord = p % 12 in chord_pcs
            stab = _stability(p % 12, chord_pcs)
            if strong:
                score += 3.2 * stab if in_chord else -1.0
            else:
                score += 0.9 * stab if in_chord else 0.0
            if not in_chord and any((p - ct) % 12 == 1 for ct in chord_pcs):
                # A scale tone a semitone *above* a chord tone (the jazz "avoid
                # note": 4 over a major triad, b9 over a dominant) is harsh unless
                # it passes quickly.
                score -= 1.5 + (1.5 if dur >= 1.0 else 0.0)
            if state.prev_pitch is not None:
                d = abs(p - state.prev_pitch)
                sgn = 1 if p > state.prev_pitch else (-1 if p < state.prev_pitch else 0)
                if d > (12 if "far" in devices else 9):
                    continue
                if d > 7:
                    score -= 5.0 if "far" not in devices else 1.0
                elif d > 4:
                    score -= 1.5 if "far" not in devices else -0.5
                if d > 4 and state.prev_interval > 4 and sgn * state.prev_sign > 0:
                    score -= 3.0                  # two leaps in the same direction
                if state.prev_nonchord:
                    score += 1.5 if d <= 2 else -2.0   # a non-chord tone resolves by step
                if "flow" in devices and d > 2:
                    score -= 1.5
                if d in (6, 10, 11):
                    score -= 2.5                  # melodic tritone / sevenths
                if d == 0:
                    score -= cfg.repeat_penalty * (1 + state.repeats)
                if not in_chord and d > 2:
                    score -= 2.0                  # non-chord tones must be approached by step
                if state.prev_interval > 4 and d <= 2 and sgn * state.prev_sign < 0:
                    score += 2.0                  # leap recovery
                if first and d <= 4:
                    score += 0.5
                # 依字行腔: follow the tone direction, punish 倒字.
                if want_dir:
                    if sgn == want_dir:
                        score += cfg.tone_weight
                    elif sgn == -want_dir:
                        score -= cfg.tone_weight * 1.5
                    else:
                        score -= cfg.tone_weight * 0.4      # a repeat is a mild violation
                if motif_iv is not None:
                    score += 4.0 if (p - state.prev_pitch) == motif_iv else 0.0
            else:
                if not in_chord:
                    score -= 2.0
            # Phrase endings rest on triad tones, not on sevenths or extensions.
            if last:
                deg = (p - tonic) % 12
                root = chord.root if chord else tonic
                third = chord.pcs[1] if chord and len(chord.pcs) > 1 else root
                if in_chord and chord_pcs.index(p % 12) >= 3:
                    score -= 2.0
                if phrase.ending == "open":
                    if deg in (7, 2):
                        score += 2.5              # dominant / supertonic
                    if p % 12 == tonic:
                        score -= 1.0
                elif phrase.ending == "semi":
                    if in_chord and p % 12 != root:
                        score += 2.0              # chord tone but not the root
                    if p % 12 == tonic:
                        score -= 1.5
                elif phrase.ending == "closed":
                    if p % 12 == root:
                        score += 1.5
                    elif p % 12 == third:
                        score += 1.0
                else:  # final
                    if p % 12 == root:
                        score += 2.5
                    if p % 12 == tonic:
                        score += 3.0
                if "home" in devices and p % 12 == tonic:
                    score += 2.0
            if p > center + 10 or p < center - 9:
                score -= 3.0
            score += line_rng.random() * cfg.temperature
            if best is None or score > best[0]:
                best = (score, p)
        assert best is not None
        pitch = best[1]
        if state.prev_pitch is not None:
            iv = pitch - state.prev_pitch
            state.repeats = state.repeats + 1 if iv == 0 else 0
            state.prev_interval = abs(iv)
            state.prev_sign = 1 if iv > 0 else (-1 if iv < 0 else state.prev_sign)
        state.prev_pitch = pitch
        state.prev_nonchord = pitch % 12 not in chord_pcs
        vel = (62 + int(34 * cfg.arousal) + (8 if strong else 0) + int(8 * arc) + phrase.velocity_shift
               + (-8 if "night" in devices else 0) + (6 if "light" in devices else 0) + line_rng.randint(-4, 4))
        vel = max(30, min(127, vel))

        # Tone ornaments (依字行腔 within the syllable).
        ornament_ok = zh and tone in (2, 3, 4) and dur >= 0.75 and "still" not in devices \
            and line_rng.random() < cfg.ornament_prob
        if ornament_ok and tone in (2, 3):
            grace = min(0.25, dur / 3)
            below = _scale_step_below(pitch, allowed)
            if tone == 3:
                below = _scale_step_below(below, allowed)
            notes.append(Note(beat, grace, below, max(30, vel - 14), "", tone))
            notes.append(Note(beat + grace, dur - grace, pitch, vel, token, tone))
        elif ornament_ok and tone == 4:
            tail = min(0.25, dur / 3)
            notes.append(Note(beat, dur - tail, pitch, vel, token, tone))
            notes.append(Note(beat + dur - tail, tail, _scale_step_below(pitch, allowed), max(30, vel - 18), "", tone))
        else:
            notes.append(Note(beat, dur, pitch, vel, token, tone))
        prev_tone = tone
    state.prev_interval = 0
    return notes


def head_motif(notes: Sequence[Note], length: int = 4) -> List[int]:
    """Intervals between the first ``length`` sung notes of a section."""
    sung = [n for n in notes if n.lyric][:length]
    return [b.pitch - a.pitch for a, b in zip(sung, sung[1:])]


def generate_melody(phrases: Sequence[PhrasePlan], chords: Sequence[ChordEvent], beats_per_bar: int,
                    cfg: MelodyConfig, rng: random.Random, state: Optional[MelodyState] = None) -> List[Note]:
    state = state or MelodyState()
    out: List[Note] = []
    for ph in phrases:
        out += sing_line(ph, chords, beats_per_bar, cfg, rng, state)
    return out
