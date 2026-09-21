# poet-melody · 信 / 诗 / 文章 → 和弦 · 合成器音色 · 旋律

把一封信、一首诗或一篇文章变成一段可以听的音乐：先分析文本的情绪与结构，再用**古典功能和声**、**现代调式与色彩和声**、**爵士 / 新灵魂扩展和弦**以及 **Synthwave / House / Trance / Lo-fi / Ambient** 等经典电子乐和弦进行编曲，最后按同一组情绪参数设计合成器音色并渲染成音频。

Turn a letter, poem or article into music: text affect → key / mode / tempo → chord progression (classical cadences, modal colour, jazz extensions, classic synth loops) → text-driven melody → affect-driven synth patches → JSON + MIDI + WAV. Pure Python, `numpy` only for audio rendering.

```
文本 text ──► analysis ──► style / key / mode / tempo
                 │
                 ├──► progressions  (library + functional-harmony generator)
                 ├──► voice leading (theory)        ──► pad / keys / bass
                 ├──► melody        (one note per syllable, phrase arcs, leitmotifs) ──► lead
                 └──► synth         (patch design)   ──► render (numpy) ──► .wav
                                                     ──► midi ──► .mid
                                                     ──► score.to_dict() ──► .json ──► web/player.html
```

## 快速开始 Quick start

```bash
pip install -e ".[audio]"          # numpy for WAV rendering (JSON/MIDI need no dependencies)

poet-melody generate examples/moon.txt              # -> out/moon.json / .mid / .wav
poet-melody generate letter.txt --style synthwave --key F# --mode aeolian --tempo 104
echo "举头望明月，低头思故乡。" | poet-melody generate - --style folk --format json,midi
poet-melody analyze examples/letter_zh.txt          # affect features only
poet-melody styles                                  # list styles
poet-melody progressions --style jazz --key F       # the progression library, resolved to a key
```

`python -m poet_melody ...` works without installing. Open `web/player.html` in a browser and drop the generated `.json` on it to hear the piece with Web Audio (lyrics and chords light up as they play).

Python API:

```python
from poet_melody import generate, write_midi
from poet_melody.render import render, write_wav

comp = generate(open("letter.txt", encoding="utf-8").read(), style="auto")
print(comp.key, comp.mode, comp.bpm, [c.symbol for c in comp.chords])
print(comp.notes_on_theory)          # why these choices were made
write_midi(comp, "letter.mid")
write_wav(render(comp), "letter.wav")
data = comp.to_dict()                # everything, incl. seconds for every note
```

## 文本如何变成音乐 How text becomes music

### 1. 文本分析 `analysis.py`

| 特征 feature | 来源 | 影响 |
|---|---|---|
| `valence` −1…1 | 双语情感词典（爱/光/暖… vs 泪/冷/别…） | 大调 / 小调家族、亮度、混响大小 |
| `arousal` 0…1 | 高能词、感叹号、大写、短句 | 速度、节奏密度、包络快慢、滤波器咬合 |
| `tension` 0…1 | 问号、转折词（但/却/如果/why/but）、省略号、矛盾情绪 | 半终止、更"有色彩"的调式、失谐与共振 |
| `warmth` 0…1 | 家/母亲/拥抱/茶… vs 冰/铁/机器/太空… | 降号调 vs 升号调、正弦/三角波 vs 锯齿波 |
| `classical` / `electronic` | 月花酒江山 / thee thou… vs 霓虹 城市 信号 neon synth… | 风格选择 |
| 结构 | 空行 = 段落 → 乐段；行 / 句 → 乐句；汉字 / 英文音节 → 音符 | 曲式与节奏 |

同一文本总是得到同一首曲子（种子来自文本的 SHA-256），`--seed` 可换一个版本。

### 2. 风格 `styles.py`

`--style auto` 按特征打分挑选；也可强制指定。

| style | 特点 |
|---|---|
| `classical` | 功能和声 I–IV–V–I、Pachelbel、五度圈、阿尔贝蒂低音、弦乐渐强、结尾渐慢 |
| `romantic` | 半音中音关系和弦（I–III、bVI）、借用小下属、阻碍终止 |
| `folk` | 五声（宫 / 羽）旋律，简单三和弦与 sus 和弦，变格终止 |
| `jazz` | ii–V–I、七九和弦、三全音替代、行走低音、摇摆八分 |
| `neo_soul` | 9/13 和弦、借用 iv / bVII、慵懒鼓 |
| `lofi` | 七和弦、摇摆、磁带抖动的电钢、Lo-fi 鼓 |
| `pop` | I–V–vi–IV 一族四和弦循环 |
| `synthwave` | 自然小调 i–VI–III–VII，Supersaw pad，八度低音，门限混响鼓 |
| `house` | Dorian / Aeolian 双和弦 vamp，反拍低音，四四拍底鼓，侧链 |
| `trance` | 上行小调循环、16 分滚动低音、Supersaw 主音、附点延迟 |
| `ambient` | Lydian / Dorian 色彩，每和弦两小节，长渐强，持续低音 |
| `cinematic` | Phrygian bII、半音中音、琶音 ostinato、半终止 |

### 3. 和声 `progressions.py` + `theory.py`

* **和弦进行库**（83 条）按风格与调式标注，用罗马数字写在各自调式里：大写 = 大三和弦，小写 = 小三和弦，`7 / maj7 / 9 / 13 / sus2 / sus4 / add9 / ° / ø7 / b / # / V7/x` 等后缀都能解析（`parse_roman`）。
* **功能和声生成器**（`generate_functional`）按 T–S–D 语法生成新进行，可调：七和弦概率、九和弦、调式混合（借用和弦）、半音中音、副属和弦、三全音替代、sus 色彩，以及终止式（正格 / 变格 / 阻碍 / 半 / 皮卡迪）。带问号的段落自动用半终止，末段用正格终止（小调而情绪积极 → 皮卡迪三度）。
* **声部连接**（`voice_lead`）：枚举声部排列，取总移动最小、无同度、不过宽的配置，pad 与 keys 都用它。
* 调式：教会七调式、和声 / 旋律小调、Phrygian dominant、五声（宫商角徵羽）、Hirajoshi、蓝调、全音、八声音阶。

### 4. 旋律 `melody.py`

1. **一字一音**：汉字 = 一个音节；英文按元音组切分音节。
2. **节奏**：每行按字数与 `arousal` 分配小节数，在八分 / 十六分网格上均匀落点后随机切分（不规则文本更多切分）；句尾音延长并留呼吸。
3. **乐句弧线**：陈述句在黄金分割处到达高点后回落；问句尾音上扬；感叹句高起下落；省略号低回徘徊。行与行之间交替为**前乐句（开放，落在二级 / 五级）**与**后乐句（收束，落在根音 / 三音）**，即古典乐段结构。
4. **主导动机**：每个字 / 音节由自身哈希得到一个固定的音高偏移，所以同一个词再次出现会带着相同的旋律指纹。
5. **约束**：强拍用和弦音，弱拍用音阶音（非和弦音须级进接近）；不超过八度；跳进后反向级进"回填"；避免旋律三全音与七度；末音落主音。

### 5. 音色 `synth.py`

每首曲子给 pad / keys / bass / lead 各设计一个 patch（振荡器 → 滤波器 → 放大器，带包络、LFO、驱动、延迟、合唱、混响）。规则连续可微，相近的文本得到相近的声音：

* 温暖 → 正弦 / 三角波、低截止；冷 → 锯齿、高截止
* 能量 → 起音更快、释音更短、滤波器包络更深
* 张力 → 更宽的失谐、更高共振、慢速截止 LFO
* 负面情绪 → 更大的混响空间

每个 patch 附带一行人类可读的 `recipe`，可在任何硬件 / 软件合成器上重建，例如：

```
Neon Supersaw: supersaw + square -1oct, unison x7 (19c); LPF 3100Hz Q 0.12 env +0.5oct (...); reverb 30% (2.6s), chorus 60%
```

### 6. 渲染 `render.py`（需要 numpy）

PolyBLEP 锯齿 / 方波、Supersaw、噪声；时变共振低通（STFT 域，无逐采样循环）；ADSR；合成脉冲响应的卷积混响；反馈延迟；合唱；侧链抽吸；软削波。合成鼓：底鼓、军鼓（synthwave 带门限混响）、拍手、踩镲、叮镲。

## 输出 Output

* `*.json` – 完整乐谱：特征、风格、调性、分段、和弦（罗马数字 + 音名 + 配置）、每轨每音（拍与秒）、patch、乐理说明。播放器与其他程序都可直接使用。
* `*.mid` – Type-1 MIDI，每轨一个 track（GM 音色近似），歌词事件写在主旋律轨，摇摆与渐慢已烘焙进时值。
* `*.wav` – 44.1 kHz 16-bit 立体声。

## 扩展 Extending

* 加一条和弦进行：在 `progressions.py` 的 `LIBRARY` 里加一行 `_p("name", "style", "mode", "i VI III VII", ("dark",))`，测试会自动验证它能解析。
* 加一种风格：在 `styles.py` 的 `STYLES` 里加一个 `Style(...)`，并在 `synth.py` 里为它选或写一组 patch。
* 改词典：`analysis.py` 顶部的中英列表。

## 测试 Tests

```bash
pip install -e ".[dev]"
pytest
```

## 已知限制 / 路线图

* 情感词典是小型手工词典，没有分词与语义模型；可以接入更大的词典或 LLM 打标签。
* 汉语声调（依字行腔）尚未参与旋律走向，需要拼音 / 声调表。
* 渲染器追求可解释与零依赖而非拟真；可将 JSON 喂给任何 DAW / Tone.js / SuperCollider。
* 尚无变奏 / 再现（ABA）曲式控制，段落间的调性对比只来自各段各自选择的进行。
