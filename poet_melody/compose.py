"""The composer: text -> :class:`~poet_melody.score.Composition`.

Pipeline
--------
1. :func:`poet_melody.analysis.analyze` extracts affect and structure.
2. A style is chosen (or forced), then key, mode, tempo, metre and swing.
3. Every stanza becomes a section with its own chord progression (library or
   functionally generated) and its lines are laid out bar by bar.
4. Chords are voice-led; pad, keys, bass, lead (the sung text) and drums are
   arranged according to the style's patterns.
5. Timbres are designed from the same affect features.

Everything is seeded from the text, so a letter always yields the same piece
unless a different ``seed`` is requested.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

from .analysis import TextFeatures, analyze
from .melody import LinePlan, MelodyConfig, generate_melody, plan_rhythm
from .midi import DRUM_NOTES
from .progressions import HarmonyOptions, Progression, generate_functional, pick_progression
from .score import ChordEvent, Composition, Note, Section, Timeline, Track
from .styles import STYLES, Style, choose_style
from .synth import design_patches
from .theory import (FLAT_KEYS, NOTE_TO_PC, Chord, is_major_like, parse_roman, pc_name, scale_pcs,
                     voice_lead)

WARM_KEYS = [5, 10, 3, 8, 1]      # F Bb Eb Ab Db
BRIGHT_KEYS = [7, 2, 9, 4, 0]     # G D A E C


def _choose_mode(f: TextFeatures, st: Style, rng: random.Random) -> str:
    v, t = f.valence, f.tension
    p_major = 0.5 + 0.9 * v - 0.25 * (t - 0.4)
    major = rng.random() < max(0.05, min(0.95, p_major))
    options = list(st.major_modes if major else st.minor_modes)
    # The second option in each list is the more "coloured" mode; tension picks it.
    if len(options) > 1 and rng.random() < 0.25 + 0.5 * t:
        return options[1]
    return options[0]


def _choose_tonic(f: TextFeatures, rng: random.Random) -> int:
    pool = WARM_KEYS if f.warmth >= 0.5 else BRIGHT_KEYS
    return rng.choice(pool)


def _mood_tags(f: TextFeatures) -> List[str]:
    tags: List[str] = []
    if f.valence > 0.2:
        tags.append("bright")
    elif f.valence < -0.2:
        tags.append("dark")
    else:
        tags.append("bittersweet")
    if f.tension > 0.5:
        tags.append("tense")
    if f.arousal < 0.3:
        tags.append("still")
    if f.arousal > 0.65:
        tags += ["driving", "epic"]
    return tags


def _section_progression(st: Style, mode: str, f: TextFeatures, rng: random.Random, index: int,
                         n_sections: int, has_question: bool, exclude: Sequence[str]) -> Tuple[str, str, List[str]]:
    """Return (name, mode, numerals) for a section."""
    last = index == n_sections - 1
    if rng.random() < st.library_ratio:
        p = pick_progression(st.name, mode, rng, _mood_tags(f) + (["cadence"] if last else []), exclude)
        return p.name, p.mode, list(p.numerals)
    opts = HarmonyOptions(**{**st.harmony.__dict__})
    opts.length = 4 if f.density < 0.7 or rng.random() < 0.6 else 8
    if has_question:
        opts.cadence = "half"
    elif last:
        if opts.cadence == "none":
            opts.cadence = "authentic"
        if not is_major_like(mode) and f.valence > 0.25:
            opts.cadence = "picardy"
    elif opts.cadence == "none":
        opts.cadence = rng.choice(["none", "half", "deceptive"])
    harm_mode = "ionian" if is_major_like(mode) else "aeolian"
    nums = generate_functional(harm_mode, rng, opts)
    return f"generated ({opts.cadence} cadence)", harm_mode, nums


def _bass_pitch(pc: int) -> int:
    return 36 + ((pc - 36) % 12)


class _Arranger:
    def __init__(self, comp: Composition, st: Style, f: TextFeatures, rng: random.Random):
        self.comp, self.st, self.f, self.rng = comp, st, f, rng
        self.bpb = comp.time_signature[0]

    # -- helpers --------------------------------------------------------
    def chord_at(self, beat: float) -> ChordEvent:
        for c in self.comp.chords:
            if c.start <= beat < c.start + c.duration:
                return c
        return self.comp.chords[-1]

    def next_chord(self, c: ChordEvent) -> ChordEvent:
        for i, x in enumerate(self.comp.chords):
            if x is c and i + 1 < len(self.comp.chords):
                return self.comp.chords[i + 1]
        return c

    def bars(self, start: float, end: float):
        b = start
        while b < end - 1e-9:
            yield b
            b += self.bpb

    # -- layers -----------------------------------------------------------
    def pad(self, track: Track) -> None:
        mode = self.st.pad
        if mode == "none":
            return
        vel = 60 + int(30 * self.f.arousal)
        for c in self.comp.chords:
            if mode in ("sustain", "swell"):
                for p in c.voicing:
                    track.notes.append(Note(c.start, c.duration - 0.05, p, vel))
            elif mode == "stab":
                for bar in self.bars(c.start, c.start + c.duration):
                    for p in c.voicing:
                        track.notes.append(Note(bar, 1.5, p, vel))
                        track.notes.append(Note(bar + 2.5, 1.0, p, vel - 10))

    def keys(self, track: Track, start: float, end: float) -> None:
        mode = self.st.keys
        if mode == "none":
            return
        rng = self.rng
        ar = self.f.arousal
        vel = 58 + int(30 * ar)
        for bar in self.bars(start, end):
            c = self.chord_at(bar)
            v = sorted(c.voicing)
            if not v:
                continue
            if mode == "alberti":
                if self.bpb == 4:
                    pat = [v[0], v[-1], v[len(v) // 2], v[-1]] * 2
                else:
                    pat = [v[0], v[len(v) // 2], v[-1], v[len(v) // 2], v[-1], v[len(v) // 2]]
                for i, p in enumerate(pat):
                    track.notes.append(Note(bar + 0.5 * i, 0.5, p, vel - (0 if i % 2 == 0 else 8)))
            elif mode == "broken":
                seq = [v[0] - 12] + v + [v[0] + 12] if len(v) < 5 else [v[0] - 12] + v
                n = self.bpb * 2
                for i in range(n):
                    p = seq[i % len(seq)] if i < len(seq) or self.bpb == 4 else seq[(n - 1 - i) % len(seq)]
                    track.notes.append(Note(bar + 0.5 * i, 0.55, p, vel - (0 if i == 0 else 6)))
            elif mode == "arpeggio_up":
                step = 0.25 if self.comp.bpm < 112 else 0.5
                seq = v + [p + 12 for p in v]
                n = int(self.bpb / step)
                for i in range(n):
                    track.notes.append(Note(bar + step * i, step * 0.9, seq[i % len(seq)], vel - (0 if i % 4 == 0 else 10)))
            elif mode == "arpeggio_updown":
                seq = v + [v[0] + 12] + list(reversed(v[1:]))
                n = self.bpb * 2
                for i in range(n):
                    track.notes.append(Note(bar + 0.5 * i, 0.7, seq[i % len(seq)], vel - 8))
            elif mode == "pluck16":
                seq = [v[0], v[-1], v[len(v) // 2], v[-1] + 12]
                for i in range(self.bpb * 4):
                    track.notes.append(Note(bar + 0.25 * i, 0.22, seq[i % 4], vel - (0 if i % 4 == 0 else 12)))
            elif mode == "comp":
                if self.st.name == "jazz":
                    hits = rng.choice([[0.0, 2.5], [1.5, 3.0], [0.5, 2.0, 3.5], [0.0, 1.5, 3.0]])
                else:
                    hits = rng.choice([[0.5, 2.0, 3.5], [0.0, 1.5, 2.5], [0.0, 2.5]])
                for h in hits:
                    if h < self.bpb:
                        for p in v:
                            track.notes.append(Note(bar + h, 1.0, p, vel - rng.randint(0, 10)))
            elif mode == "stab_offbeat":
                if self.st.name == "house":
                    hits = [0.5, 1.5, 2.5, 3.5]
                    dur = 0.35
                else:
                    hits = [0.0, 2.5] if rng.random() < 0.7 else [0.0, 1.5, 2.5]
                    dur = 1.0
                for h in hits:
                    if h < self.bpb:
                        for p in v:
                            track.notes.append(Note(bar + h, dur, p, vel - rng.randint(0, 8)))

    def bass(self, track: Track, start: float, end: float) -> None:
        mode = self.st.bass
        vel = 70 + int(30 * self.f.arousal)
        rng = self.rng
        if mode == "drone":
            for c in self.comp.chords:
                if c.start >= start and c.start < end:
                    track.notes.append(Note(c.start, c.duration, c.bass, vel))
            return
        for bar in self.bars(start, end):
            c = self.chord_at(bar)
            root = c.bass
            fifth = root + 7
            if mode == "root_whole":
                track.notes.append(Note(bar, self.bpb, root, vel))
            elif mode == "root_fifth":
                if self.bpb == 4:
                    track.notes += [Note(bar, 2.0, root, vel), Note(bar + 2, 2.0, fifth if rng.random() < 0.7 else root, vel - 8)]
                else:
                    track.notes += [Note(bar, 1.5, root, vel), Note(bar + 2, 1.0, fifth, vel - 10)]
            elif mode == "octaves8":
                for i in range(self.bpb * 2):
                    track.notes.append(Note(bar + 0.5 * i, 0.45, root + (12 if i % 2 else 0), vel - (0 if i % 2 == 0 else 10)))
            elif mode == "offbeat8":
                for i in range(self.bpb):
                    track.notes.append(Note(bar + i + 0.5, 0.4, root, vel))
            elif mode == "rolling16":
                for i in range(self.bpb * 4):
                    p = root + (12 if i % 4 == 2 else 0)
                    track.notes.append(Note(bar + 0.25 * i, 0.2, p, vel - (0 if i % 4 == 0 else 8)))
            elif mode == "walking":
                nxt = self.next_chord(c) if bar + self.bpb >= c.start + c.duration else c
                third = root + (3 if c.quality.startswith("min") or c.quality in ("dim", "m7b5", "dim7") else 4)
                target = nxt.bass
                approach = target - 1 if rng.random() < 0.5 else target + 1
                seq = [root, third, fifth, approach] if self.bpb == 4 else [root, third, fifth]
                for i, p in enumerate(seq):
                    p = p if 34 <= p <= 55 else (p - 12 if p > 55 else p + 12)
                    track.notes.append(Note(bar + i, 0.95, p, vel - rng.randint(0, 8)))
            elif mode == "root_13":
                track.notes.append(Note(bar, 1.5, root, vel))
                track.notes.append(Note(bar + 2.5, 1.0, root if rng.random() < 0.7 else fifth, vel - 8))
                if rng.random() < 0.3 and self.bpb == 4:
                    track.notes.append(Note(bar + 3.5, 0.5, fifth - 12 + 12, vel - 16))

    def drums(self, track: Track, start: float, end: float, final_hit: bool) -> None:
        mode = self.st.drums
        if mode == "none":
            return
        K, S, C, H, OH = DRUM_NOTES["kick"], DRUM_NOTES["snare"], DRUM_NOTES["clap"], DRUM_NOTES["hat"], DRUM_NOTES["ohat"]
        rng = self.rng
        vel = 90 + int(25 * self.f.arousal)
        bars = list(self.bars(start, end))
        for bi, bar in enumerate(bars):
            last_bar = bi == len(bars) - 1
            if mode == "four_floor":
                for i in range(self.bpb):
                    track.notes.append(Note(bar + i, 0.25, K, vel))
                    track.notes.append(Note(bar + i + 0.5, 0.15, OH if (i == self.bpb - 1 and rng.random() < 0.5) else H, vel - 30))
                    if i in (1, 3):
                        track.notes.append(Note(bar + i, 0.25, C, vel - 10))
            elif mode == "trance":
                for i in range(self.bpb):
                    track.notes.append(Note(bar + i, 0.25, K, vel))
                    track.notes.append(Note(bar + i + 0.5, 0.15, OH, vel - 25))
                    if i in (1, 3):
                        track.notes.append(Note(bar + i, 0.25, C, vel - 5))
                    for q in (0.25, 0.75):
                        track.notes.append(Note(bar + i + q, 0.1, H, vel - 45))
                if last_bar and self.bpb == 4:
                    for q in range(8):   # snare roll into the next section
                        track.notes.append(Note(bar + 2 + q * 0.25, 0.1, S, vel - 40 + q * 5))
            elif mode == "lofi":
                kicks = [0.0, 2.5] if rng.random() < 0.6 else [0.0, 1.75, 2.5]
                for k in kicks:
                    track.notes.append(Note(bar + k, 0.25, K, vel - 10))
                for s in (1.0, 3.0):
                    if s < self.bpb:
                        track.notes.append(Note(bar + s, 0.25, S, vel - 15))
                for i in range(self.bpb * 2):
                    if rng.random() < 0.9:
                        track.notes.append(Note(bar + 0.5 * i, 0.12, H, vel - 45 - (0 if i % 2 == 0 else 12) + rng.randint(-5, 5)))
            elif mode == "backbeat":
                for k in ([0.0, 2.5] if rng.random() < 0.7 else [0.0, 2.0, 2.5]):
                    track.notes.append(Note(bar + k, 0.25, K, vel))
                for s in (1.0, 3.0):
                    if s < self.bpb:
                        track.notes.append(Note(bar + s, 0.3, S, vel))
                for i in range(self.bpb * 2):
                    track.notes.append(Note(bar + 0.5 * i, 0.12, H, vel - 35 - (0 if i % 2 == 0 else 10)))
        if final_hit:
            track.notes.append(Note(end, 0.5, K, vel))
            track.notes.append(Note(end, 0.5, DRUM_NOTES["ride"], vel - 10))


def generate(text: str, style: str = "auto", seed: Optional[int] = None, title: Optional[str] = None,
             tempo: Optional[float] = None, key: Optional[str] = None, mode: Optional[str] = None,
             drums: Optional[bool] = None) -> Composition:
    """Compose a piece from ``text``. See module docstring."""
    f = analyze(text)
    if not f.stanzas:
        raise ValueError("the text contains no singable syllables")
    seed = f.seed if seed is None else int(seed)
    rng = random.Random(seed)

    style_name = choose_style(f) if style == "auto" else style
    if style_name not in STYLES:
        raise KeyError(f"unknown style {style_name!r}; choose from {', '.join(STYLES)}")
    st = STYLES[style_name]
    if drums is not None and not drums:
        st = Style(**{**st.__dict__, "drums": "none"})

    colour_mode = mode or _choose_mode(f, st, rng)
    tonic = NOTE_TO_PC[key] if key else _choose_tonic(f, rng)
    prefer_flats = ((tonic if is_major_like(colour_mode) else (tonic + 3) % 12) in FLAT_KEYS)
    bpm = float(tempo) if tempo else round(st.tempo_range[0] + (st.tempo_range[1] - st.tempo_range[0]) * f.arousal + rng.uniform(-3, 3))
    ts = (4, 4)
    if len(st.time_signatures) > 1 and f.arousal < 0.45 and rng.random() < 0.35:
        ts = st.time_signatures[1]
    bpb = ts[0]

    timeline = Timeline(bpm=bpm, beats_per_bar=bpb, swing=st.swing if bpb == 4 else 0.5)
    comp = Composition(
        title=title or (f.stanzas[0].lines[0].text[:24]),
        style=style_name, key=pc_name(tonic, prefer_flats), tonic=tonic, mode=colour_mode,
        scale=[pc_name(p, prefer_flats) for p in scale_pcs(tonic, colour_mode)],
        bpm=bpm, time_signature=list(ts), timeline=timeline, seed=seed, features=f.to_dict(),
    )
    notes_on_theory: List[str] = []

    # ---- Sections -----------------------------------------------------------
    n_sections = len(f.stanzas)
    harm_mode = None
    plans: List[Tuple[LinePlan, float, bool, bool, str]] = []   # plan, start, antecedent, final, section mode
    chord_slots: List[Tuple[float, float, Chord, str, str]] = []  # start, duration, chord, numeral, progression name
    cursor = 0.0
    prev_name = ""
    first_prog: Optional[Tuple[str, str, List[str]]] = None

    def emit_cycle(start: float, mode_: str, nums: List[str], name: str, n_bars: int, align_end: bool = True) -> float:
        """Lay ``n_bars`` bars of the progression from ``start``. A partial last
        cycle uses the *final* chords (``align_end``) so a section ends on its
        cadence; the intro uses the first chords instead."""
        bpc = st.bars_per_chord
        cycle = len(nums) * bpc
        b = start
        remaining = int(n_bars)
        while remaining > 0:
            if remaining >= cycle:
                seq = list(nums)
            else:
                k = max(1, remaining // bpc)
                seq = list(nums[-k:]) if align_end else list(nums[:k])
            for numeral in seq:
                if remaining <= 0:
                    break
                bars_here = min(bpc, remaining)
                chord_slots.append((b, bars_here * bpb, parse_roman(numeral, tonic, mode_), numeral, name))
                b += bars_here * bpb
                remaining -= bars_here
        return b

    # Intro
    intro_start = cursor
    for si, stanza in enumerate(f.stanzas):
        has_q = any(l.ends_with_question for l in stanza.lines)
        name, sec_mode, nums = _section_progression(st, colour_mode, f, rng, si, n_sections, has_q, [prev_name])
        prev_name = name
        if first_prog is None:
            first_prog = (name, sec_mode, nums)
            # Intro: one cycle for grooves, two bars for classical styles.
            intro_bars = len(nums) * st.bars_per_chord if st.family != "classical" else min(2, len(nums))
            cursor = emit_cycle(cursor, sec_mode, nums, name + " (intro)", intro_bars, align_end=False)
            comp.sections.append(Section("intro", intro_start, cursor - intro_start, "intro", sec_mode, name, list(nums)))
        sec_start = cursor
        line_plans: List[LinePlan] = []
        for line in stanza.lines:
            line_plans.append(plan_rhythm(line, bpb, f.arousal, f.irregularity, rng))
        total_bars = sum(p.bars for p in line_plans)
        cycle = len(nums) * st.bars_per_chord
        if total_bars <= cycle:
            # Short stanza: at least one full cycle (or a 4-bar multiple ending on the cadence for long cycles).
            sec_bars = cycle if cycle <= 4 else max(4, math.ceil(total_bars / 4) * 4)
        elif total_bars <= cycle * 1.5:
            sec_bars = math.ceil(total_bars / cycle) * cycle
        else:
            sec_bars = total_bars
        sec_end = emit_cycle(sec_start, sec_mode, nums, name, sec_bars)
        b = sec_start
        for li, plan in enumerate(line_plans):
            antecedent = (li % 2 == 0) and li != len(line_plans) - 1
            final = si == n_sections - 1 and li == len(line_plans) - 1
            plans.append((plan, b, antecedent, final, sec_mode))
            b += plan.bars * bpb
        cursor = sec_end
        comp.sections.append(Section(f"stanza {si + 1}", sec_start, sec_end - sec_start, "verse", sec_mode, name,
                                     list(nums), "\n".join(l.text for l in stanza.lines)))
        if si == 0:
            harm_mode = sec_mode
            comp.mode = sec_mode
            comp.scale = [pc_name(p, prefer_flats) for p in scale_pcs(tonic, sec_mode)]
        notes_on_theory.append(
            f"Stanza {si + 1}: {name} in {pc_name(tonic, prefer_flats)} {sec_mode} -> " + " ".join(nums))

    # Outro: tonic chord held for two bars.
    assert first_prog is not None
    outro_start = cursor
    last_mode = comp.sections[-1].mode
    tonic_numeral = "I" if is_major_like(last_mode) else "i"
    if st.harmony.sevenths > 0.6:
        tonic_numeral += "maj7" if is_major_like(last_mode) else "7"
    if st.name == "ambient":
        tonic_numeral = "Isus2" if is_major_like(last_mode) else "isus2"
    chord_slots.append((cursor, 2 * bpb, parse_roman(tonic_numeral, tonic, last_mode), tonic_numeral, "outro"))
    cursor += 2 * bpb
    comp.sections.append(Section("outro", outro_start, cursor - outro_start, "outro", last_mode, "outro", [tonic_numeral]))
    if st.ritardando:
        timeline.rit_start = outro_start - bpb
        timeline.rit_end = cursor

    # ---- Chord events with voice leading (merge repeated chords) --------------
    prev_voicing: Optional[List[int]] = None
    for start, dur, chord, numeral, pname in chord_slots:
        if comp.chords and comp.chords[-1].symbol == chord.symbol(prefer_flats) and comp.chords[-1].numeral == numeral \
                and abs(comp.chords[-1].start + comp.chords[-1].duration - start) < 1e-6 and st.name in ("ambient",):
            comp.chords[-1].duration += dur
            continue
        max_voices = 4 if st.family == "classical" else 5
        voicing = voice_lead(prev_voicing, chord, low=52, high=76, max_voices=max_voices)
        prev_voicing = voicing
        comp.chords.append(ChordEvent(start, dur, chord.symbol(prefer_flats), numeral, chord.root, chord.quality,
                                      chord.pcs, voicing, _bass_pitch(chord.bass if chord.bass is not None else chord.root)))

    # ---- Tracks ----------------------------------------------------------------
    arr = _Arranger(comp, st, f, rng)
    patches = design_patches(f, st, rng)
    comp.patches = {role: p.to_dict() for role, p in patches.items()}
    total_end = cursor
    verse_start = comp.sections[1].start if len(comp.sections) > 1 else 0.0

    pad_tr = Track("Pad", "pad", patches["pad"].name, midi_channel=0, level=patches["pad"].level, pan=0.0)
    arr.pad(pad_tr)
    keys_tr = Track("Keys", "keys", patches["keys"].name, midi_channel=1, level=patches["keys"].level, pan=-0.25)
    arr.keys(keys_tr, intro_start if st.family != "classical" else verse_start, outro_start)
    bass_tr = Track("Bass", "bass", patches["bass"].name, midi_channel=2, level=patches["bass"].level)
    arr.bass(bass_tr, intro_start, total_end if st.bass == "drone" else outro_start)
    if st.bass != "drone":
        c = arr.chord_at(outro_start)
        bass_tr.notes.append(Note(outro_start, 2 * bpb, c.bass, 80))

    center = 67 + int(round(3 * f.valence)) + 12 * st.lead_octave_shift
    if st.name in ("folk", "classical", "romantic"):
        center += 2
    cfg = MelodyConfig(center=center, span=12, melody_scale=st.melody_scale, arousal=f.arousal,
                       valence=f.valence, tension=f.tension,
                       temperature=0.4 + 0.5 * f.irregularity)
    lead_tr = Track("Lead (text)", "lead", patches["lead"].name, midi_channel=3, level=patches["lead"].level, pan=0.1)
    by_mode: Dict[str, List[Tuple[LinePlan, float, bool, bool]]] = {}
    for plan, start, ant, fin, m in plans:
        by_mode.setdefault(m, []).append((plan, start, ant, fin))
    # Melody is generated in text order; section modes only change the scale.
    lead_notes: List[Note] = []
    for plan, start, ant, fin, m in plans:
        lead_notes += generate_melody([(plan, start, ant, fin)], comp.chords, tonic, m, bpb, cfg, rng)
    lead_tr.notes = lead_notes

    drum_tr = Track("Drums", "drums", "drums", midi_channel=9, level=0.8)
    arr.drums(drum_tr, intro_start, outro_start, final_hit=True)

    # Humanise timing (never before beat 0).
    if st.humanize > 0:
        for tr in (keys_tr, bass_tr, lead_tr):
            for n in tr.notes:
                n.start = max(0.0, n.start + rng.gauss(0, st.humanize))

    comp.tracks = [t for t in (pad_tr, keys_tr, bass_tr, lead_tr, drum_tr) if t.notes]

    # ---- Explain ------------------------------------------------------------------
    top = sorted([("valence", f.valence), ("arousal", f.arousal), ("tension", f.tension), ("warmth", f.warmth),
                  ("classical", f.classical), ("electronic", f.electronic)], key=lambda kv: -abs(kv[1] - 0.5))
    notes_on_theory.insert(0, f"Style '{style_name}' chosen from affect: " + ", ".join(f"{k}={v:.2f}" for k, v in top[:4]) + ".")
    notes_on_theory.insert(1, (f"Key {comp.key} {comp.mode} ({'major-like' if is_major_like(comp.mode) else 'minor-like'}), "
                               f"{int(bpm)} bpm, {ts[0]}/{ts[1]}, swing {st.swing:.2f}; "
                               f"{'warm (flat) key' if f.warmth >= 0.5 else 'bright (sharp) key'} from warmth {f.warmth:.2f}."))
    notes_on_theory.append(
        f"Melody: one note per syllable ({f.n_syllables} syllables), chord tones on strong beats, "
        f"{'pentatonic' if st.melody_scale == 'pentatonic' else st.melody_scale} scale, antecedent/consequent phrase endings, "
        f"leitmotif signatures per syllable; range centred on MIDI {center}.")
    notes_on_theory.append(
        f"Timbre from warmth {f.warmth:.2f} / arousal {f.arousal:.2f} / tension {f.tension:.2f}: "
        + ", ".join(f"{role} = {p.name}" for role, p in patches.items()) + " (full recipes under 'patches').")
    comp.notes_on_theory = notes_on_theory
    return comp
