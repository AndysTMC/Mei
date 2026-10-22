"""Passing the engine's events to more than one publisher (the D-Bus service, voice)."""

from mei.protocol import Envelope


class Fanout:
    def __init__(self, *sinks) -> None:
        self._sinks = sinks

    def publish(self, events: list[Envelope]) -> None:
        for sink in self._sinks:
            sink.publish(events)

    def publish_ephemeral(self, event: Envelope) -> None:
        for sink in self._sinks:
            sink.publish_ephemeral(event)
