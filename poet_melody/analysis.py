"""Text analysis: turn a letter, poem or article into musical *affect* features.

The features are deliberately simple and transparent so that the mapping from
words to music can be explained and tuned:

* ``valence``   -1..1   sad/dark ... happy/bright        -> mode, key colour
* ``arousal``    0..1   still/quiet ... energetic         -> tempo, envelopes, density
* ``tension``    0..1   resolved ... unresolved/questioning -> dissonance, cadence type
* ``warmth``     0..1   cold/distant ... warm/intimate    -> timbre (sine/triangle vs saw)
* ``classical``  0..1   how strongly the vocabulary evokes classical / literary imagery
* ``electronic`` 0..1   how strongly it evokes machines, cities, neon, future
* rhythm: syllable units, lines, stanzas, sentence-length variance

Chinese (CJK) and English are both supported; every CJK character is one
syllable, English words are split into syllables with a vowel-group heuristic.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Sequence

CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
CJK_PUNCT = "，。！？；：、（）「」『』《》〈〉“”‘’…—～·"
SENTENCE_END = re.compile(r"[。！？!?\.;；]+|…+|\.\.\.+")

# --- Lexicons ---------------------------------------------------------------
# Small, hand-curated, bilingual. Chinese entries match as substrings (no
# segmentation needed); English entries match whole lower-cased words.
POSITIVE_ZH = "爱 喜 乐 笑 光 暖 春 花 梦 希望 温柔 幸福 美 甜 阳光 拥抱 家 归 安 欢 舞 歌 生 星 海 蓝 晴 好 谢 亲爱 想念 微笑 柔 香 明亮 晨 桃 燕 鸟 蝶 糖 礼物 快乐 平安 温暖 依然 相信 永远 成长 青 绿".split()
NEGATIVE_ZH = "哭 泪 痛 伤 死 别 离 孤 冷 灰 忘 悲 愁 苦 恨 怕 空 断 失 落 暗 沉 病 老 远 无 伤心 寂寞 孤独 绝望 荒 坟 血 灭 碎 弃 逝 憾 悔 叹 殇 哀 泣 寒 枯 尘 夜".split()
POSITIVE_EN = "love loves loved joy light warm warmth spring bright hope hopes gentle happy sweet home embrace peace calm smile smiles laugh laughter dream dreams star stars sea blue sun sunlight kind thank thanks dear beloved bloom blossom tender grace glow soft golden morning garden bird birds song sing alive forever always believe grow green gift".split()
NEGATIVE_EN = "cry cried tears tear pain hurt death dead die dying goodbye lonely alone cold grey gray forget forgotten sorrow grief bitter hate fear afraid empty broken lost dark sink sick old far never nothing ache ashes grave blood ruin regret sigh mourn wound winter ghost silence silent gone".split()

HIGH_AROUSAL_ZH = "火 燃 跑 冲 狂 风暴 雷 心跳 疯 快 战 舞 闪 电 霓虹 呐喊 叫 燃烧 奔 撞 炸 鼓 震 醒 起来 冲刺 呼喊 热 沸".split()
LOW_AROUSAL_ZH = "静 慢 睡 眠 月 云 雾 湖 息 轻 悄 淡 缓 沉默 安静 寂静 微 柔 低语 呼吸 冬 雪 溪 浅 空 夜".split()
HIGH_AROUSAL_EN = "fire burn burning run running rush wild storm thunder heartbeat mad fast fight dance dancing flash electric city neon loud scream shout drum pulse race racing crash explode awake rise hot boil".split()
LOW_AROUSAL_EN = "sleep slow quiet still moon cloud clouds mist lake breath breathe hush soft whisper whispers gentle calm silent silence winter snow stream shallow drift float linger".split()

TENSION_ZH = "但 却 可是 然而 如果 为什么 为何 是否 难道 也许 或许 不知 不能 无法 还是 直到 等待 犹豫 徘徊 矛盾".split()
TENSION_EN = "but yet however if why whether maybe perhaps unless until wait waiting hesitate torn doubt question unsure cannot".split()

WARM_ZH = "家 妈妈 母亲 父亲 爸爸 你 我们 拥抱 手 怀 亲 温 暖 灯 炉 汤 茶 饭 信 陪 伴 老友 兄弟 姐妹 孩子 童年".split()
COLD_ZH = "冰 霜 雪 铁 钢 石 墙 玻璃 远方 陌生 机器 荒野 孤岛 深海 太空 荒漠 雾".split()
WARM_EN = "home mother mom father dad you we us embrace hands hold arms kiss warm lamp hearth soup tea bread letter company friend brother sister child childhood hug".split()
COLD_EN = "ice frost snow iron steel stone wall glass distant stranger machine wasteland island ocean space desert fog concrete".split()

CLASSICAL_ZH = "月 花 酒 江 山 风 雪 古 琴 诗 词 楼 舟 桥 柳 燕 雁 松 竹 梅 菊 亭 帘 烛 墨 笔 砚 卷 客 故人 明月 长亭 千里 万里 天涯 春秋 苍 悠 兮 之 乎 者 也 焉 矣 君 吾 汝 尔".split()
CLASSICAL_EN = "thee thou thy thine hath doth ere o'er whilst sonnet muse verse lyre nightingale meadow moonlight lament yonder hither fair maiden knight harp chapel candle quill parchment".split()
ELECTRONIC_ZH = "霓虹 城市 电 屏幕 机器 信号 数据 像素 未来 太空 星际 赛博 网络 代码 电流 频率 光纤 芯片 合成 键盘 引擎 高速 地铁 车站 夜店 灯光 闪烁 电台".split()
ELECTRONIC_EN = "neon city electric screen screens machine signal data pixel pixels future space synth synthesizer code wire wires glow static cyber network circuit frequency chip engine highway subway station club strobe radio digital laser chrome".split()


@dataclass
class Line:
    text: str
    syllables: List[str]
    ends_with_question: bool = False
    ends_with_exclamation: bool = False
    ends_with_ellipsis: bool = False


@dataclass
class Stanza:
    lines: List[Line]


@dataclass
class TextFeatures:
    language: str                 # "zh", "en" or "mixed"
    n_chars: int
    n_syllables: int
    n_lines: int
    n_stanzas: int
    valence: float
    arousal: float
    tension: float
    warmth: float
    classical: float
    electronic: float
    density: float                # average syllables per line, normalised 0..1
    irregularity: float           # variance of line lengths, normalised 0..1
    question_ratio: float
    exclamation_ratio: float
    seed: int
    keyword_hits: Dict[str, List[str]] = field(default_factory=dict)
    stanzas: List[Stanza] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("stanzas")
        for k in ("valence", "arousal", "tension", "warmth", "classical", "electronic",
                  "density", "irregularity", "question_ratio", "exclamation_ratio"):
            d[k] = round(d[k], 3)
        return d


# --- Helpers -----------------------------------------------------------------

def text_seed(text: str) -> int:
    """Deterministic 32-bit seed derived from the text (same text -> same piece)."""
    h = hashlib.sha256(text.strip().encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")


def token_seed(token: str) -> int:
    h = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")


def detect_language(text: str) -> str:
    cjk = len(CJK_RE.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk == 0 and latin == 0:
        return "en"
    ratio = cjk / (cjk + latin)
    if ratio > 0.7:
        return "zh"
    if ratio < 0.3:
        return "en"
    return "mixed"


_VOWEL_GROUPS = re.compile(r"[aeiouy]+")


def english_syllables(word: str) -> List[str]:
    """Split an English word into syllable-ish chunks (heuristic)."""
    w = word.lower()
    w = re.sub(r"[^a-z']", "", w)
    if not w:
        return []
    groups = list(_VOWEL_GROUPS.finditer(w))
    count = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and count > 1:
        count -= 1
    if w.endswith("ed") and count > 1 and not w.endswith(("ted", "ded")):
        count -= 1
    count = max(1, count)
    if count == 1:
        return [w]
    # Cut roughly at vowel-group boundaries for the syllable texts.
    cuts: List[str] = []
    last = 0
    boundaries = [g.end() for g in groups][: count - 1]
    for b in boundaries:
        # include following consonant if there is one
        nxt = b + 1 if b < len(w) and w[b] not in "aeiouy" and b + 1 < len(w) else b
        cuts.append(w[last:nxt])
        last = nxt
    cuts.append(w[last:])
    return [c for c in cuts if c]


def split_syllables(line: str) -> List[str]:
    """Return the singable units of a line: CJK characters and English syllables."""
    out: List[str] = []
    for token in re.findall(r"[㐀-䶿一-鿿豈-﫿]|[A-Za-z']+|\d+", line):
        if CJK_RE.match(token):
            out.append(token)
        elif token.isdigit():
            out.extend(list(token))
        else:
            out.extend(english_syllables(token))
    return out


def _count_hits(text_lower: str, words_zh: Sequence[str], words_en: Sequence[str], en_tokens: Sequence[str]) -> List[str]:
    hits: List[str] = []
    for w in words_zh:
        c = text_lower.count(w)
        hits.extend([w] * c)
    en_set = set(words_en)
    for t in en_tokens:
        if t in en_set:
            hits.append(t)
    return hits


def _sigmoid_scale(x: float, k: float) -> float:
    """Map a non-negative count to 0..1 with saturation at ~k."""
    return 1.0 - math.exp(-x / k) if k > 0 else 0.0


def parse_structure(text: str) -> List[Stanza]:
    stanzas: List[Stanza] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines: List[Line] = []
        for raw in block.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            # Long prose lines: split into sentences so each sentence sings as a phrase.
            pieces = [p for p in re.split(r"(?<=[。！？!?；;])\s*", raw) if p.strip()]
            for piece in pieces:
                syl = split_syllables(piece)
                if not syl:
                    continue
                lines.append(Line(
                    text=piece.strip(),
                    syllables=syl,
                    ends_with_question=bool(re.search(r"[?？]\s*$", piece)),
                    ends_with_exclamation=bool(re.search(r"[!！]\s*$", piece)),
                    ends_with_ellipsis=bool(re.search(r"(…|\.\.\.)\s*$", piece)),
                ))
        if lines:
            stanzas.append(Stanza(lines))
    # Very long single stanzas are broken into 4-line groups (musical periods).
    out: List[Stanza] = []
    for st in stanzas:
        if len(st.lines) > 8:
            for i in range(0, len(st.lines), 4):
                out.append(Stanza(st.lines[i:i + 4]))
        else:
            out.append(st)
    return out


def analyze(text: str) -> TextFeatures:
    text = text.replace("\r\n", "\n")
    stanzas = parse_structure(text)
    lower = text.lower()
    en_tokens = re.findall(r"[a-z']+", lower)
    language = detect_language(text)

    pos = _count_hits(lower, POSITIVE_ZH, POSITIVE_EN, en_tokens)
    neg = _count_hits(lower, NEGATIVE_ZH, NEGATIVE_EN, en_tokens)
    hi = _count_hits(lower, HIGH_AROUSAL_ZH, HIGH_AROUSAL_EN, en_tokens)
    lo = _count_hits(lower, LOW_AROUSAL_ZH, LOW_AROUSAL_EN, en_tokens)
    ten = _count_hits(lower, TENSION_ZH, TENSION_EN, en_tokens)
    warm = _count_hits(lower, WARM_ZH, WARM_EN, en_tokens)
    cold = _count_hits(lower, COLD_ZH, COLD_EN, en_tokens)
    cla = _count_hits(lower, CLASSICAL_ZH, CLASSICAL_EN, en_tokens)
    ele = _count_hits(lower, ELECTRONIC_ZH, ELECTRONIC_EN, en_tokens)

    n_syl = sum(len(l.syllables) for st in stanzas for l in st.lines)
    n_lines = sum(len(st.lines) for st in stanzas)
    per_100 = 100.0 / max(n_syl, 20)

    # Valence: smoothed ratio, with a little pull towards neutral for tiny texts.
    valence = (len(pos) - len(neg)) / (len(pos) + len(neg) + 2.0)

    n_excl = len(re.findall(r"[!！]", text))
    n_q = len(re.findall(r"[?？]", text))
    n_ell = len(re.findall(r"…|\.\.\.", text))
    caps = len(re.findall(r"[A-Z]", text))
    caps_ratio = caps / max(1, len(re.findall(r"[A-Za-z]", text)))
    line_lengths = [len(l.syllables) for st in stanzas for l in st.lines] or [0]
    mean_len = sum(line_lengths) / len(line_lengths)

    arousal = 0.35
    arousal += 0.35 * _sigmoid_scale((len(hi) + 1.5 * n_excl) * per_100, 4.0)
    arousal -= 0.30 * _sigmoid_scale((len(lo) + 0.7 * n_ell) * per_100, 4.0)
    arousal += 0.10 * min(1.0, caps_ratio * 4)          # SHOUTING
    arousal += 0.10 * (1.0 - min(1.0, mean_len / 14.0))  # short lines feel urgent
    arousal = min(1.0, max(0.0, arousal))

    tension = 0.15
    tension += 0.45 * _sigmoid_scale((len(ten) + 2.0 * n_q) * per_100, 4.0)
    tension += 0.15 * _sigmoid_scale(n_ell * per_100, 2.0)
    tension += 0.15 * (1 - abs(valence))  # ambivalent texts are tense
    tension = min(1.0, max(0.0, tension))

    warmth = 0.5 + 0.5 * (len(warm) - len(cold)) / (len(warm) + len(cold) + 2.0)
    warmth = 0.7 * warmth + 0.3 * (0.5 + 0.5 * valence)
    classical = _sigmoid_scale(len(cla) * per_100, 5.0)
    electronic = _sigmoid_scale(len(ele) * per_100, 4.0)

    density = min(1.0, mean_len / 16.0)
    var = sum((x - mean_len) ** 2 for x in line_lengths) / len(line_lengths)
    irregularity = min(1.0, math.sqrt(var) / max(mean_len, 1.0))

    return TextFeatures(
        language=language,
        n_chars=len(text),
        n_syllables=n_syl,
        n_lines=n_lines,
        n_stanzas=len(stanzas),
        valence=valence,
        arousal=arousal,
        tension=tension,
        warmth=min(1.0, max(0.0, warmth)),
        classical=classical,
        electronic=electronic,
        density=density,
        irregularity=irregularity,
        question_ratio=n_q / max(1, n_lines),
        exclamation_ratio=n_excl / max(1, n_lines),
        seed=text_seed(text),
        keyword_hits={
            "positive": pos, "negative": neg, "high_arousal": hi, "low_arousal": lo,
            "tension": ten, "warm": warm, "cold": cold, "classical": cla, "electronic": ele,
        },
        stanzas=stanzas,
    )
