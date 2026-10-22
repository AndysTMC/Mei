"""Spike 0c: word error rate on the owner's own voice. Records the default mic for --seconds while the
person reads COMMANDS (from bench.py) in order, then transcribes it with Kroko and compares. The
audio stays in memory and is dropped; only the numbers go to results/own_voice.json.

    ~/.cache/mei-spikes/0c/venv/bin/python own_voice.py --seconds 120
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from bench import COMMANDS, SR, recognizer, vad, wer, words  # noqa: E402

HERE = Path(__file__).resolve().parent


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--seconds", type=float, default=120)
    seconds = a.parse_args().seconds
    mic = subprocess.Popen(["/usr/bin/pw-record", "--raw", "--format", "f32", "--rate", str(SR), "--channels", "1", "-"],
                           stdout=subprocess.PIPE)
    want = int(seconds * SR) * 4
    data = b""
    while len(data) < want:
        chunk = mic.stdout.read(min(65536, want - len(data)))
        if not chunk:
            break
        data += chunk
    mic.terminate()
    mic.wait()
    audio = np.frombuffer(data, dtype=np.float32).copy()
    del data
    # One utterance per VAD segment, each with the silence the endpointing leaves.
    v = vad()
    for i in range(0, len(audio), 512):
        v.accept_waveform(audio[i:i + 512])
    v.flush()
    segments = []
    while not v.empty():
        segments.append(np.asarray(v.front.samples, dtype=np.float32))
        v.pop()
    rec = recognizer("kroko", 2)
    heard = []
    for seg in segments:
        s = rec.create_stream()
        s.accept_waveform(SR, np.concatenate([seg, np.zeros(int(0.8 * SR), np.float32)]))
        s.input_finished()
        while rec.is_ready(s):
            rec.decode_stream(s)
        heard.append(rec.get_result(s))
    errors, total = wer([w for c in COMMANDS for w in words(c)], [w for h in heard for w in words(h)])
    per = []
    for c in COMMANDS:  # best-matching heard segment per command, for a readable comparison
        best = min(heard, key=lambda h: wer(words(c), words(h))[0], default="")
        per.append({"said": c, "heard": best})
    out = {"seconds": seconds, "segments": len(segments), "wer": round(errors / max(total, 1), 3), "per_command": per}
    (HERE / "results" / "own_voice.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("segments", "wer")}))


if __name__ == "__main__":
    main()
