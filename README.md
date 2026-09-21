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
poet-melody generate poem.txt --form ABA --tone-weight 5   # force a form, stricter 依字行腔
poet-melody analyze examples/letter_zh.txt          # affect features only
poet-melody tag letter.txt                          # print an LLM tagging prompt (any model)
poet-melody generate letter.txt --affect tags.json  # use the model's ratings
poet-melody generate letter.txt --llm               # rate with Claude via the anthropic SDK (pip install anthropic)
poet-melody styles                                  # list styles
poet-melody progressions --style jazz --key F       # the progression library, resolved to a key
```

`python -m poet_melody ...` works without installing. Open `web/player.html` in a browser and drop the generated `.json` on it to hear the piece with Web Audio (lyrics and chords light up as they play).

**手机 / 浏览器版**：`web/app.html` + `web/engine.js`（引擎的 JavaScript 移植，无需服务器）在手机上直接生成并试听；`web/engine.test.mjs` 用 node 校验它与 Python 版输出结构一致。

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

同一文本总是得到同一首曲子（种子来自文本的 SHA-256），`--seed` 可换一个版本。词典条目带权重：否定词（不 / 没 / 无 / not / never）翻转极性，程度副词（很 / 非常 / very / so）加权 1.5；长词优先匹配（温暖 不再重复计入 暖）。`analyze(text, affect={...})` / `--affect` 可用外部（例如大模型）评分覆盖六个维度，`poet_melody.llm` 提供提示词模板与可选的 Claude 调用。

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
* **声部连接**（`voice_lead`）：枚举声部排列，取总移动最小、无同度、不过宽的配置，pad 与 keys 都用它。九和弦 / 十三和弦按爵士键盘习惯省略五音（再省根音），不会堆成五音簇。
* **风格约束**：groove 类风格（lofi / house / trance / pop / synthwave / ambient / neo-soul / folk）的功能生成器不产生减三和弦；借用主功能（bIII / bVI）只在下属之后出现一次，不会作为属和弦的解决。曲库只有一种调式家族的风格（trance 只有小调）整曲保持该家族，B 段也不转到曲库不支持的关系调。
* 调式：教会七调式、和声 / 旋律小调、Phrygian dominant、五声（宫商角徵羽）、Hirajoshi、蓝调、全音、八声音阶。

### 4. 解读 `interpret.py` — 像作曲家读歌词那样读文本

* **诗体识别**：五言 / 七言 绝句 / 律诗、四行诗、十四行诗、书信（称呼—正文—告别）、自由诗。
* **曲式**：按段落数规划 A / AB / ABA / AABA（或 ABAB）/ 回旋 ABACA…（`--form` 可强制）。同字母的段落共用和弦进行，再现的 A 段回忆首段的**头部动机**（前几个音程）；B 段有概率转到**关系大小调**（古典家族 75%，其他 35%）。
* **情感弧线**：每段单独分析效价 / 能量 / 张力，按强度（偏向黄金分割位置）确定**高潮段**；各段得到力度值 → 所有声部力度缩放、主旋律音区升降、高潮段键盘八度加厚、称呼 / 告别段抽掉鼓与键盘（breakdown）。
* **起承转合**：四行段落的第三行（转）在其下方替换一个色彩和弦（大调借用 iv / bVI / vi / ii，小调 IV / bII / VI / iv）并抬高音区，第四行（合）用最强终止。
* **音画（word painting）**：升（上 / 飞 / 望 / rise / sky）→ 轮廓上行；降（落 / 沉 / 泪 / fall）→ 下行；静（静 / 眠 / still）→ 拉长时值、少装饰；流（河 / 风 / river / wind）→ 级进连奏；远（远 / 天涯 / far）→ 允许大跳；归（归 / 回 / home）→ 句尾落主音；夜（月 / 夜 / moon / night）→ 低音区更轻；光（光 / 火 / fire / sun）→ 高音区更响。

### 5. 旋律 `melody.py`

1. **一字一音**：汉字 = 一个音节；英文按元音组切分音节。
2. **节奏**：每行按字数与 `arousal` 分配小节数，在八分 / 十六分网格上均匀落点后随机切分；句尾音延长并留呼吸。
3. **乐句弧线**：陈述句在黄金分割处到达高点后回落；问句尾音上扬；感叹句高起下落；省略号低回徘徊。
4. **收尾方式**：开放（落二级 / 五级）、半收（和弦音但非根音）、收束（根音 / 三音）、终止（主音）。由起承转合角色、汉语句尾声调（阴平 / 阳平 = 开放，上声 / 去声 = 收束）或行的奇偶决定。
5. **依字行腔 `tones.py`**：内置 20992 个汉字的声调表（`data/tones_4e00_9fff.txt`，由 pypinyin 生成，离线使用）。相邻两字按声调音区（阴平高、阳平中高、去声中、上声低）给出旋律方向：去声→阴平必须上行，阴平→上声必须下行，两个阳平自由；违反即"倒字"，被重罚。阳平字加下方倚音（上滑），上声字加更低的倚音，去声字加下落尾音。`--tone-weight` 调节强度，0 关闭。
6. **声调与和声匹配**：段落末字为阴平 / 阳平（上扬、开放）→ 该段用半终止（停在属和弦）；上声 / 去声（下落、收束）→ 正格 / 变格终止；问句同样触发半终止。
7. **主导动机**：每个字由自身哈希得到固定的音高偏移，同一个词再次出现带着相同的旋律指纹；A 段的头部动机在再现段开头被召回。
8. **约束**：强拍用和弦音（根音 / 五音 > 三音 > 七音 > 九音等，按稳定度加权），弱拍用音阶音；非和弦音须级进接近并级进解决；不超过大六度（"远"意象放宽到八度）；跳进后反向级进回填，禁止连续同向跳进；避免旋律三全音与七度；乐句结尾不停在七音 / 九音上。
9. **避免音**：与和弦音相差半音之上的音阶音（大三和弦上的四度、属七上的 b9）在弱拍重罚、时值越长罚越重；与调外和弦音（小调 V 的导音、借用和弦的降六级）相邻半音的音阶音直接排除，避免 b7 撞导音之类的错音。

### 6. 音色 `synth.py`

每首曲子给 pad / keys / bass / lead 各设计一个 patch（振荡器 → 滤波器 → 放大器，带包络、LFO、驱动、延迟、合唱、混响）。规则连续可微，相近的文本得到相近的声音：

* 温暖 → 正弦 / 三角波、低截止；冷 → 锯齿、高截止
* 能量 → 起音更快、释音更短、滤波器包络更深
* 张力 → 更宽的失谐、更高共振、慢速截止 LFO
* 负面情绪 → 更大的混响空间

每个 patch 附带一行人类可读的 `recipe`，可在任何硬件 / 软件合成器上重建，例如：

```
Neon Supersaw: supersaw + square -1oct, unison x7 (19c); LPF 3100Hz Q 0.12 env +0.5oct (...); reverb 30% (2.6s), chorus 60%
```

### 7. 渲染 `render.py`（需要 numpy）

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

* 词典仍是手工表（每类 80–120 条），没有分词与语义模型；`--affect` / `--llm` 可接入大模型评分。
* 声调表取每个字最常见的读音，多音字（如"行""重"）可能取错调；轻声按上下文判断尚未实现。
* 渲染器追求可解释与零依赖而非拟真；可将 JSON 喂给任何 DAW / Tone.js / SuperCollider。
* 曲式再现只召回头部动机与和弦进行，尚无变奏（augmentation / inversion）处理。
