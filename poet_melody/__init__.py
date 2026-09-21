"""poet-melody: turn letters, poems and articles into chords, synth patches and melodies.

>>> from poet_melody import generate
>>> comp = generate("床前明月光，疑是地上霜。")
>>> comp.style, comp.key, comp.mode
"""
from .analysis import analyze, TextFeatures
from .compose import generate
from .midi import write_midi, composition_to_midi
from .score import Composition
from .styles import STYLES, style_names, choose_style
from .progressions import LIBRARY, generate_functional, HarmonyOptions

__version__ = "0.1.0"
__all__ = [
    "analyze", "TextFeatures", "generate", "write_midi", "composition_to_midi", "Composition",
    "STYLES", "style_names", "choose_style", "LIBRARY", "generate_functional", "HarmonyOptions",
]
