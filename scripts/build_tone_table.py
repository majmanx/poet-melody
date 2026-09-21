"""Regenerate poet_melody/data/tones_4e00_9fff.txt from pypinyin.

    pip install pypinyin && python scripts/build_tone_table.py

One ASCII digit per code point U+4E00..U+9FFF: 1-4 = Mandarin tones of the
most common reading, 5 = neutral tone, 0 = unknown.
"""
import os

from pypinyin import Style, pinyin

START, END = 0x4E00, 0x9FFF
chars = [chr(c) for c in range(START, END + 1)]
readings = pinyin(chars, style=Style.TONE3, heteronym=False, errors=lambda x: [["0"]] * len(x))
digits = []
for r in readings:
    s = r[0]
    if s and s[-1].isdigit():
        digits.append(s[-1])
    elif s and s != "0" and s.isalpha():
        digits.append("5")
    else:
        digits.append("0")
out = os.path.join(os.path.dirname(__file__), "..", "poet_melody", "data", "tones_4e00_9fff.txt")
with open(out, "w", encoding="ascii") as fh:
    fh.write("".join(digits))
print(f"wrote {out}: {len(digits)} entries")
