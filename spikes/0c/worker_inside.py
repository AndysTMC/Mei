"""Runs inside the voice worker's jail (worker_profile.sh): what can it reach? Plays 0.3 s of
silence through PipeWire to prove audio output works; never opens the microphone."""

import json
import os
import socket
import sys
import time

report = {}
try:
    socket.create_connection(("1.1.1.1", 53), timeout=2).close()
    report["network"] = "reachable"
except OSError as e:
    report["network"] = f"blocked ({e.__class__.__name__}: {e.strerror or e})"
try:
    socket.getaddrinfo("example.com", 443)
    report["dns"] = "resolves"
except OSError as e:
    report["dns"] = f"blocked ({e.__class__.__name__})"
home = sys.argv[1]  # what of the person's home shows: only the empty folders leading to bound paths
report["home_entries"] = sorted(os.listdir(home)) if os.path.isdir(home) else None
report["home_files_visible"] = any(os.path.exists(os.path.join(home, p)) for p in
                                   ("Documents", "Downloads", ".ssh", ".bashrc", ".config", ".local/share/keyrings"))
report["session_bus"] = os.path.exists(f"/run/user/{os.getuid()}/bus")
report["pulse_socket"] = os.path.exists(f"/run/user/{os.getuid()}/pulse/native")
report["run_user_entries"] = sorted(os.listdir(f"/run/user/{os.getuid()}"))

import sherpa_onnx as so  # noqa: E402

t = time.perf_counter()
d = "/models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
so.KeywordSpotter(tokens=f"{d}/tokens.txt", encoder=f"{d}/encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
                  decoder=f"{d}/decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
                  joiner=f"{d}/joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx", keywords_file=f"{d}/keywords.txt")
report["kws_load_s"] = round(time.perf_counter() - t, 3)

import subprocess  # noqa: E402

try:
    import sounddevice  # noqa: F401  PortAudio: Ubuntu's build starts its PulseAudio host API first
    report["sounddevice"] = "initialized"
except Exception as e:  # noqa: BLE001
    report["sounddevice"] = f"failed: {str(e)[:120]}"

dump = json.loads(subprocess.run(["/usr/bin/pw-dump"], capture_output=True, text=True, timeout=10).stdout or "[]")
nodes = [o["info"]["props"] for o in dump if o.get("type") == "PipeWire:Interface:Node" and o.get("info")]
report["pipewire_sources"] = sorted(p.get("node.name", "") for p in nodes if p.get("media.class") == "Audio/Source")
report["pipewire_sinks"] = sorted(p.get("node.name", "") for p in nodes if p.get("media.class") == "Audio/Sink")
silence = bytes(4 * 48000 * 3 // 10)  # 0.3 s of float32 zeros, mono, 48 kHz
t = time.perf_counter()
play = subprocess.run(["/usr/bin/pw-cat", "--playback", "--raw", "--format", "f32", "--rate", "48000", "--channels", "1",
                       "--latency", "20ms", "-"], input=silence, capture_output=True, timeout=10)
report["pw_cat_playback"] = f"exit {play.returncode} in {time.perf_counter() - t:.2f} s" + (
    f": {play.stderr.decode()[:120]}" if play.returncode else "")
print(json.dumps(report, indent=1))
