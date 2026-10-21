"""The scalar part of GVariant text format, as `gsettings` prints and reads it.

Enough for the allow-listed settings (strings, enums, booleans, numbers). Anything else stays text.
"""

_TYPE_PREFIXES = ("byte ", "int16 ", "uint16 ", "int32 ", "uint32 ", "int64 ", "uint64 ", "double ", "string ")
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", "'": "'", '"': '"'}

Scalar = str | bool | int | float


def parse(text: str) -> Scalar | None:
    """A scalar from GVariant text, or None if it isn't one (arrays, tuples, maybe types)."""
    value = text.strip()
    for prefix in _TYPE_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    if value in ("true", "false"):
        return value == "true"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return _unescape(value[1:-1])
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return None


def loose(text: str) -> Scalar:
    """What a person or model meant by a value: GVariant text, or a bare word as a string."""
    parsed = parse(text)
    return text.strip() if parsed is None else parsed


def same_value(current: str, expected: str) -> bool:
    a, b = parse(current), loose(expected)
    if a is None:
        return " ".join(current.split()) == " ".join(expected.split())
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def to_text(value: Scalar) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _unescape(body: str) -> str:
    out, i = [], 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            out.append(_ESCAPES.get(body[i + 1], body[i + 1]))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)
