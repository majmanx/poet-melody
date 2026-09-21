"""Minimal Standard MIDI File (type 1) writer, no dependencies.

Timing is *performed*: swing and ritardando are baked into the note ticks at a
constant tempo, so the file plays back exactly like the rendered audio.
"""
from __future__ import annotations

import struct
from typing import List, Tuple

from .score import Composition

PPQ = 480

GM_PROGRAMS = {
    "pad": 89,      # Pad 2 (warm)
    "keys": 4,      # Electric Piano 1
    "bass": 38,     # Synth Bass 1
    "lead": 80,     # Lead 1 (square)
    "drums": 0,
}
GM_PROGRAMS_CLASSICAL = {"pad": 48, "keys": 0, "bass": 42, "lead": 73}   # strings, piano, cello, flute

# Drum note numbers (GM channel 10)
DRUM_NOTES = {"kick": 36, "snare": 38, "clap": 39, "hat": 42, "ohat": 46, "ride": 51}


def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def _track_chunk(events: List[Tuple[int, bytes]]) -> bytes:
    events.sort(key=lambda e: e[0])
    data = bytearray()
    last = 0
    for tick, msg in events:
        data += _vlq(tick - last) + msg
        last = tick
    data += _vlq(0) + b"\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def _meta(kind: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([kind]) + _vlq(len(payload)) + payload


def composition_to_midi(comp: Composition) -> bytes:
    tl = comp.timeline
    bpm = comp.bpm
    spb = 60.0 / bpm

    def tick(beat: float) -> int:
        return int(round(tl.seconds(beat) / spb * PPQ))

    tracks: List[bytes] = []
    meta: List[Tuple[int, bytes]] = [
        (0, _meta(0x03, comp.title.encode("utf-8"))),
        (0, _meta(0x51, struct.pack(">I", int(60_000_000 / bpm))[1:])),
        (0, _meta(0x58, bytes([comp.time_signature[0], {2: 1, 4: 2, 8: 3}[comp.time_signature[1]], 24, 8]))),
        (0, _meta(0x01, f"key {comp.key} {comp.mode}; style {comp.style}".encode("utf-8"))),
    ]
    tracks.append(_track_chunk(meta))
    classical = comp.style in ("classical", "romantic", "folk", "cinematic")
    for t in comp.tracks:
        ch = 9 if t.role == "drums" else t.midi_channel
        ev: List[Tuple[int, bytes]] = [(0, _meta(0x03, t.name.encode("utf-8")))]
        if t.role != "drums":
            prog = (GM_PROGRAMS_CLASSICAL if classical else GM_PROGRAMS).get(t.role, t.midi_program)
            ev.append((0, bytes([0xC0 | ch, prog])))
        for n in t.notes:
            on, off = tick(n.start), tick(n.start + n.duration)
            if off <= on:
                off = on + 1
            if n.lyric:
                ev.append((on, _meta(0x05, n.lyric.encode("utf-8"))))
            ev.append((on, bytes([0x90 | ch, n.pitch & 0x7F, max(1, min(127, n.velocity))])))
            ev.append((off, bytes([0x80 | ch, n.pitch & 0x7F, 0])))
        tracks.append(_track_chunk(ev))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ)
    return header + b"".join(tracks)


def write_midi(comp: Composition, path: str) -> None:
    with open(path, "wb") as fh:
        fh.write(composition_to_midi(comp))
