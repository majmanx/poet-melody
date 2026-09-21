import pytest

from poet_melody.theory import (Chord, chord_from_symbol, close_voicing, parse_roman, scale_pcs, spread_voicing,
                                voice_lead, midi_name)


def test_scales():
    assert scale_pcs(0, "ionian") == [0, 2, 4, 5, 7, 9, 11]
    assert scale_pcs(9, "aeolian") == [9, 11, 0, 2, 4, 5, 7]
    assert scale_pcs(0, "gong") == [0, 2, 4, 7, 9]
    assert scale_pcs(0, "yu") == [0, 3, 5, 7, 10]


@pytest.mark.parametrize("numeral,tonic,mode,symbol", [
    ("I", 0, "ionian", "C"), ("ii7", 0, "ionian", "Dm7"), ("V7", 0, "ionian", "G7"),
    ("bVImaj7", 0, "ionian", "G#maj7"), ("viiø7", 0, "ionian", "Bm7b5"), ("V7/V", 0, "ionian", "D7"),
    ("i", 9, "aeolian", "Am"), ("VI", 9, "aeolian", "F"), ("VII", 9, "aeolian", "G"), ("V", 9, "aeolian", "E"),
    ("bII", 9, "aeolian", "A#"), ("IV", 2, "dorian", "G"), ("II", 0, "lydian", "D"),
    ("#iv°7", 0, "ionian", "F#dim7"), ("Isus2", 0, "ionian", "Csus2"), ("V13", 5, "ionian", "C13"),
])
def test_parse_roman(numeral, tonic, mode, symbol):
    assert parse_roman(numeral, tonic, mode).symbol() == symbol


def test_parse_roman_rejects_garbage():
    with pytest.raises(ValueError):
        parse_roman("VIII", 0, "ionian")
    with pytest.raises(ValueError):
        parse_roman("Ixyz", 0, "ionian")


def test_chord_symbol_roundtrip():
    c = chord_from_symbol("Bbm7b5")
    assert c.root == 10 and c.quality == "m7b5"
    assert chord_from_symbol("G7/B").symbol() == "G7/B"


def test_voice_leading_is_smooth_and_complete():
    prev = None
    chords = [parse_roman(n, 0, "ionian") for n in "I vi IV V I".split()]
    for c in chords:
        v = voice_lead(prev, c)
        assert set(p % 12 for p in v) == set(c.pcs)
        assert v == sorted(v)
        if prev is not None:
            assert sum(abs(a - b) for a, b in zip(v, prev)) <= 12
        prev = v


def test_voice_leading_handles_size_changes():
    v3 = voice_lead(None, parse_roman("I", 0, "ionian"))
    v4 = voice_lead(v3, parse_roman("ii7", 0, "ionian"))
    v3b = voice_lead(v4, parse_roman("V", 0, "ionian"))
    assert len(v3) == 3 and len(v4) == 4 and len(v3b) == 3


def test_spread_and_close_voicing():
    c = parse_roman("i", 9, "aeolian")
    assert spread_voicing(c)[0] % 12 == 9
    v = close_voicing(c, 57, 76)
    assert v[0] == 57 and v == sorted(v) and set(p % 12 for p in v) == set(c.pcs)
    assert midi_name(60) == "C4"
