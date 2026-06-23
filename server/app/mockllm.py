"""A stand-in for a real LLM.

It streams canned prose token-by-token. There is no model; the point is to
exercise the *system* (non-blocking send, real-time steering, cancel,
horizontal fan-out), not to be intelligent.

`select_pool` maps a steering instruction to a different content "style" so
that steering is visibly reflected in the stream.
"""
from __future__ import annotations

import itertools

# Each pool is a body of text we tokenise into word-ish chunks. They are kept
# deliberately long so a streaming reply lasts long enough to be steered while
# it is still typing.
POOLS: dict[str, str] = {
    "default": (
        "Sure, let me walk through that. Here is a clear, structured explanation of "
        "the idea you asked about, building up from the fundamentals and adding "
        "detail as we go so the reasoning stays easy to follow throughout. We start "
        "with the core concept, then look at how the individual pieces fit together "
        "and why each one matters in practice. Along the way it helps to keep a "
        "concrete example in mind, because an example grounds the abstract parts and "
        "shows how they behave when real inputs flow through the system. Once the "
        "shape is clear, we can talk about the trade-offs, the common pitfalls to "
        "watch for, and the small refinements that make the whole thing robust. By "
        "the end you should have a complete mental model you can apply confidently "
        "to new situations of your own."
    ),
    "concise": (
        "In short: yes. The key points are simple, the trade-offs are small, and the "
        "recommended path is the straightforward one. Keep the moving parts to a "
        "minimum, lean on the defaults, and only add complexity when a real problem "
        "demands it. That is really all there is to it."
    ),
    "detailed": (
        "Let's go deep. We'll start with the underlying model, examine each moving "
        "part in turn, consider the edge cases and failure modes, weigh the "
        "alternatives against one another, and only then arrive at a well-justified "
        "conclusion supported by the reasoning we developed along the way. First, "
        "consider how the components communicate and where state actually lives, "
        "because that determines what can scale independently and what cannot. Next, "
        "think carefully about what happens when a part fails midway: who retries, "
        "what is idempotent, and how the system converges back to a consistent "
        "state. Finally, we layer in the performance characteristics, the operational "
        "concerns, and the long-term maintenance cost so the recommendation holds up "
        "well beyond the happy path."
    ),
    "french": (
        "Bien sur. Voici une explication claire et structuree de votre demande, en "
        "partant des principes de base et en ajoutant des details au fur et a mesure "
        "pour que le raisonnement reste facile a suivre. Nous commencons par le "
        "concept central, puis nous regardons comment les differentes pieces "
        "s'assemblent et pourquoi chacune compte en pratique. Un exemple concret "
        "aide beaucoup, car il ancre les parties abstraites et montre leur "
        "comportement reel. Ensuite nous discutons des compromis, des pieges "
        "courants et des petits ajustements qui rendent l'ensemble solide et fiable."
    ),
    "pirate": (
        "Arr, gather round. Here be the tale ye asked for, charted plain and true, "
        "startin' from the shallows and sailin' out to the deep, with nary a reef of "
        "confusion to wreck us along the way, matey. First we hoist the mainsail and "
        "name the parts of the ship, so every hand knows port from starboard. Then we "
        "read the winds and the tides, for they decide how fast we may run and where "
        "the danger lies. And when a squall rolls in, a steady crew knows who bails, "
        "who steers, and how we come about and right ourselves before the next swell."
    ),
    "haiku": (
        "Quiet morning light.\nA single thought drifts downstream.\nThe answer ripples."
    ),
    "excited": (
        "Oh this is a great one!! Okay so here's the thing, and I think you're going "
        "to love where this goes, because it ties together a bunch of ideas in a "
        "really satisfying way, so let's dive right in! First the big picture clicks "
        "into place, and then, honestly, the details just start falling out one after "
        "another like dominoes. The best part is how naturally each piece leads to "
        "the next, so by the time we reach the end it all feels obvious in the very "
        "best way. Trust me, this is going to be fun, so stick with me here!"
    ),
}

# Keyword -> pool routing for steering instructions.
_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("short", "concise", "brief", "tldr", "shorter"), "concise"),
    (("detail", "longer", "more", "explain", "depth", "elaborate"), "detailed"),
    (("french", "francais", "france"), "french"),
    (("pirate", "arr"), "pirate"),
    (("haiku", "poem", "poetry"), "haiku"),
    (("excited", "fun", "energy", "hype"), "excited"),
]


def select_pool(instruction: str) -> str:
    text = instruction.lower()
    for keys, pool in _KEYWORDS:
        if any(k in text for k in keys):
            return pool
    # No keyword matched: rotate to *some* different style so steering is still
    # visible in the demo.
    return _rotate(text)


_ROTATION = itertools.cycle(["detailed", "excited", "concise", "pirate"])


def _rotate(_seed: str) -> str:
    return next(_ROTATION)


def tokenize(text: str) -> list[str]:
    """Split into streamed chunks, keeping trailing spaces so concatenation of
    the stream reproduces the text exactly."""
    out: list[str] = []
    for word in text.split(" "):
        out.append(word + " ")
    if out:
        out[-1] = out[-1].rstrip()
    return out
