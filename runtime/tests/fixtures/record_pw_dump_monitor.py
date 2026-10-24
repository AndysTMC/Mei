"""Records pw-dump-monitor.txt for test_voice_mic_users.py, in a private PipeWire (pipewire_lab.py):
Mei's own recorder comes and goes, then another app's. Nothing plays aloud; no real microphone.
Only nodes and removals are kept, so the fixture stays small.

    cd runtime && uv run --extra voice python tests/fixtures/record_pw_dump_monitor.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import pipewire_lab  # noqa: E402


def record(lab: pipewire_lab.Lab, name: str, seconds: float = 0.6) -> None:
    proc = subprocess.Popen(["pw-record", "--target", pipewire_lab.MIC, "-P", f"{{ node.name = {name} }}", "/dev/null"],
                            env=lab.env, stderr=subprocess.DEVNULL)
    time.sleep(seconds)
    proc.kill()
    proc.wait()
    time.sleep(0.4)


def main() -> None:
    with pipewire_lab.Lab() as lab:
        raw = lab.root / "monitor.txt"
        with open(raw, "wb") as out:
            monitor = subprocess.Popen(["pw-dump", "--monitor", "--no-colors"], env=lab.env, stdout=out,
                                       stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            record(lab, "mei.microphone")
            record(lab, "otherapp")
            monitor.kill()
            monitor.wait()
        kept, lines = [], []
        for line in raw.read_text().splitlines():
            lines.append(line)
            if line == "]":
                batch = [o for o in json.loads("\n".join(lines))
                         if o.get("info") is None or o.get("type") == "PipeWire:Interface:Node"]
                lines = []
                for o in batch:
                    if o.get("info"):  # props only: ports, params and timing don't matter here
                        o["info"] = {"props": o["info"].get("props") or {}}
                if batch:
                    kept.append(json.dumps(batch, indent=2))
        (Path(__file__).parent / "pw-dump-monitor.txt").write_text("\n".join(kept) + "\n")


if __name__ == "__main__":
    main()
