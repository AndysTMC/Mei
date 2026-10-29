"""One picture of a screen, from the session's ScreenCast stream (decision 0022), through the portal's
PipeWire fd: the worker's jail has no PipeWire socket of its own.

The stream is named by its node id with `path`. `target-object` takes a serial or a name, and on a miss
PipeWire falls back to the default video source, which is a camera. `node.dont-fallback` makes a miss
fail instead.
"""

import base64
import os

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib, Gst  # noqa: E402

from mei.computer.geometry import Rect  # noqa: E402

FRAME_TIMEOUT_S = 5
_initialized = False


class FrameError(Exception):
    pass


def grab(fd: int, node: int) -> GdkPixbuf.Pixbuf:
    """One frame of stream `node`, read through the PipeWire connection `fd` (which this closes)."""
    global _initialized
    if not _initialized:
        Gst.init(None)
        _initialized = True
    source = Gst.ElementFactory.make("pipewiresrc")
    convert, sink = Gst.ElementFactory.make("videoconvert"), Gst.ElementFactory.make("appsink")
    if source is None or convert is None or sink is None:
        os.close(fd)
        raise FrameError("GStreamer's PipeWire plugin isn't installed (gstreamer1.0-pipewire)")
    source.set_property("fd", fd)
    source.set_property("path", str(node))
    source.set_property("stream-properties", Gst.Structure.new_from_string(
        "props, node.dont-fallback=(boolean)true, node.dont-reconnect=(boolean)true"))
    source.set_property("num-buffers", 1)
    sink.set_property("caps", Gst.Caps.from_string("video/x-raw,format=RGB"))
    pipeline = Gst.Pipeline()
    for element in (source, convert, sink):
        pipeline.add(element)
    source.link(convert)
    convert.link(sink)
    try:
        pipeline.set_state(Gst.State.PLAYING)
        sample = sink.emit("try-pull-sample", FRAME_TIMEOUT_S * Gst.SECOND)
        if sample is None:
            raise FrameError("the screen's stream gave no picture")
        caps = sample.get_caps().get_structure(0)
        width, height = caps.get_value("width"), caps.get_value("height")
        buffer = sample.get_buffer()
        data = buffer.extract_dup(0, buffer.get_size())
    finally:
        pipeline.set_state(Gst.State.NULL)
    stride = len(data) // height if height else 0
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, False, 8, width, height,
                                           stride)


def screen_png(frames: list[tuple[GdkPixbuf.Pixbuf, Rect]], width: int, height: int) -> str:
    """Each monitor's whole frame, scaled into its place (pixels) in a width × height picture, as base64 PNG."""
    canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, height)
    canvas.fill(0x000000ff)
    for frame, place in frames:
        w, h = min(int(place.width), width - int(place.x)), min(int(place.height), height - int(place.y))
        if w > 0 and h > 0:
            frame.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR).copy_area(0, 0, w, h, canvas, int(place.x),
                                                                                int(place.y))
    return _encode(canvas)


def png(frame: GdkPixbuf.Pixbuf, crop: Rect, width: int, height: int) -> str:
    """The `crop` of a frame, scaled to width × height, as base64 PNG."""
    x = max(0, min(int(crop.x), frame.get_width() - 1))
    y = max(0, min(int(crop.y), frame.get_height() - 1))
    w = max(1, min(int(crop.width), frame.get_width() - x))
    h = max(1, min(int(crop.height), frame.get_height() - y))
    return _encode(frame.new_subpixbuf(x, y, w, h).scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR))


def _encode(picture: GdkPixbuf.Pixbuf) -> str:
    ok, data = picture.save_to_bufferv("png", [], [])
    if not ok:
        raise FrameError("couldn't encode the picture")
    return base64.b64encode(data).decode()
