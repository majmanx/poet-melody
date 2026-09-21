"""Command line interface.

    poet-melody generate letter.txt --out out/letter --format json,midi,wav
    poet-melody analyze letter.txt
    poet-melody styles
    poet-melody progressions --style jazz
    echo "举头望明月" | poet-melody generate - --style folk
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from .analysis import analyze
from .compose import generate
from .midi import write_midi
from .progressions import LIBRARY, all_styles
from .styles import STYLES
from .theory import parse_roman


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _print_summary(comp) -> None:
    print(f"Title      : {comp.title}")
    print(f"Style      : {comp.style}")
    print(f"Key / mode : {comp.key} {comp.mode}  scale {' '.join(comp.scale)}")
    print(f"Tempo      : {comp.bpm:g} bpm, {comp.time_signature[0]}/{comp.time_signature[1]}, swing {comp.timeline.swing:.2f}")
    print(f"Length     : {comp.total_beats:g} beats, {comp.total_seconds:.1f} s, seed {comp.seed}")
    print(f"Form       : {comp.form}  ({comp.interpretation.get('poem_form', '')})")
    print("Sections   :")
    for s in comp.sections:
        print(f"  {s.name:10s} {s.label:2s} {s.role:11s} dyn {s.dynamic:.2f} bars {s.start / comp.time_signature[0]:4.0f}-{(s.start + s.duration) / comp.time_signature[0]:<4.0f} "
              f"{s.key:3s}{s.mode:15s} {s.progression}: {' '.join(s.numerals)}")
    print("Chords     : " + " | ".join(c.symbol for c in comp.chords))
    lead = comp.track("lead")
    if lead:
        sung = [n for n in lead.notes if n.lyric]
        print("Melody     : " + " ".join(f"{n.lyric}{n.tone or ''}({n.pitch})" for n in sung[:40]) + (" ..." if len(sung) > 40 else ""))
    print("Patches    :")
    for role, p in comp.patches.items():
        print(f"  {role:5s} {p['name']:18s} {p['recipe']}")
    print("Theory     :")
    for line in comp.notes_on_theory:
        print(f"  - {line}")


def _load_affect(path: Optional[str]):
    if not path:
        return None
    from .llm import parse_affect_json
    with open(path, "r", encoding="utf-8") as fh:
        return parse_affect_json(fh.read())


def cmd_generate(args: argparse.Namespace) -> int:
    text = _read_text(args.input)
    affect = _load_affect(args.affect)
    if args.llm:
        from .llm import tag_with_claude
        affect = {**(affect or {}), **tag_with_claude(text)}
        print("LLM affect: " + json.dumps(affect, ensure_ascii=False), file=sys.stderr)
    comp = generate(text, style=args.style, seed=args.seed, title=args.title, tempo=args.tempo,
                    key=args.key, mode=args.mode, drums=None if args.drums == "auto" else args.drums == "on",
                    form=args.form, affect=affect, tone_weight=args.tone_weight)
    formats = [f.strip() for f in args.format.split(",") if f.strip()]
    out = args.out
    if out is None:
        base = os.path.splitext(os.path.basename(args.input))[0] if args.input != "-" else "poem"
        out = os.path.join("out", base)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if not args.quiet:
        _print_summary(comp)
    written: List[str] = []
    if "json" in formats:
        path = out + ".json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(comp.to_dict(), fh, ensure_ascii=False, indent=1)
        written.append(path)
    if "midi" in formats or "mid" in formats:
        path = out + ".mid"
        write_midi(comp, path)
        written.append(path)
    if "wav" in formats:
        try:
            from .render import render, write_wav
        except ImportError:
            print("numpy is required for WAV rendering: pip install numpy", file=sys.stderr)
            return 2
        audio = render(comp, sr=args.sample_rate)
        path = out + ".wav"
        write_wav(audio, path, args.sample_rate)
        written.append(path)
    for w in written:
        print(f"wrote {w}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    f = analyze(_read_text(args.input))
    d = f.to_dict()
    if not args.verbose:
        d["keyword_hits"] = {k: v[:8] for k, v in d["keyword_hits"].items() if v}
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    from .llm import tag_with_claude, tagging_prompt
    text = _read_text(args.input)
    if args.llm:
        print(json.dumps(tag_with_claude(text), ensure_ascii=False, indent=1))
    else:
        print(tagging_prompt(text))
    return 0


def cmd_styles(_: argparse.Namespace) -> int:
    for name, st in STYLES.items():
        print(f"{name:10s} {st.tempo_range[0]:3d}-{st.tempo_range[1]:<3d} bpm  major {', '.join(st.major_modes):22s} minor {', '.join(st.minor_modes)}")
        print(f"           {st.description}")
    return 0


def cmd_progressions(args: argparse.Namespace) -> int:
    from .theory import NOTE_TO_PC
    tonic = NOTE_TO_PC[args.key]
    for p in LIBRARY:
        if args.style and p.style != args.style:
            continue
        chords = " ".join(parse_roman(n, tonic, p.mode).symbol() for n in p.numerals)
        print(f"{p.style:10s} {p.mode:10s} {p.name:28s} {' '.join(p.numerals):32s} -> {chords}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="poet-melody", description="Turn text into chords, synth patches and melody.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="compose from a text file ('-' for stdin)")
    g.add_argument("input")
    g.add_argument("--out", help="output path without extension (default out/<input name>)")
    g.add_argument("--style", default="auto", choices=["auto"] + list(STYLES))
    g.add_argument("--format", default="json,midi,wav", help="comma list of json,midi,wav")
    g.add_argument("--seed", type=int)
    g.add_argument("--title")
    g.add_argument("--tempo", type=float)
    g.add_argument("--key", help="tonic, e.g. C, F#, Bb")
    g.add_argument("--mode", help="ionian, aeolian, dorian, lydian, mixolydian, phrygian, harmonic_minor ...")
    g.add_argument("--drums", default="auto", choices=["auto", "on", "off"])
    g.add_argument("--form", default="auto", help="musical form, one letter per stanza, e.g. ABA, AABA (default auto)")
    g.add_argument("--affect", help="JSON file with affect overrides (valence, arousal, tension, warmth, classical, electronic)")
    g.add_argument("--llm", action="store_true", help="rate the affect with Claude first (needs `pip install anthropic` and credentials)")
    g.add_argument("--tone-weight", type=float, help="strength of the Mandarin tone constraint (default 3, 0 disables)")
    g.add_argument("--sample-rate", type=int, default=44100)
    g.add_argument("--quiet", action="store_true")
    g.set_defaults(func=cmd_generate)
    a = sub.add_parser("analyze", help="print the affect features of a text")
    a.add_argument("input")
    a.add_argument("--verbose", action="store_true")
    a.set_defaults(func=cmd_analyze)
    t = sub.add_parser("tag", help="print an LLM tagging prompt for a text (or call Claude with --llm)")
    t.add_argument("input")
    t.add_argument("--llm", action="store_true")
    t.set_defaults(func=cmd_tag)
    s = sub.add_parser("styles", help="list styles")
    s.set_defaults(func=cmd_styles)
    p = sub.add_parser("progressions", help="list the progression library")
    p.add_argument("--style", choices=all_styles())
    p.add_argument("--key", default="C")
    p.set_defaults(func=cmd_progressions)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
