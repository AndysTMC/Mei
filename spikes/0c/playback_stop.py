"""Spike 0c: how fast playback through PipeWire stops when barge-in fires (software side only).
Streams silence through pw-cat and kills it mid-stream, 20 times, and reads the graph's quantum:
after the kill, what is already in the graph (about one quantum) and the card's buffer still play.
The acoustic tail is measured by aec_test.py's barge-in run, not here. Nothing audible plays."""

import json
import os
import re
import signal
import statistics
import subprocess
import time
from pathlib import Path

stops = []
for _ in range(20):
    p = subprocess.Popen(["/usr/bin/pw-cat", "--playback", "--raw", "--format", "f32", "--rate", "24000", "--channels",
                          "1", "--latency", "20ms", "-"], stdin=subprocess.PIPE)
    for _ in range(10):
        p.stdin.write(bytes(4 * 480))  # 20 ms chunks of silence, as sentence audio would arrive
        p.stdin.flush()
    time.sleep(0.1)
    t = time.perf_counter()
    os.kill(p.pid, signal.SIGKILL)  # barge-in: drop the stream at once
    p.wait()
    stops.append(time.perf_counter() - t)
settings = subprocess.run(["/usr/bin/pw-metadata", "-n", "settings"], capture_output=True, text=True).stdout
value = {k: int(v) for k, v in re.findall(r"key:'clock\.(rate|quantum)' value:'(\d+)'", settings)}
out = {"kill_to_exit_ms_median": round(1000 * statistics.median(stops), 2), "kill_to_exit_ms_max": round(1000 * max(stops), 2),
       "graph_quantum_ms": round(1000 * value["quantum"] / value["rate"], 1), "stream_latency_requested_ms": 20}
(Path(__file__).parent / "results").mkdir(exist_ok=True)
(Path(__file__).parent / "results" / "playback_stop.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out))
