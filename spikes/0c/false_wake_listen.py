"""Spike 0c: false wakes on real room audio. Runs the wake-word model on the microphone for a
number of hours and counts how often it fires. No audio is kept: each 100 ms chunk is spotted and
dropped. GNOME shows the microphone indicator the whole time.

Run it only with the person's agreement, ideally through an ordinary day (talk, TV, calls), and
not saying "Hey Mei". Results: results/false_wake.json (times of each false wake, nothing else).

    ~/.cache/mei-spikes/0c/venv/bin/python false_wake_listen.py --hours 8
"""

import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from bench import SR, spotter  # noqa: E402

HERE = Path(__file__).resolve().parent


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--hours", type=float, default=8.0)
    args.add_argument("--threshold", type=float, default=0.25)
    a = args.parse_args()
    kws = spotter(a.threshold, 1.0)
    stream = kws.create_stream()
    mic = subprocess.Popen(["/usr/bin/pw-record", "--raw", "--format", "f32", "--rate", str(SR), "--channels", "1",
                            "-"], stdout=subprocess.PIPE)
    wakes, started, heard = [], time.monotonic(), 0
    try:
        while time.monotonic() - started < a.hours * 3600:
            chunk = mic.stdout.read(1600 * 4)
            if not chunk:
                break
            heard += len(chunk) // 4
            stream.accept_waveform(SR, np.frombuffer(chunk, dtype=np.float32))
            while kws.is_ready(stream):
                kws.decode_stream(stream)
                if kws.get_result(stream):
                    wakes.append(datetime.datetime.now().isoformat(timespec="seconds"))
                    kws.reset_stream(stream)
                    print("wake", wakes[-1], flush=True)
    except KeyboardInterrupt:
        pass  # stopped early (Ctrl+C or SIGINT): keep what was counted
    finally:
        mic.terminate()
        mic.wait()
    hours = heard / SR / 3600
    out = {"hours": round(hours, 2), "threshold": a.threshold, "false_wakes": len(wakes),
           "per_8h": round(len(wakes) / hours * 8, 2) if hours else None, "at": wakes}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "false_wake.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
