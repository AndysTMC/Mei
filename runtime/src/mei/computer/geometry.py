"""Where things are on screen (§10.1, decision 0022). Pure: the worker and the tests use it alike.

Three spaces meet here, all measured in spike 0b:
- **Logical**: the Shell's stage coordinates. Windows and monitors are given in them.
- **Element**: AT-SPI's WINDOW extents. They are relative to the window's buffer, so an element's logical
  point is the buffer origin plus its extents (the frame origin is off by the client-side shadow).
  SCREEN extents are zero for GTK4 apps on Wayland and are never used.
- **Frame**: the ScreenCast stream's pixels, physical. A stream reports its position and size in
  logical units; frame width ÷ stream width is the monitor's scale.

Pointer motion through the RemoteDesktop portal is the odd one. Absolute positions are frame pixels,
but positions past the stream's *logical* size are refused, so on a scaled monitor the bottom and right
edges are out of reach. Relative motion is in logical units and reaches them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def intersection(self, other: "Rect") -> "Rect | None":
        left, top = max(self.x, other.x), max(self.y, other.y)
        right = min(self.x + self.width, other.x + other.width)
        bottom = min(self.y + self.height, other.y + other.height)
        return Rect(left, top, right - left, bottom - top) if right > left and bottom > top else None

    @classmethod
    def parse(cls, value) -> "Rect":
        """From the Shell's {x, y, width, height}; ValueError for anything else."""
        if not isinstance(value, dict):
            raise ValueError(f"not a rectangle: {value!r}")
        try:
            numbers = [float(value[k]) for k in ("x", "y", "width", "height")]
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"not a rectangle: {value!r}") from None
        if numbers[2] < 0 or numbers[3] < 0:
            raise ValueError(f"negative size: {value!r}")
        return cls(*numbers)


@dataclass(frozen=True)
class Window:
    """A window as the Shell's ListWindows gives it."""

    id: int
    title: str
    pid: int
    buffer: Rect
    focused: bool = False
    app_id: str = ""

    @classmethod
    def parse(cls, value) -> "Window":
        if not isinstance(value, dict):
            raise ValueError(f"not a window: {value!r}")
        return cls(id=int(value.get("id") or 0), title=str(value.get("title") or ""), pid=int(value.get("pid") or 0),
                   buffer=Rect.parse(value.get("buffer")), focused=bool(value.get("focused")),
                   app_id=str(value.get("app_id") or ""))


@dataclass(frozen=True)
class Stream:
    """One monitor's ScreenCast stream: where it is (logical), and its frames' size (physical)."""

    node: int
    rect: Rect  # position and size, logical
    frame_width: int  # physical; 0 until a frame has been seen

    @property
    def scale(self) -> float:
        return self.frame_width / self.rect.width if self.frame_width and self.rect.width else 1.0


@dataclass(frozen=True)
class Picture:
    """How a snapshot's picture maps to logical points: its top-left corner, and logical units per pixel."""

    x: float
    y: float
    per_pixel: float
    width: int
    height: int

    def logical(self, px: float, py: float) -> tuple[float, float]:
        if not (0 <= px < self.width and 0 <= py < self.height):
            raise ValueError(f"({px:.0f}, {py:.0f}) is outside the {self.width}×{self.height} picture")
        return self.x + px * self.per_pixel, self.y + py * self.per_pixel


def element_point(window: Window, extents: Rect) -> tuple[float, float]:
    """An element's center, logical, from its WINDOW extents."""
    cx, cy = extents.center
    return window.buffer.x + cx, window.buffer.y + cy


def element_rect(window: Window, extents: Rect) -> Rect:
    return Rect(window.buffer.x + extents.x, window.buffer.y + extents.y, extents.width, extents.height)


def stream_at(streams: list[Stream], x: float, y: float) -> Stream | None:
    return next((s for s in streams if s.rect.contains(x, y)), None)


def pointer_moves(stream: Stream, x: float, y: float) -> list[tuple[str, float, float]]:
    """How to put the pointer on the logical point (x, y) of this stream's monitor:
    [("absolute", fx, fy)] in frame pixels when that position is accepted, else an absolute move to the
    nearest accepted position followed by [("relative", dx, dy)] in logical units."""
    if not stream.rect.contains(x, y):
        raise ValueError(f"({x:.0f}, {y:.0f}) isn't on this stream's monitor")
    scale = stream.scale
    fx, fy = (x - stream.rect.x) * scale, (y - stream.rect.y) * scale
    # Accepted positions: inside the stream's logical size, whatever the frame's.
    ax, ay = min(fx, stream.rect.width - 1), min(fy, stream.rect.height - 1)
    if (ax, ay) == (fx, fy):
        return [("absolute", fx, fy)]
    return [("absolute", ax, ay), ("relative", (fx - ax) / scale, (fy - ay) / scale)]


def screen_picture(streams: list[Stream], max_width: int) -> tuple[Picture, list[tuple[Stream, Rect]]]:
    """The whole screen as one picture: every monitor at one scale (logical units, so monitors at different
    scalings line up as they do on screen), at most `max_width` wide. Returns how the picture maps back to
    logical points, and where in it each stream's frame goes (pixels). Space between monitors stays dark."""
    if not streams:
        raise ValueError("no screens")
    left = min(s.rect.x for s in streams)
    top = min(s.rect.y for s in streams)
    right = max(s.rect.x + s.rect.width for s in streams)
    bottom = max(s.rect.y + s.rect.height for s in streams)
    shrink = min(1.0, max_width / (right - left))
    width, height = max(1, round((right - left) * shrink)), max(1, round((bottom - top) * shrink))
    places = [(s, Rect(round((s.rect.x - left) * shrink), round((s.rect.y - top) * shrink),
                       max(1, round(s.rect.width * shrink)), max(1, round(s.rect.height * shrink)))) for s in streams]
    return Picture(left, top, (right - left) / width, width, height), places


def window_picture(window: Window, stream: Stream, max_width: int) -> tuple[Rect, Picture] | None:
    """Which part of the stream's frame shows the window (frame pixels), and how the picture made from
    it, at most `max_width` wide, maps back to logical points. None if the window isn't on it."""
    seen = window.buffer.intersection(stream.rect)
    if seen is None:
        return None
    scale = stream.scale
    crop = Rect(round((seen.x - stream.rect.x) * scale), round((seen.y - stream.rect.y) * scale),
                round(seen.width * scale), round(seen.height * scale))
    shrink = min(1.0, max_width / crop.width) if crop.width else 1.0
    width, height = max(1, round(crop.width * shrink)), max(1, round(crop.height * shrink))
    return crop, Picture(seen.x, seen.y, seen.width / width, width, height)
