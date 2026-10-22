"""Runs inside the voice worker's jail with the GPU devices bound (worker_profile.sh --gpu): can
Kokoro use CUDA from there, with the network still blocked?"""

import json
import socket
import time

import sherpa_onnx as so

report = {}
try:
    socket.create_connection(("1.1.1.1", 53), timeout=2).close()
    report["network"] = "reachable"
except OSError as e:
    report["network"] = f"blocked ({e.strerror or e})"
d = "/models/kokoro-en-v0_19"
t = time.perf_counter()
tts = so.OfflineTts(so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(kokoro=so.OfflineTtsKokoroModelConfig(
    model=f"{d}/model.onnx", voices=f"{d}/voices.bin", tokens=f"{d}/tokens.txt", data_dir=f"{d}/espeak-ng-data"),
    num_threads=4, provider="cuda")))
report["load_s"] = round(time.perf_counter() - t, 2)
tts.generate("Warm up.", sid=0)
t = time.perf_counter()
tts.generate("It will be sunny tomorrow, around eighteen degrees.", sid=0)
report["first_sentence_s"] = round(time.perf_counter() - t, 3)
print(json.dumps(report))
