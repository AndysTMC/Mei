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
