"""Score data model shared by the composer, the MIDI writer and the renderer.

Times are in *beats* (quarter notes) from the start of the piece; the
:class:`Timeline` converts beats to seconds (tempo, swing, ritardando).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Note:
    start: float            # beats
    duration: float         # beats
    pitch: int              # MIDI
    velocity: int = 90      # 1..127
    lyric: str = ""         # syllable that produced the note (lead only)
    tone: int = 0           # Mandarin tone of the syllable (0 unknown)

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class ChordEvent:
    start: float
    duration: float
    symbol: str
    numeral: str
    root: int               # pitch class
    quality: str
    pcs: List[int]
    voicing: List[int]      # MIDI pitches used by the pad/keys
    bass: int               # MIDI pitch of the bass root


@dataclass
class Section:
    name: str
    start: float
    duration: float
    kind: str                # intro | verse | outro
    mode: str = "ionian"
    progression: str = ""
    numerals: List[str] = field(default_factory=list)
    text: str = ""
    label: str = ""          # form letter (A, B, C)
    key: str = ""            # tonic name of the section (B sections may modulate)
    role: str = ""           # exposition | development | climax | resolution | ...
    dynamic: float = 0.5


@dataclass
class Track:
    name: str
    role: str                # pad | keys | bass | lead | drums
    patch: str               # patch name (see Composition.patches)
    notes: List[Note] = field(default_factory=list)
    midi_program: int = 0
    midi_channel: int = 0
    level: float = 0.8
    pan: float = 0.0


@dataclass
class Timeline:
    """Beat -> seconds mapping with swing and an optional final ritardando."""
    bpm: float
    beats_per_bar: int = 4
    swing: float = 0.5              # 0.5 straight; 0.66 = triplet swing
    rit_start: Optional[float] = None   # beat where the ritardando begins
    rit_end: Optional[float] = None
    rit_factor: float = 0.65        # tempo multiplier reached at rit_end

    def swung(self, beat: float) -> float:
        """Warp the position inside each beat so off-beat eighths land late."""
        if abs(self.swing - 0.5) < 1e-6:
            return beat
        whole = math.floor(beat)
        frac = beat - whole
        s = self.swing
        if frac < 0.5:
            frac = frac * 2 * s
        else:
            frac = s + (frac - 0.5) * 2 * (1 - s)
        return whole + frac

    def seconds(self, beat: float) -> float:
        b = self.swung(beat)
        spb = 60.0 / self.bpm
        if self.rit_start is None or self.rit_end is None or b <= self.rit_start:
            return b * spb
        L = self.rit_end - self.rit_start
        k = (1 - self.rit_factor) / L if L > 0 else 0.0
        base = self.rit_start * spb

        def integ(x: float) -> float:
            # integral of spb / (1 - k x) dx from 0..x
            if k <= 0:
                return spb * x
            x = min(x, (1 - 1e-6) / k)
            return -spb / k * math.log(1 - k * x)

        if b <= self.rit_end:
            return base + integ(b - self.rit_start)
        return base + integ(L) + (b - self.rit_end) * spb / self.rit_factor

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Composition:
    title: str
    style: str
    key: str                # e.g. "Eb"
    tonic: int              # pitch class
    mode: str
    scale: List[str]        # note names of the mode
    bpm: float
    time_signature: List[int]
    timeline: Timeline
    seed: int
    features: Dict[str, Any]
    sections: List[Section] = field(default_factory=list)
    chords: List[ChordEvent] = field(default_factory=list)
    tracks: List[Track] = field(default_factory=list)
    patches: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    notes_on_theory: List[str] = field(default_factory=list)
    interpretation: Dict[str, Any] = field(default_factory=dict)
    form: str = ""

    @property
    def total_beats(self) -> float:
        ends = [n.end for t in self.tracks for n in t.notes] + [c.start + c.duration for c in self.chords]
        return max(ends) if ends else 0.0

    @property
    def total_seconds(self) -> float:
        return self.timeline.seconds(self.total_beats)

    def track(self, role: str) -> Optional[Track]:
        for t in self.tracks:
            if t.role == role:
                return t
        return None

    def to_dict(self) -> dict:
        tl = self.timeline
        return {
            "title": self.title,
            "style": self.style,
            "key": self.key,
            "tonic": self.tonic,
            "mode": self.mode,
            "scale": self.scale,
            "bpm": self.bpm,
            "time_signature": self.time_signature,
            "swing": tl.swing,
            "timeline": tl.to_dict(),
            "seed": self.seed,
            "duration_beats": round(self.total_beats, 3),
            "duration_seconds": round(self.total_seconds, 3),
            "features": self.features,
            "form": self.form,
            "interpretation": self.interpretation,
            "notes_on_theory": self.notes_on_theory,
            "sections": [asdict(s) for s in self.sections],
            "chords": [
                {**asdict(c), "start_sec": round(tl.seconds(c.start), 4),
                 "end_sec": round(tl.seconds(c.start + c.duration), 4)} for c in self.chords
            ],
            "patches": self.patches,
            "tracks": [
                {
                    "name": t.name, "role": t.role, "patch": t.patch, "midi_program": t.midi_program,
                    "midi_channel": t.midi_channel, "level": t.level, "pan": t.pan,
                    "notes": [
                        {"start": round(n.start, 4), "duration": round(n.duration, 4), "pitch": n.pitch,
                         "velocity": n.velocity, "lyric": n.lyric, "tone": n.tone,
                         "start_sec": round(tl.seconds(n.start), 4),
                         "end_sec": round(tl.seconds(n.start + n.duration), 4)}
                        for n in t.notes
                    ],
                }
                for t in self.tracks
            ],
        }
