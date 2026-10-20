"""Work around dbus-fast 5.2.0 treating EAGAIN on its non-blocking socket as fatal (ADR 0003).

`_MessageWriter.write_callback` lets `BlockingIOError` from `sock.send()` reach a generic
`except Exception`, which calls `bus._finalize()` and drops the bus connection whenever the bus
daemon momentarily reads slower than we write. Stage 0a reproduced it 3/3 under load; upstream
`main` has the same code. This replaces that one method with the upstream body plus an
EAGAIN/EINTR branch that keeps the partial buffer and waits for the socket to become writable.
The version check refuses to run on any other dbus-fast, so the patch can't outlive the bug.
"""

import array
import importlib.metadata
import socket

from dbus_fast.aio import message_bus

PATCHED_VERSIONS = {"5.2.0"}


def _write_callback(self, remove_writer: bool = True) -> None:
    sock = self.sock
    try:
        while True:
            if self.buf is None:
                if not self.messages:
                    if remove_writer:
                        self.loop.remove_writer(self.fd)
                    return
                buf, unix_fds, fut = self.messages.popleft()
                self.unix_fds = unix_fds
                self.buf = memoryview(buf)
                self.offset = 0
                self.fut = fut

            try:
                if self.unix_fds and self.negotiate_unix_fd:
                    ancdata = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", self.unix_fds))]
                    self.offset += sock.sendmsg([self.buf[self.offset :]], ancdata)
                    self.unix_fds = None
                else:
                    self.offset += sock.send(self.buf[self.offset :])
            except (BlockingIOError, InterruptedError):
                # Socket buffer full: not an error. Resume when writable.
                self.loop.add_writer(self.fd, self.write_callback)
                return

            if self.offset < len(self.buf):
                self.loop.add_writer(self.fd, self.write_callback)
                return

            self.buf = None
            message_bus._future_set_result(self.fut, None)
    except Exception as e:
        if self.bus._user_disconnect:
            message_bus._future_set_result(self.fut, None)
        else:
            message_bus._future_set_exception(self.fut, e)
        self.bus._finalize(e)


def apply() -> None:
    version = importlib.metadata.version("dbus-fast")
    if version not in PATCHED_VERSIONS:
        raise RuntimeError(f"dbus-fast {version}: re-check whether the EAGAIN fix is still needed")
    message_bus._MessageWriter.write_callback = _write_callback
