import pytest

from mei.providers.sse import SseDecoder, SseEvent


def decode_all(chunks: list[bytes]) -> list[SseEvent]:
    d = SseDecoder()
    out = []
    for c in chunks:
        out += d.feed(c)
    return out + d.close()


@pytest.mark.parametrize("sep", [b"\n", b"\r\n", b"\r"])
def test_line_endings(sep):
    raw = b"data: one" + sep + sep + b"data: two" + sep + sep
    assert [e.data for e in decode_all([raw])] == ["one", "two"]


def test_every_split_point_gives_the_same_events():
    raw = "data: {\"t\":\"🌸 café\"}\r\n\r\n: comment\r\nevent: x\r\ndata: a\r\ndata: b\r\n\r\ndata: [DONE]\r\n\r\n".encode()
    expected = decode_all([raw])
    assert [(e.event, e.data) for e in expected] == [("message", '{"t":"🌸 café"}'), ("x", "a\nb"), ("message", "[DONE]")]
    for i in range(1, len(raw)):
        assert decode_all([raw[:i], raw[i:]]) == expected, f"split at {i}"


def test_byte_by_byte():
    raw = "data: ünïcödé\n\n".encode()
    assert [e.data for e in decode_all([bytes([b]) for b in raw])] == ["ünïcödé"]


def test_unterminated_event_is_flushed_on_close():
    assert [e.data for e in decode_all([b"data: tail"])] == ["tail"]


def test_comments_and_unknown_fields_are_ignored():
    assert decode_all([b": ping\n\nid: 3\nretry: 10\n\n"]) == []
