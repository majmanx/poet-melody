import random

from poet_melody.progressions import LIBRARY, HarmonyOptions, all_styles, generate_functional, pick_progression
from poet_melody.theory import parse_roman


def test_library_parses_in_its_mode():
    for p in LIBRARY:
        chords = p.chords(0)
        assert len(chords) == len(p.numerals)


def test_pick_progression_matches_mode_family():
    rng = random.Random(1)
    for style in all_styles():
        for mode in ("ionian", "aeolian"):
            p = pick_progression(style, mode, rng)
            assert p.style == style


def test_generated_cadences():
    rng = random.Random(7)
    for mode in ("ionian", "aeolian"):
        for _ in range(30):
            nums = generate_functional(mode, rng, HarmonyOptions(length=4, sevenths=0.5, secondary=0.4, cadence="authentic"))
            assert nums[-1].lstrip("b#").startswith(("I", "i"))
            assert nums[-2].startswith(("V", "bII"))          # dominant or tritone sub
            for n in nums:
                parse_roman(n, 0, mode)
            half = generate_functional(mode, rng, HarmonyOptions(length=4, cadence="half"))
            assert half[-1].startswith("V")
            dec = generate_functional(mode, rng, HarmonyOptions(length=4, cadence="deceptive"))
            assert dec[-1] in ("vi", "VI", "vi7", "VImaj7")
            pic = generate_functional("aeolian", rng, HarmonyOptions(length=4, cadence="picardy"))
            assert pic[-1] == "I"


def test_generated_starts_on_tonic_and_avoids_static_repeats():
    rng = random.Random(3)
    for _ in range(50):
        nums = generate_functional("ionian", rng, HarmonyOptions(length=8, cadence="none"))
        assert nums[0] == "I"
        assert not any(a == b for a, b in zip(nums, nums[1:])) or len(set(nums)) == 1
