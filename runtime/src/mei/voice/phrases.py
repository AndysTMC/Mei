"""What the person says that Mei acts on itself, without asking the model (§11.2, §11.6): "stop" stops
the task, and "yes, do it" answers an approval Mei read out. And how an action is said back.
"""

import re

STOP = re.compile(r"^\s*(stop|cancel|cancel (that|it)|never ?mind|forget it|stop (that|it)|that's enough)[.!]?\s*$", re.I)
# Spoken approval (§11.6): only this explicit phrase, after Mei has read the action back.
CONFIRM = re.compile(r"^\s*(yes|yeah|yep)[,.]?\s+(do it|go ahead)[.!]?\s*$", re.I)
DECLINE = re.compile(r"^\s*(no|nope|don'?t|do not)([,.]?\s+(do it|don'?t|thanks|thank you))?[.!]?\s*$", re.I)
_HOME_PATH = re.compile(r"~/(?:([^/\s]+)/)*([^/\s]+)")


def spoken_ok(effects: dict) -> bool:
    """May a voice approve an action with these effects? (§11.6: a voice in the room isn't verified.)"""
    return (effects.get("mutates") == "local" and effects.get("undo") == "recorded"
            and effects.get("visibility", "private") == "private" and effects.get("disclosure", "none") != "off_machine"
            and not effects.get("loses_data", False))


def speakable_title(title: str) -> str:
    """A card title as it is said: "Move ~/Music/old.txt to the trash" → "move old.txt in Music to the trash"."""
    def say_path(m: re.Match) -> str:
        return f"{m.group(2)} in {m.group(1)}" if m.group(1) else f"{m.group(2)} in your home folder"
    text = _HOME_PATH.sub(say_path, title)
    return text[:1].lower() + text[1:]
