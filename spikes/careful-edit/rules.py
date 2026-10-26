"""Option 1: plain rules, no model. Two variants.

`seam`: the Rules step in runtime/src/mei/voice/cleanup.py as the parallel session has it (loaded by path,
read-only), so the numbers are for the code that will ship.
`plus`: the seam's rules and three more: "like" as a filler after a modal ("we could like move"), a question
mark or full stop to end, and capitals for the days, the months and Mei. Still no model.
"""

import importlib.util
import re
from pathlib import Path

SEAM = Path.home() / "Spaces/Code/mei/runtime/src/mei/voice/cleanup.py"


def load_seam():
    spec = importlib.util.spec_from_file_location("seam_cleanup", SEAM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Rules()


_LIKE_AFTER_MODAL = re.compile(r"\b(can|could|should|will|might|must|may|gonna|just)\s+like\s+(?=\w)", re.I)
_LIKE_AFTER_FILLER = re.compile(r"(?:^|(?<=\s))(?:so\s+)?like,?\s+(?=(?:um|uh|you know)\b)", re.I)
_QUESTION = re.compile(
    r"^(?:hey \w+,? )?(?:can|could|would|will|should|shall|is|are|am|was|were|do|does|did|have|has|had|"
    r"what|what's|when|where|who|whom|whose|why|how|which)\b",
    re.I,
)
_PROPER = {w.lower(): w for w in (
    "Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April June July "
    "August September October November December Mei").split()}


class RulesPlus:
    name = "rules+"

    def __init__(self) -> None:
        self.seam = load_seam()

    def clean(self, text: str) -> str:
        text = _LIKE_AFTER_MODAL.sub(lambda m: m.group(1) + " ", text)
        text = _LIKE_AFTER_FILLER.sub("", text)
        text = self.seam.clean(text)
        text = re.sub(r"\b\w+\b", lambda m: _PROPER.get(m.group(0).lower(), m.group(0)), text)
        if text and text[-1] not in ".?!":
            text += "?" if _QUESTION.match(text) else "."  # a question when it opens like one
        return text[:1].upper() + text[1:]
