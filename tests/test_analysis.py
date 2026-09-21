from poet_melody.analysis import analyze, english_syllables, split_syllables, detect_language, text_seed


def test_language_and_syllables():
    assert detect_language("床前明月光") == "zh"
    assert detect_language("hello there") == "en"
    assert split_syllables("床前明月光，") == list("床前明月光")
    assert english_syllables("beautiful") == ["beaut", "if", "ul"]
    assert english_syllables("the") == ["the"]
    assert len(split_syllables("The city is on fire tonight!")) == 8


def test_affect_direction():
    happy = analyze("阳光，温暖，微笑，我们一起回家。\n春天的花开了，鸟儿在歌唱。")
    sad = analyze("孤独的夜，冰冷的雨。\n泪水，离别，遗忘，死亡。")
    assert happy.valence > 0.3 > sad.valence
    assert happy.warmth > sad.warmth
    loud = analyze("RUN! FIRE! The storm is here, dance, scream, burn!")
    calm = analyze("quiet moon, soft mist on the lake, slow breath, sleep...")
    assert loud.arousal > calm.arousal
    question = analyze("为什么？你是否还在？如果……也许。")
    assert question.tension > calm.tension


def test_structure_and_determinism():
    f = analyze("a b c\nd e f\n\ng h i")
    assert f.n_stanzas == 2 and f.n_lines == 3
    assert text_seed("x") == text_seed("x ") == text_seed("x")
    assert analyze("hello").seed == analyze("hello").seed


def test_long_prose_is_split_into_sentences():
    f = analyze("好久不见。城市的霓虹还在闪烁。地铁在深夜依然呼啸。")
    assert f.n_lines == 3
