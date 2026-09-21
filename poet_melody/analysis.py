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
from typing import Dict, List, Optional, Sequence, Tuple

CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
CJK_PUNCT = "，。！？；：、（）「」『』《》〈〉“”‘’…—～·"
SENTENCE_END = re.compile(r"[。！？!?\.;；]+|…+|\.\.\.+")

# --- Lexicons ---------------------------------------------------------------
# Hand-curated, bilingual, deliberately transparent. Chinese entries match as
# substrings (longest entries first, so 伤心 wins over 心), English entries match
# whole lower-cased words. A preceding negation (不/没/无/非, not/no/never/without)
# flips polarity; a preceding intensifier (很/非常/太/最, very/so/deeply) scales it.
POSITIVE_ZH = """爱 喜 乐 笑 光 暖 春 花 梦 希望 温柔 幸福 美 甜 阳光 拥抱 家 归 安 欢 舞 歌 生 星 海 蓝 晴 好 谢 亲爱 想念
微笑 柔 香 明亮 晨 桃 燕 鸟 蝶 糖 礼物 快乐 平安 温暖 依然 相信 永远 成长 青 绿 喜欢 感动 珍惜 陪伴 祝福 自由 勇敢 灿烂
清澈 宁静 甘 蜜 暖阳 晨光 彩虹 拥 亲吻 欣喜 欢喜 欢乐 幸运 圆满 团圆 重逢 盛开 绽放 明媚 灵动 温情 慈 善 美好 顺利 安心 安然
安稳 舒展 轻盈 飞翔 翱翔 微风 春风 暖风 晴朗 皎洁 璀璨 辉煌 荣耀 胜利 收获 丰盈 富足 感恩 谢谢 可爱 迷人 动人 心动 心安 心暖""".split()
NEGATIVE_ZH = """哭 泪 痛 伤 死 别 离 孤 冷 灰 忘 悲 愁 苦 恨 怕 空 断 失 落 暗 沉 病 老 远 无 伤心 寂寞 孤独 绝望 荒 坟 血 灭 碎 弃
逝 憾 悔 叹 殇 哀 泣 寒 枯 尘 夜 悲伤 忧伤 忧愁 哀愁 哀伤 惆怅 落寞 孤单 无助 无奈 疲惫 迷茫 恐惧 害怕 恐慌 焦虑 不安 崩溃
破碎 凋零 枯萎 腐烂 废墟 阴影 阴暗 黑暗 深渊 沉默 沉沦 沉重 冰冷 冷漠 冷酷 残忍 残酷 折磨 挣扎 疼 疼痛 苦涩 辛酸 心碎 心痛 眼泪
告别 离别 分离 分手 失去 失落 失望 消失 遗忘 遗憾 后悔 怨 怨恨 仇 愤怒 抛弃 背叛 欺骗 谎言 战争 死亡 葬 墓 哭泣 呜咽 叹息""".split()
POSITIVE_EN = """love loves loved loving joy joyful light warm warmth spring bright hope hopes hopeful gentle happy sweet home embrace
peace peaceful calm smile smiles smiling laugh laughter dream dreams star stars sea blue sun sunlight sunshine kind kindness thank thanks
grateful dear beloved darling bloom blossom tender grace glow golden morning garden bird birds song sing singing alive forever always
believe grow green gift treasure cherish delight delighted glad cheer cheerful comfort comforting safe sweetness honey blessing blessed
free freedom brave courage radiant shining shine sparkle wonder wonderful beautiful beauty lovely pretty precious heaven angel paradise
harmony serene soft softly hug kiss kisses together reunion welcome celebrate celebration victory triumph flourish thrive rainbow dawn""".split()
NEGATIVE_EN = """cry cried crying tears tear pain painful hurt hurts death dead die dying died goodbye farewell lonely alone loneliness cold
grey gray forget forgotten sorrow sorrowful grief grieve bitter hate hatred fear afraid empty emptiness broken lost dark darkness sink
sinking sick old far never nothing ache aches ashes grave blood ruin ruins regret sigh mourn mourning wound wounds winter ghost silence
silent gone sad sadness unhappy miserable misery despair hopeless helpless weary tired exhausted numb hollow shadow shadows abyss
cruel cruelty torment agony anguish suffer suffering struggle wither withered decay rot rotten wreck wreckage wasted waste lie lies
betray betrayal betrayed abandon abandoned war fight fought bury buried funeral coffin weep weeping sob sobbing scar scars poison""".split()

HIGH_AROUSAL_ZH = """火 燃 跑 冲 狂 风暴 雷 心跳 疯 快 战 舞 闪 电 霓虹 呐喊 叫 燃烧 奔 撞 炸 鼓 震 醒 起来 冲刺 呼喊 热 沸 奔跑 狂奔
飞奔 疾驰 爆发 爆炸 轰 咆哮 怒吼 尖叫 呐 呼啸 呼喊 激动 兴奋 热血 沸腾 燃起 点燃 闪电 暴雨 狂风 巨浪 海啸 地震 战斗 冲锋 突围
急促 急切 紧张 剧烈 汹涌 澎湃 跳动 心跳 脉搏 急速 高速 飞驰 呼吸急 喘 挣扎 摇滚 狂欢 舞动 跳舞 起舞 欢呼 喝彩 高喊 大笑 狂笑""".split()
LOW_AROUSAL_ZH = """静 慢 睡 眠 月 云 雾 湖 息 轻 悄 淡 缓 沉默 安静 寂静 微 柔 低语 呼吸 冬 雪 溪 浅 空 夜 静谧 宁静 幽静 清幽 悠然
悠悠 缓缓 慢慢 轻轻 悄悄 淡淡 薄薄 朦胧 迷蒙 氤氲 袅袅 飘 漂 浮 荡 摇 摇曳 摇晃 微光 月光 星光 烛光 灯火 余晖 黄昏 暮 晚 深夜
午夜 凌晨 清晨 拂晓 露 霜 冰 湖面 河面 水面 倒影 影 梦 梦境 睡梦 入睡 沉睡 安眠 长眠 停 停留 停下 驻足 凝望 凝视 凝 沉思 冥想""".split()
HIGH_AROUSAL_EN = """fire burn burning burns run running runs rush rushing wild storm storms thunder lightning heartbeat mad madness fast
faster fight fighting dance dancing flash electric city neon loud louder scream screaming shout shouting drum drums pulse race racing
crash crashing explode explosion awake rise rising hot boil boiling blaze blazing roar roaring rage raging fury furious frantic frenzy
chaos chase chasing leap leaping jump jumping sprint speed speeding engine engines highway fever fevered hammer hammering pound pounding
shake shaking tremble trembling burst bursting spark sparks ignite alive electric strobe bass beat beats throb throbbing stomp""".split()
LOW_AROUSAL_EN = """sleep sleeping slow slowly quiet quietly still stillness moon moonlight cloud clouds mist misty lake breath breathe
breathing hush hushed soft softly whisper whispers whispering gentle gently calm calmly silent silence winter snow snowfall stream
shallow drift drifting float floating linger lingering dusk twilight evening midnight dawn candle candlelight lamp lamplight pale dim
faint fading fade fog foggy haze hazy dream dreaming dreamy rest resting pause paused wait waiting patient patience slumber hum humming
lull lullaby cradle drowsy sleepy lazy idle wander wandering meadow willow river riverbank shore tide tides ripple ripples""".split()

TENSION_ZH = """但 却 可是 然而 如果 为什么 为何 是否 难道 也许 或许 不知 不能 无法 还是 直到 等待 犹豫 徘徊 矛盾 不确定 疑惑 困惑
迷惑 怀疑 质疑 追问 询问 疑问 问 究竟 到底 何时 何处 何以 怎 怎么 怎样 如何 万一 倘若 假如 若 除非 只是 只不过 偏偏 竟 竟然
居然 却又 又或 抑或 还 仍 仍然 依旧 尚未 未 尚 仍旧 挣扎 摇摆 动摇 迟疑 踌躇 彷徨 纠结 焦灼 悬 悬念 未知 未来 不知道 不明白""".split()
TENSION_EN = """but yet however if why whether maybe perhaps unless until wait waiting hesitate hesitation torn doubt doubts doubtful
question questions unsure uncertain uncertainty cannot can't couldn't wouldn't shouldn't should would could might although though
still nevertheless nonetheless whereas otherwise suppose supposing what when where how who whom whose which somehow someday somewhere
almost nearly barely hardly scarcely between edge brink verge cliff tightrope suspense pending unresolved unanswered unknown unsaid""".split()

WARM_ZH = """家 妈妈 母亲 父亲 爸爸 你 我们 拥抱 手 怀 亲 温 暖 灯 炉 汤 茶 饭 信 陪 伴 老友 兄弟 姐妹 孩子 童年 爷爷 奶奶 外婆
外公 姥姥 姥爷 家人 亲人 爱人 恋人 朋友 伙伴 同伴 邻居 故乡 老家 屋 房 门 窗 床 被 毯 火炉 灶 厨房 饭桌 餐桌 饭菜 面 粥 酒 酒杯
杯 碗 筷 围巾 毛衣 棉 绒 手心 掌心 怀抱 肩 背 膝 笑声 谈笑 闲聊 叙旧 重逢 团圆 归来 归家 回家 回来 等你 想你 念你 你好 晚安""".split()
COLD_ZH = """冰 霜 雪 铁 钢 石 墙 玻璃 远方 陌生 机器 荒野 孤岛 深海 太空 荒漠 雾 水泥 混凝土 钢筋 铁轨 铁门 铁窗 铁链 锁 锈 金属
金属感 塑料 屏幕 显示器 键盘 电缆 电线 天线 信号塔 高楼 大厦 摩天 玻璃幕墙 荒原 荒凉 荒芜 冷清 冷寂 空旷 空荡 空无 无人 陌生人
异乡 他乡 远行 远去 远离 边缘 边界 荒岛 冰川 冰山 冰河 极地 极夜 真空 黑洞 星际 宇宙 深空 虚空 空洞 麻木 冷眼 冷笑 冷漠 疏离""".split()
COLD_EN = """ice icy frost frozen snow iron steel stone stones wall walls glass distant stranger strangers machine machines wasteland
island ocean space desert deserts fog concrete asphalt metal metallic chrome plastic screen screens keyboard cable cables wire wires
antenna tower towers skyscraper skyscrapers vacant empty hollow barren bleak desolate stark remote faraway exile exiled alien foreign
border edge frontier glacier tundra arctic void vacuum orbit satellite static numb detached indifferent clinical sterile blank""".split()
WARM_EN = """home mother mom mama father dad papa you we us embrace hands hand hold holding arms kiss warm lamp hearth fireplace soup tea
bread letter letters company friend friends brother sister child children childhood hug hugs grandmother grandfather grandma grandpa
family beloved lover neighbor neighbour kitchen table supper dinner breakfast blanket blankets wool sweater scarf mitten mittens pillow
bed window door porch garden yard laughter chatter stories story voice voices together reunion return returning homecoming welcome""".split()

CLASSICAL_ZH = """月 花 酒 江 山 风 雪 古 琴 诗 词 楼 舟 桥 柳 燕 雁 松 竹 梅 菊 亭 帘 烛 墨 笔 砚 卷 客 故人 明月 长亭 千里 万里 天涯
春秋 苍 悠 兮 之 乎 者 也 焉 矣 君 吾 汝 尔 兰 荷 莲 桂 枫 桐 杏 李 桃花 落花 飞花 残花 芳 芳草 青山 绿水 碧 苍茫 苍穹 云海 烟雨
烟波 江南 塞北 关山 玉 珠 簪 绣 锦 罗 纱 绢 帛 笛 箫 筝 瑟 鼓角 钟 磬 寺 庙 塔 阁 台 榭 廊 庭 院 阶 檐 瓦 篱 井 陌 驿 渡 舫 棹
帆 樯 归雁 孤鸿 杜鹃 鹧鸪 鸥 鹤 鹿 蝉 蛩 萤 霞 岚 霭 晖 曦 汀 洲 屿 涧 壑 岫 峦 崖 岭 潭 溪 泉 瀑 烟 霜 露 霁 岁 朝暮 晨昏""".split()
CLASSICAL_EN = """thee thou thy thine hath doth ere o'er whilst sonnet muse verse lyre nightingale meadow moonlight lament yonder
hither fair maiden knight harp chapel candle quill parchment art wert shalt canst dost hast tis twas nay yea forsooth alas oft ne'er
e'er 'tis 'twas ballad ode elegy psalm hymn minstrel bard troubadour lute viol organ choir cathedral abbey cloister castle tower
throne crown sword shield banner steed chariot laurel garland wreath rose lily violet ivy oak willow yew orchard vineyard shepherd
shepherdess nymph faun sprite fairy fae elfin dryad naiad muse muses grecian roman gothic baroque sonata nocturne prelude fugue""".split()
ELECTRONIC_ZH = """霓虹 城市 电 屏幕 机器 信号 数据 像素 未来 太空 星际 赛博 网络 代码 电流 频率 光纤 芯片 合成 键盘 引擎 高速 地铁 车站
夜店 灯光 闪烁 电台 电子 电脑 手机 程序 算法 系统 服务器 云端 虚拟 数字 比特 字节 二进制 模拟 电波 无线 蓝牙 雷达 激光 全息 投影
机械 机甲 机器人 仿生 义体 芯 电路 电池 电压 电磁 磁场 脉冲 波形 振荡 调制 滤波 混音 采样 循环 节拍 鼓机 贝斯 低音 合成器 音序
夜晚 夜色 夜幕 深夜 午夜 霓虹灯 街灯 路灯 车灯 尾灯 高架 立交 隧道 公路 街道 街头 楼群 天际线 摩天楼 玻璃 反光 倒影 雨夜 雨街""".split()
ELECTRONIC_EN = """neon city electric screen screens machine signal signals data pixel pixels future space synth synthesizer synthesizers
code wire wires glow static cyber network circuit circuits frequency chip engine highway subway station club strobe radio digital laser
chrome computer computers phone program programs algorithm system server cloud virtual bit bits byte bytes binary analog analogue wave
waves wireless bluetooth radar hologram holographic projection mechanical mech robot robots android cyborg bionic circuitry battery
voltage magnetic pulse pulses waveform oscillator modulate modulation filter mixer sample sampler loop loops beat beats drum machine
bassline sequencer arpeggio midnight nightlife streetlight streetlights headlights taillights overpass tunnel asphalt skyline glass
reflection reflections rain rainy grid matrix terminal console monitor cursor glitch glitches interface upload download stream""".split()

NEGATION_ZH = ("不", "没", "无", "非", "未", "莫", "勿", "别")
NEGATION_EN = {"not", "no", "never", "without", "nor", "neither", "n't", "cannot", "hardly"}
INTENSIFIER_ZH = ("很", "非常", "太", "最", "极", "特别", "十分", "格外", "更", "好", "真")
INTENSIFIER_EN = {"very", "so", "deeply", "truly", "really", "utterly", "extremely", "terribly", "absolutely", "completely"}

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


def _count_hits(text_lower: str, words_zh: Sequence[str], words_en: Sequence[str], en_tokens: Sequence[str],
                negation: bool = True) -> Tuple[float, List[str]]:
    """Weighted lexicon hits. Returns (weight, matched words). Negated matches
    count negative (the caller moves them to the opposite pole), intensified
    matches count 1.5."""
    weight = 0.0
    hits: List[str] = []
    masked = text_lower                       # matched spans are blanked so 暖 does not re-match inside 温暖
    for w in sorted(set(words_zh), key=len, reverse=True):
        start = 0
        while True:
            i = masked.find(w, start)
            if i < 0:
                break
            start = i + len(w)
            masked = masked[:i] + "\x00" * len(w) + masked[start:]
            factor = 1.0
            before = text_lower[max(0, i - 2):i]
            if negation and before and (before[-1] in NEGATION_ZH or (len(before) > 1 and before[-2] in NEGATION_ZH and before[-1] in ("是", "会", "再", "曾"))):
                factor = -0.8
            elif any(before.endswith(x) for x in INTENSIFIER_ZH):
                factor = 1.5
            weight += factor
            hits.append(("~" if factor < 0 else "") + w)
    en_set = set(words_en)
    for k, t in enumerate(en_tokens):
        if t in en_set:
            factor = 1.0
            prev = en_tokens[k - 1] if k > 0 else ""
            prev2 = en_tokens[k - 2] if k > 1 else ""
            if negation and (prev in NEGATION_EN or prev.endswith("n't") or prev2 in NEGATION_EN and prev in ("so", "very", "really")):
                factor = -0.8
            elif prev in INTENSIFIER_EN:
                factor = 1.5
            weight += factor
            hits.append(("~" if factor < 0 else "") + t)
    return weight, hits


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


AFFECT_KEYS = ("valence", "arousal", "tension", "warmth", "classical", "electronic")


def _pole(pos_w: float, neg_w: float) -> Tuple[float, float]:
    """Move negated hits to the opposite pole."""
    p = max(0.0, pos_w) + max(0.0, -neg_w)
    n = max(0.0, neg_w) + max(0.0, -pos_w)
    return p, n


def affect_of(text: str) -> Dict[str, float]:
    """The six affect dials for a piece of text (used per stanza by interpret)."""
    f = analyze(text) if text.strip() else None
    if f is None:
        return {k: 0.0 for k in AFFECT_KEYS}
    return {k: getattr(f, k) for k in AFFECT_KEYS}


def analyze(text: str, affect: Optional[Dict[str, float]] = None) -> TextFeatures:
    """Extract features. ``affect`` may override any of the six affect dials
    (e.g. tags produced by a larger model, see :mod:`poet_melody.llm`)."""
    text = text.replace("\r\n", "\n")
    stanzas = parse_structure(text)
    lower = text.lower()
    en_tokens = re.findall(r"[a-z']+", lower)
    language = detect_language(text)

    pos_w, pos = _count_hits(lower, POSITIVE_ZH, POSITIVE_EN, en_tokens)
    neg_w, neg = _count_hits(lower, NEGATIVE_ZH, NEGATIVE_EN, en_tokens)
    hi_w, hi = _count_hits(lower, HIGH_AROUSAL_ZH, HIGH_AROUSAL_EN, en_tokens, negation=False)
    lo_w, lo = _count_hits(lower, LOW_AROUSAL_ZH, LOW_AROUSAL_EN, en_tokens, negation=False)
    ten_w, ten = _count_hits(lower, TENSION_ZH, TENSION_EN, en_tokens, negation=False)
    warm_w, warm = _count_hits(lower, WARM_ZH, WARM_EN, en_tokens, negation=False)
    cold_w, cold = _count_hits(lower, COLD_ZH, COLD_EN, en_tokens, negation=False)
    cla_w, cla = _count_hits(lower, CLASSICAL_ZH, CLASSICAL_EN, en_tokens, negation=False)
    ele_w, ele = _count_hits(lower, ELECTRONIC_ZH, ELECTRONIC_EN, en_tokens, negation=False)
    pos_w, neg_w = _pole(pos_w, neg_w)

    n_syl = sum(len(l.syllables) for st in stanzas for l in st.lines)
    n_lines = sum(len(st.lines) for st in stanzas)
    per_100 = 100.0 / max(n_syl, 20)

    # Valence: smoothed ratio, with a little pull towards neutral for tiny texts.
    valence = (pos_w - neg_w) / (pos_w + neg_w + 2.0)

    n_excl = len(re.findall(r"[!！]", text))
    n_q = len(re.findall(r"[?？]", text))
    n_ell = len(re.findall(r"…|\.\.\.", text))
    caps = len(re.findall(r"[A-Z]", text))
    caps_ratio = caps / max(1, len(re.findall(r"[A-Za-z]", text)))
    line_lengths = [len(l.syllables) for st in stanzas for l in st.lines] or [0]
    mean_len = sum(line_lengths) / len(line_lengths)

    arousal = 0.35
    arousal += 0.35 * _sigmoid_scale((hi_w + 1.5 * n_excl) * per_100, 4.0)
    arousal -= 0.30 * _sigmoid_scale((lo_w + 0.7 * n_ell) * per_100, 4.0)
    arousal += 0.10 * min(1.0, caps_ratio * 4)          # SHOUTING
    arousal += 0.10 * (1.0 - min(1.0, mean_len / 14.0))  # short lines feel urgent
    arousal = min(1.0, max(0.0, arousal))

    tension = 0.15
    tension += 0.45 * _sigmoid_scale((ten_w + 2.0 * n_q) * per_100, 4.0)
    tension += 0.15 * _sigmoid_scale(n_ell * per_100, 2.0)
    tension += 0.15 * (1 - abs(valence))  # ambivalent texts are tense
    tension = min(1.0, max(0.0, tension))

    warmth = 0.5 + 0.5 * (warm_w - cold_w) / (warm_w + cold_w + 2.0)
    warmth = 0.7 * warmth + 0.3 * (0.5 + 0.5 * valence)
    classical = _sigmoid_scale(cla_w * per_100, 5.0)
    electronic = _sigmoid_scale(ele_w * per_100, 4.0)

    density = min(1.0, mean_len / 16.0)
    var = sum((x - mean_len) ** 2 for x in line_lengths) / len(line_lengths)
    irregularity = min(1.0, math.sqrt(var) / max(mean_len, 1.0))

    values = {"valence": valence, "arousal": arousal, "tension": tension,
              "warmth": min(1.0, max(0.0, warmth)), "classical": classical, "electronic": electronic}
    if affect:
        for k, v in affect.items():
            if k in values and v is not None:
                lo_, hi_ = (-1.0, 1.0) if k == "valence" else (0.0, 1.0)
                values[k] = min(hi_, max(lo_, float(v)))

    return TextFeatures(
        language=language,
        n_chars=len(text),
        n_syllables=n_syl,
        n_lines=n_lines,
        n_stanzas=len(stanzas),
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
        **values,
    )
