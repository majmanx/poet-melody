import random

from poet_melody import generate
from poet_melody.analysis import analyze
from poet_melody.interpret import detect_poem_form, interpret, plan_form
from poet_melody.tones import describe, phrase_openness, tone_direction, tone_of, tones_of

MOON = "床前明月光，\n疑是地上霜。\n举头望明月，\n低头思故乡。\n"
LETTER = "亲爱的你：\n\n好久不见。城市的霓虹还在闪烁。\n你还好吗？\n\n愿你平安。\n"


def test_tone_table():
    assert tones_of(list("床前明月光")) == [2, 2, 2, 4, 1]
    assert tone_of("吗") == 5 and tone_of("a") == 0 and tone_of("床前") == 0
    assert "月4" in describe(list("明月"))


def test_tone_direction_and_openness():
    assert tone_direction(4, 1) == 1          # falling tone to high level: melody must rise
    assert tone_direction(1, 3) == -1         # high level to low dipping: melody must fall
    assert tone_direction(2, 2) == 0          # two rising tones: free
    assert tone_direction(0, 1) == 0
    assert phrase_openness(1) is True and phrase_openness(4) is False and phrase_openness(5) is None


def _violations(comp):
    sung = [n for n in comp.track("lead").notes if n.lyric]
    tot = viol = 0
    for a, b in zip(sung, sung[1:]):
        d = tone_direction(a.tone, b.tone)
        if d:
            tot += 1
            s = (b.pitch > a.pitch) - (b.pitch < a.pitch)
            viol += s == -d
    return tot, viol


def test_tone_constraint_reduces_daozi():
    with_tones = generate(MOON, style="folk")
    without = generate(MOON, style="folk", tone_weight=0)
    t1, v1 = _violations(with_tones)
    t0, v0 = _violations(without)
    assert t1 == t0 > 0
    assert v1 <= v0 and v1 <= t1 * 0.3
    # tones are reported on the notes and ornaments exist for zh text
    lead = with_tones.track("lead")
    assert all(n.tone in range(0, 6) for n in lead.notes)
    assert any(not n.lyric for n in lead.notes)


def test_poem_form_and_form_plan():
    f = analyze(MOON)
    assert detect_poem_form(f.stanzas, f.language) == "五言绝句"
    assert detect_poem_form(analyze(LETTER).stanzas, "zh") == "letter"
    assert plan_form(1, "free verse", random.Random(0).choice) == "A"
    assert plan_form(3, "free verse", random.Random(0).choice) == "ABA"
    assert plan_form(4, "free verse", lambda opts: opts[0]) == "AABA"
    assert plan_form(5, "letter", lambda opts: opts[0]) == "ABACA"


def test_interpretation_quatrain_roles_and_turn_chord():
    comp = generate(MOON, style="classical")
    roles = [l["role"] for l in comp.interpretation["stanzas"][0]["lines"]]
    assert roles == ["起", "承", "转", "合"]
    assert any(c.numeral.endswith("*") for c in comp.chords)          # the 转 colour chord
    assert comp.form == "A"


def test_form_reprise_shares_progression_and_motif():
    text = "\n\n".join(["春风吹过山谷。\n花开满地。", "冬雪落在屋顶！\n炉火轻轻。", "又是春天了。\n燕子回来。"])
    comp = generate(text, style="classical", form="ABA")
    verses = [s for s in comp.sections if s.kind == "verse"]
    assert [s.label for s in verses] == ["A", "B", "A"]
    assert verses[0].numerals == verses[2].numerals and verses[0].progression == verses[2].progression
    assert any("Head motif" in n for n in comp.notes_on_theory)
    assert set(comp.interpretation) >= {"poem_form", "form", "climax_index", "stanzas", "notes"}


def test_relative_key_modulation_possible():
    text = "\n\n".join(["The morning is bright and warm.\nWe sing in the garden.", "But the night is cold and far.\nWhy did you go?", "The morning returns.\nWe sing again."])
    seen = set()
    for seed in range(8):
        comp = generate(text, style="classical", form="ABA", seed=seed)
        seen.add(tuple(s.key for s in comp.sections if s.kind == "verse"))
    assert any(k[0] != k[1] for k in seen)        # some seeds modulate the B section
    assert all(k[0] == k[2] for k in seen)         # A sections always share the home key


def test_affect_override_changes_mode_choice():
    happy = generate("hello world", style="classical", affect={"valence": 0.95, "arousal": 0.9})
    sad = generate("hello world", style="classical", affect={"valence": -0.95, "arousal": 0.1})
    assert happy.features["valence"] > sad.features["valence"]
    assert happy.bpm > sad.bpm
