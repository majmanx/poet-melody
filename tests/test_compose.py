import json

import pytest

from poet_melody import STYLES, generate, composition_to_midi
from poet_melody.theory import SCALES

MOON = "床前明月光，\n疑是地上霜。\n举头望明月，\n低头思故乡。\n"
LETTER = "Dear friend,\n\nThe winter has been long and quiet here.\nWill you come home in spring?\n"


def test_deterministic():
    a, b = generate(MOON), generate(MOON)
    assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)
    assert generate(MOON, seed=5).seed == 5


def test_lead_has_one_note_per_syllable_with_lyrics():
    comp = generate(MOON, style="classical")
    lead = comp.track("lead")
    assert lead is not None
    assert [n.lyric for n in lead.notes if n.lyric] == list("床前明月光疑是地上霜举头望明月低头思故乡")
    assert all(n.duration > 0 for n in lead.notes)
    starts = [n.start for n in lead.notes if n.lyric]
    assert starts == sorted(starts)


def test_melody_respects_scale_and_leaps():
    comp = generate(MOON, style="folk")
    lead = comp.track("lead")
    tonic = comp.tonic
    from poet_melody.theory import is_major_like
    pent = {(tonic + i) % 12 for i in SCALES["major_pentatonic" if is_major_like(comp.mode) else "minor_pentatonic"]}
    chord_pcs = {pc for c in comp.chords for pc in c.pcs}
    sung = [n for n in lead.notes if n.lyric]
    for n in sung:
        assert n.pitch % 12 in pent | chord_pcs
    for a, b in zip(sung, sung[1:]):
        assert abs(a.pitch - b.pitch) <= 12


@pytest.mark.parametrize("style", list(STYLES))
def test_every_style_generates_and_serialises(style):
    comp = generate(LETTER, style=style)
    d = comp.to_dict()
    s = json.dumps(d, ensure_ascii=False)
    assert d["style"] == style
    assert comp.total_seconds > 5
    assert {"pad", "keys", "bass", "lead"} <= set(comp.patches)
    assert comp.track("lead") is not None
    assert comp.sections[0].kind == "intro" and comp.sections[-1].kind == "outro"
    assert all(c.duration > 0 for c in comp.chords)
    # chords tile the timeline without gaps
    for a, b in zip(comp.chords, comp.chords[1:]):
        assert abs(a.start + a.duration - b.start) < 1e-6
    midi = composition_to_midi(comp)
    assert midi[:4] == b"MThd" and midi.count(b"MTrk") == len(comp.tracks) + 1


def test_overrides():
    comp = generate(LETTER, style="synthwave", key="F#", mode="aeolian", tempo=100, drums=False)
    assert comp.key == "F#" and comp.mode == "aeolian" and comp.bpm == 100
    assert comp.track("drums") is None


def test_timeline_swing_and_rit_monotonic():
    comp = generate(MOON, style="classical")
    tl = comp.timeline
    prev = -1.0
    b = 0.0
    while b < comp.total_beats:
        t = tl.seconds(b)
        assert t > prev
        prev = t
        b += 0.125


def test_empty_text_rejected():
    with pytest.raises(ValueError):
        generate("... !!! ???")
