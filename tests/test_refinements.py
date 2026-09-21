import random

from poet_melody import generate
from poet_melody.melody import _avoid_notes, _stability
from poet_melody.progressions import HarmonyOptions, generate_functional
from poet_melody.theory import is_major_like, parse_roman, voice_lead

HAPPY = "Sunlight on the water, laughter in the garden!\nWe run, we dance, we sing all night.\n\nThe city glows with neon and heartbeat.\nNothing can stop us now."


def test_extended_chords_drop_the_fifth():
    c = parse_roman("Imaj9", 0, "ionian")
    assert c.voicing_pcs(4) == [0, 4, 11, 2]          # root, third, seventh, ninth
    assert c.voicing_pcs(3) == [4, 11, 2]             # then rootless
    assert parse_roman("I", 0, "ionian").voicing_pcs(4) == [0, 4, 7]
    v = voice_lead(None, parse_roman("ii9", 0, "ionian"), max_voices=4)
    assert len(v) == 4 and 9 not in {p % 12 for p in v}   # no fifth (A) in Dm9


def test_no_diminished_chords_when_disabled():
    rng = random.Random(5)
    for mode in ("ionian", "aeolian"):
        for _ in range(60):
            nums = generate_functional(mode, rng, HarmonyOptions(length=8, cadence="none", diminished=False))
            assert not any("°" in n for n in nums)


def test_borrowed_tonic_never_resolves_a_dominant():
    rng = random.Random(9)
    for _ in range(200):
        nums = generate_functional("ionian", rng, HarmonyOptions(length=8, cadence="none", mixture=1.0))
        for a, b in zip(nums, nums[1:]):
            if a.startswith("V") and not a.startswith("VI"):
                assert not b.startswith("bIII")          # bVI may follow V as a borrowed subdominant


def test_avoid_notes_and_stability():
    # A minor scale against E major (V): the G natural clashes with G#, the A with G# too.
    assert _avoid_notes([9, 11, 0, 2, 4, 5, 7], [4, 8, 11]) == {7, 9}
    assert _avoid_notes([0, 2, 4, 5, 7, 9, 11], [0, 4, 7]) == set()
    assert _stability(0, [0, 4, 7, 11, 2]) == 1.0 > _stability(11, [0, 4, 7, 11, 2]) > _stability(2, [0, 4, 7, 11, 2])


def test_trance_stays_in_one_mode_family():
    for seed in range(6):
        comp = generate(HAPPY, style="trance", seed=seed)
        assert not is_major_like(comp.mode)
        verses = [s for s in comp.sections if s.kind == "verse"]
        assert all(not is_major_like(s.mode) for s in verses)
        assert all(s.key == comp.key for s in verses)
        assert comp.sections[-1].numerals == ["i"]


def test_groove_styles_have_no_diminished_chords():
    for style in ("lofi", "trance", "house", "synthwave", "pop"):
        for seed in range(3):
            comp = generate(HAPPY, style=style, seed=seed)
            assert not any(c.quality in ("dim", "dim7", "m7b5") for c in comp.chords), style


def test_phrase_endings_prefer_triad_tones():
    comp = generate(open("examples/letter_zh.txt", encoding="utf-8").read(), style="lofi")
    sung = [n for n in comp.track("lead").notes if n.lyric]
    ends = []
    for i, n in enumerate(sung):
        last = i + 1 == len(sung) or sung[i + 1].start - (n.start + n.duration) > 0.4
        if last:
            chord = next(c for c in comp.chords if c.start <= n.start < c.start + c.duration)
            ends.append(n.pitch % 12 in chord.pcs[:3] or n.pitch % 12 not in chord.pcs)
    assert sum(ends) >= 0.85 * len(ends)
