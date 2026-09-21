"""Optional LLM affect tagging.

The built-in lexicons are small and transparent. For richer readings you can
ask a large language model to rate the six affect dials and feed the result
back with ``generate(text, affect=...)`` or ``poet-melody generate --affect``.

:func:`tagging_prompt` builds a prompt usable with *any* model; :func:`tag_with_claude`
calls the Claude API through the official ``anthropic`` SDK when it is installed
and credentials are available (``pip install anthropic``; set ``ANTHROPIC_API_KEY``
or log in with ``ant auth login``).
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional

from .analysis import AFFECT_KEYS

DEFAULT_MODEL = "claude-opus-5"

PROMPT_TEMPLATE = """You are a composer reading a text before setting it to music.
Rate the text on six dials and answer ONLY with a JSON object.

Dials:
- valence: -1 (grief, darkness) .. 1 (joy, light)
- arousal: 0 (still, quiet, slow) .. 1 (frantic, loud, fast)
- tension: 0 (resolved, settled) .. 1 (questioning, unresolved, torn)
- warmth: 0 (cold, distant, mechanical) .. 1 (intimate, tender, homely)
- classical: 0 .. 1 how strongly the vocabulary and imagery evoke classical or literary tradition
- electronic: 0 .. 1 how strongly it evokes cities, machines, neon, the future
Also give "summary": one sentence describing the emotional arc, and
"climax_hint": the 1-based index of the stanza that should be the musical climax (or null).

Text:
<<<
{text}
>>>

JSON:"""


def tagging_prompt(text: str) -> str:
    return PROMPT_TEMPLATE.replace("{text}", text.strip())


def parse_affect_json(raw: str) -> Dict[str, float]:
    """Extract the affect dict from a model reply (tolerates prose around the JSON)."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    data = json.loads(m.group(0))
    out: Dict[str, float] = {}
    for k in AFFECT_KEYS:
        if k in data and data[k] is not None:
            out[k] = float(data[k])
    for extra in ("summary", "climax_hint"):
        if extra in data:
            out[extra] = data[extra]
    return out


def tag_with_claude(text: str, model: str = DEFAULT_MODEL) -> Dict[str, float]:
    """Rate the text with Claude. Requires the ``anthropic`` package and credentials."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pip install anthropic to use LLM tagging") from exc
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": tagging_prompt(text)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("the model declined to rate this text")
    reply = "".join(block.text for block in response.content if block.type == "text")
    return parse_affect_json(reply)
