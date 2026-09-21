"""Reading a text the way a composer reads a libretto.

Before a note is written, a composer asks: what is the *form* of this text
(a quatrain, a sonnet, a letter with an opening, a body and a farewell)?
Where is its emotional climax? Which images ask for word painting? This
module answers those questions from the analysed text and returns a
structured :class:`Interpretation` that the composer turns into dynamics,
register, texture, cadences and form, and that is reported back to the user
so every musical decision can be traced to the words.

Devices implemented (all standard techniques of common-practice text setting):

* **Emotional arc / climax** – per-stanza affect drives a dynamic plan
  (exposition -> development -> climax -> resolution) with the climax placed
  by intensity, biased toward the golden-ratio point of the piece.
* **起承转合 (qi-cheng-zhuan-he)** – the four-line stanza is treated as
  opening / continuation / turn / conclusion: the third line receives a
  harmonic and registral *turn*, the fourth the strongest cadence.
* **Word painting (音画)** – rising/falling/still/flowing/far/home/night/
  light imagery bends the phrase contour, rhythm and register of its line.
* **Poem-form detection** – 五言/七言 绝句/律诗, quatrains, sonnets, letters
  (salutation, body, farewell), free verse.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence

from .analysis import Line, Stanza, TextFeatures, affect_of

PAINTING = {
    "rise": ("上 高 飞 升 天 空 云 顶 望 攀 翔 举 起 冲 sky fly flies flying high higher climb climbs soar soars up upward rise rises rising mountain mountains ascend heaven heavens", "contour up"),
    "fall": ("下 落 沉 低 坠 泪 雨 埋 垂 降 跌 fall falls falling down downward sink sinks low lower drop drops tears rain bury descend descending plunge", "contour down"),
    "still": ("静 停 眠 睡 止 定 凝 息 still stillness silence silent stop stops sleep sleeps freeze frozen pause quiet hush", "longer notes, fewer ornaments"),
    "flow": ("河 流 水 风 江 海 波 溪 涌 淌 river rivers flow flows flowing stream streams wind winds sea waves wave breeze current tide", "stepwise legato motion"),
    "far": ("远 天涯 千里 万里 遥 隔 far distant distance away miles horizon faraway beyond remote", "wide leaps"),
    "home": ("家 归 回 故乡 返 home return returns returning back homeward homecoming", "line ends on the tonic"),
    "night": ("月 夜 星 梦 暗 黑 影 moon moonlight night nights star stars dream dreams dark shadow shadows midnight", "lower register, softer"),
    "light": ("火 光 燃 日 阳 亮 晨 曦 fire light lights burn burning sun sunlight dawn bright neon blaze glow shine", "higher register, louder"),
}
_PAINT_SETS = {k: set(v[0].split()) for k, v in PAINTING.items()}


@dataclass
class LineReading:
    index: int
    text: str
    devices: List[str] = field(default_factory=list)     # painting keys
    role: str = ""                                       # 起 承 转 合 or "" for non-quatrains
    open_ending: Optional[bool] = None                   # decided by the composer (tones / parity)


@dataclass
class StanzaReading:
    index: int
    label: str                  # form label: A, B, C ...
    valence: float
    arousal: float
    tension: float
    role: str                   # exposition | development | climax | resolution | salutation | farewell
    dynamic: float              # 0..1 target loudness / fullness
    lines: List[LineReading] = field(default_factory=list)


@dataclass
class Interpretation:
    poem_form: str
    form: str                   # e.g. "ABA", "AABA", "through"
    climax_index: int
    stanzas: List[StanzaReading]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for st in d["stanzas"]:
            for k in ("valence", "arousal", "tension", "dynamic"):
                st[k] = round(st[k], 3)
        return d


def detect_poem_form(stanzas: Sequence[Stanza], language: str) -> str:
    lengths = [len(l.syllables) for st in stanzas for l in st.lines]
    n = len(lengths)
    if not lengths:
        return "empty"
    if language == "zh" and n in (4, 8) and len(set(lengths)) == 1 and lengths[0] in (5, 7):
        kind = "绝句" if n == 4 else "律诗"
        return f"{'五言' if lengths[0] == 5 else '七言'}{kind}"
    if language == "zh" and len(set(lengths)) <= 2 and n >= 4 and max(lengths) <= 7:
        return "古体/齐言诗"
    first = stanzas[0].lines[0].text if stanzas and stanzas[0].lines else ""
    if re.match(r"^(亲爱的|敬爱的|尊敬的|dear|hi|hello|to )", first.strip().lower()):
        return "letter"
    if n == 14 and language == "en":
        return "sonnet"
    if all(len(st.lines) == 4 for st in stanzas):
        return "quatrains"
    if len(stanzas) == 1 and n <= 2:
        return "couplet" if n == 2 else "single line"
    return "free verse"


def plan_form(n: int, poem_form: str, rng_choice) -> str:
    """Return a form string with one letter per stanza."""
    if n == 1:
        return "A"
    if n == 2:
        return "AB"
    if n == 3:
        return "ABA"
    if n == 4:
        return rng_choice(["AABA", "ABAB"])
    letters = []
    for i in range(n):
        if i % 2 == 0:
            letters.append("A")
        else:
            letters.append("B" if (i // 2) % 2 == 0 else "C")
    if poem_form == "letter":
        letters[-1] = "A"          # a letter closes where it began
    return "".join(letters)


def _paint_line(line: Line) -> List[str]:
    text = line.text.lower()
    tokens = set(re.findall(r"[a-z']+", text))
    found = []
    for key, words in _PAINT_SETS.items():
        for w in words:
            if (re.search(r"[一-鿿]", w) and w in text) or (w in tokens):
                found.append(key)
                break
    return found


def interpret(f: TextFeatures, rng_choice, form: str = "auto") -> Interpretation:
    stanzas = f.stanzas
    n = len(stanzas)
    poem_form = detect_poem_form(stanzas, f.language)
    form_str = form if form != "auto" else plan_form(n, poem_form, rng_choice)
    if len(form_str) < n:
        form_str = (form_str * (n // len(form_str) + 1))[:n]
    form_str = form_str[:n]

    readings: List[StanzaReading] = []
    intensities: List[float] = []
    for i, st in enumerate(stanzas):
        text = "\n".join(l.text for l in st.lines)
        a = affect_of(text)
        # Blend with the whole-text affect so tiny stanzas do not swing wildly.
        w = min(1.0, sum(len(l.syllables) for l in st.lines) / 24.0)
        val = w * a["valence"] + (1 - w) * f.valence
        aro = w * a["arousal"] + (1 - w) * f.arousal
        ten = w * a["tension"] + (1 - w) * f.tension
        pos = i / max(1, n - 1)
        intensity = aro + 0.4 * abs(val) + 0.3 * ten - 0.35 * abs(pos - 0.62)
        intensities.append(intensity)
        lines = []
        for li, line in enumerate(st.lines):
            role = ""
            if len(st.lines) == 4:
                role = "起承转合"[li]
            lines.append(LineReading(li, line.text, _paint_line(line), role))
        readings.append(StanzaReading(i, form_str[i], val, aro, ten, "", 0.5, lines))

    climax = max(range(n), key=lambda i: intensities[i]) if n > 1 else 0
    for i, r in enumerate(readings):
        if n == 1:
            r.role, r.dynamic = "single", 0.6 + 0.3 * r.arousal
        elif i == climax:
            r.role, r.dynamic = "climax", 1.0
        elif i == n - 1:
            r.role, r.dynamic = "resolution", 0.45 + 0.3 * r.arousal
        elif i == 0:
            r.role, r.dynamic = "exposition", 0.5 + 0.3 * r.arousal
        elif i < climax:
            r.role, r.dynamic = "development", 0.55 + 0.35 * r.arousal + 0.15 * (i / max(1, climax))
        else:
            r.role, r.dynamic = "release", 0.5 + 0.3 * r.arousal
        if poem_form == "letter":
            if i == 0 and len(stanzas[0].lines) == 1:
                r.role, r.dynamic = "salutation", 0.4
            if i == n - 1 and n > 2 and sum(len(l.syllables) for l in stanzas[-1].lines) <= 14:
                r.role, r.dynamic = "farewell", 0.4
        r.dynamic = min(1.0, max(0.25, r.dynamic))

    notes = [f"Poem form: {poem_form}; musical form {form_str} (sections sharing a letter share harmony and the head motif)."]
    if n > 1:
        notes.append(f"Emotional arc: climax at stanza {climax + 1} (" + ", ".join(
            f"{r.role} {r.dynamic:.2f}" for r in readings) + ").")
    painted = [(r.index + 1, lr.index + 1, lr.devices) for r in readings for lr in r.lines if lr.devices]
    if painted:
        notes.append("Word painting: " + "; ".join(
            f"stanza {s} line {l}: {', '.join(PAINTING[d][1] for d in devs)}" for s, l, devs in painted[:8]))
    if any(len(st.lines) == 4 for st in stanzas):
        notes.append("Four-line stanzas follow 起承转合: line 3 turns (colour chord, higher register), line 4 concludes with the strongest cadence.")
    return Interpretation(poem_form, form_str, climax, readings, notes)
