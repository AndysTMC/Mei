"""What of a reply is spoken: sentences as they complete, markdown as plain words, code and tables
left out with one note."""

from mei.voice.speakable import ON_SCREEN, Sentences


def spoken(*pieces: str) -> list[str]:
    s = Sentences()
    out: list[str] = []
    for piece in pieces:
        out += s.feed(piece)
    return out + s.flush()


def test_sentences_come_out_as_they_complete_while_streaming():
    s = Sentences()
    assert s.feed("It will be sun") == []
    assert s.feed("ny tomorrow. Around eigh") == ["It will be sunny tomorrow."]
    assert s.feed("teen degrees, e.g. warm. Take a") == ["Around eighteen degrees, e.g. warm."]
    assert s.flush() == ["Take a"]


def test_numbers_and_abbreviations_dont_split():
    assert spoken("Version 2.5 costs $3.50 vs. the old one. Done!") == ["Version 2.5 costs $3.50 vs. the old one.", "Done!"]


def test_markdown_is_spoken_as_words():
    assert spoken("## Your day\n- **Dentist** at 4:30\n- Call [Anna](https://x.example)\nSee https://example.com/a.\n") == [
        "Your day.", "Dentist at 4:30.", "Call Anna.", "See a link."]


def test_code_and_tables_are_left_out_with_one_note():
    reply = "Here it is:\n```bash\nls -la\nrm -rf /tmp/x\n```\n| a | b |\n|---|---|\n| 1 | 2 |\nThat's all."
    assert spoken(reply) == ["Here it is:", "That's all.", ON_SCREEN]
    assert spoken("Just words.") == ["Just words."]


def test_the_wake_gate_spots_only_while_someone_talks_and_hears_the_start():
    """WakeGate: no spotting in silence; when a voice starts, the spotter hears the second before it
    in order; it stops a second after the voice does."""
    import numpy as np
    from mei.voice.pipeline import WakeGate

    class Vad:
        def __init__(self) -> None:
            self.voice, self.quiet = False, 0.0

        def is_speech(self, chunk) -> bool:
            self.quiet = 0.0 if self.voice else self.quiet + 0.1
            return self.voice

        def quiet_for(self) -> float:
            return self.quiet

        def reset(self) -> None:
            self.quiet = 0.0

    class Spotter:
        def __init__(self) -> None:
            self.fed: list[float] = []

        def heard(self, chunk) -> bool:
            self.fed.append(float(chunk[0]))
            return float(chunk[0]) == 99

        def reset(self) -> None:
            self.fed.append(-1)

    vad, spotter = Vad(), Spotter()
    gate = WakeGate(vad, spotter)
    chunk = lambda n: np.full(1600, n, np.float32)  # noqa: E731
    assert not any(gate.heard(chunk(n)) for n in range(20))  # 2 s of silence: the spotter never ran
    assert spotter.fed == []
    vad.voice = True
    assert not gate.heard(chunk(20))
    assert spotter.fed == [-1, *range(11, 21)]  # fresh, then the last second before the voice and now
    vad.voice = False
    for n in range(21, 40):
        gate.heard(chunk(n))
    assert spotter.fed[-1] < 39  # stopped a second after the voice did
    vad.voice = True
    assert gate.heard(chunk(99))  # the keyword, when it comes, is heard
