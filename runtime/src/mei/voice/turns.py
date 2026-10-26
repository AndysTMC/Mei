"""When the person's turn ends: the turn detector seam (decision 0029).

A detector is asked once per pause, when the person stops talking: how much quiet ends their turn?
`math.inf` means they sound mid-thought, so Mei waits for them with no timer (pressing again still
sends at once). Detectors are swappable: the word list here works with no model at all and is what
runs when nothing better is installed; a model that hears intonation (Smart Turn) goes behind the
same interface.
"""

import math
from typing import Protocol

import numpy as np

# Words a sentence doesn't end on: after them the person is still thinking, so Mei waits longer.
TRAILING = frozenset("""a an and are as at because but by for from if in is like my of on or so than that the then to
uh um was what when where which while who why will with would your""".split())
UNFINISHED_S = 2.5  # how long Mei waits after "and…", "um…", or a single word
WAIT = math.inf  # "they sound mid-thought": no timer


class TurnDetector(Protocol):
    name: str
    # Seconds of this turn's audio the detector wants (the Listener keeps no more than that); 0: none.
    audio_s: float

    def pause_for(self, said: str, audio: np.ndarray) -> float:
        """The person paused after saying `said` (the latest partial text); `audio` is the end of this
        turn's audio, 16 kHz. Returns the seconds of quiet that end the turn, or WAIT."""
        ...


def unfinished(said: str) -> bool:
    """Does what was heard so far sound like it stops mid-thought?"""
    words = said.lower().replace(",", " ").split()
    return len(words) < 2 or words[-1].strip(".!?") in TRAILING


class WordTurn:
    """By the last word: the settings' pause after a finished-sounding sentence, at least
    UNFINISHED_S after one left hanging (decision 0028). A longer setting is never shortened."""

    name = "words"
    audio_s = 0.0

    def __init__(self, base_s: float = 0.8) -> None:
        self.base_s = base_s

    def pause_for(self, said: str, audio: np.ndarray | None = None) -> float:
        return max(self.base_s, UNFINISHED_S) if unfinished(said) else self.base_s
