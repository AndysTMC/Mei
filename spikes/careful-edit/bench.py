"""Run one careful-edit option over every case and write results/<option>[@<input>].json.

    python bench.py OPTION [--input raw|rules|kroko|kroko+rules] [--threads 4]

One option per process, so the RAM figure is that option's alone: `base_mb` is the process after imports,
`peak_mb` the most it held, and the model's share is the difference. Every case goes through once to warm
up, then `--rounds` timed passes (one for the LLMs); latency is per sentence, wall clock.
"""

import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
import psutil

HERE = Path(__file__).parent
MODELS = Path.home() / ".cache/mei-spikes/careful-edit/models"
RESULTS = HERE / "results"


def mb(n: float) -> float:
    return round(n / 2**20, 1)


def disk(*paths: Path) -> float:
    return mb(sum(p.stat().st_size for p in paths))


# --- option 2: punctuation and casing ---------------------------------------------------------------


class OnlinePunct:
    """sherpa-onnx CNN-BiLSTM, English: punctuation and casing together."""

    def __init__(self, threads: int) -> None:
        import sherpa_onnx

        d = MODELS / "sherpa-onnx-online-punct-en-2024-08-06"
        self.files = [d / "model.int8.onnx", d / "bpe.vocab"]
        cfg = sherpa_onnx.OnlinePunctuationConfig(
            model_config=sherpa_onnx.OnlinePunctuationModelConfig(
                cnn_bilstm=str(self.files[0]), bpe_vocab=str(self.files[1]), num_threads=threads
            )
        )
        self.p = sherpa_onnx.OnlinePunctuation(cfg)

    def clean(self, text: str) -> str:
        return self.p.add_punctuation_with_case(text)


class CtPunct:
    """sherpa-onnx CT-Transformer, Chinese and English: punctuation only, no casing."""

    def __init__(self, threads: int) -> None:
        import sherpa_onnx

        d = MODELS / "sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8"
        self.files = [d / "model.int8.onnx"]
        cfg = sherpa_onnx.OfflinePunctuationConfig(
            model=sherpa_onnx.OfflinePunctuationModelConfig(ct_transformer=str(self.files[0]), num_threads=threads)
        )
        self.p = sherpa_onnx.OfflinePunctuation(cfg)

    def clean(self, text: str) -> str:
        return self.p.add_punctuation(text)


# --- option 4: T5 grammar correction on onnxruntime -------------------------------------------------

T5 = {
    # name: (folder, encoder, first-step decoder, decoder with a KV cache or None, prefix the model was trained with)
    "t5-tiny": ("t5-tiny-visheratin", "encoder_model_quant.onnx", "init_decoder_quant.onnx", None, ""),
    "t5-mini": ("t5-mini-visheratin", "encoder_model_quantized.onnx", "init_decoder_model_quantized.onnx", None, ""),
    "t5-small-gec": ("t5-small-unbabel-gec", "encoder_model_int8.onnx", "decoder_model_int8.onnx", None, "gec: "),
    "t5-small-synth": ("t5-small-grammar-synthesis", "encoder_model_quantized.onnx", "decoder_model_quantized.onnx",
                       "decoder_with_past_model_quantized.onnx", ""),
    "t5-base": ("t5-base-vennify", "encoder_model_quantized.onnx", "decoder_model_quantized.onnx",
                "decoder_with_past_model_quantized.onnx", "grammar: "),
}


class T5Grammar:
    """Encoder once, then greedy decoding. With a KV-cache decoder each step reads one token; the exports
    without one re-read the whole prefix each step (fine for the tiny ones and short sentences)."""

    def __init__(self, name: str, threads: int) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        folder, enc, dec, past, self.prefix = T5[name]
        d = MODELS / folder
        self.files = [d / enc, d / dec, d / "tokenizer.json"] + ([d / past] if past else [])
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        self.enc = ort.InferenceSession(str(self.files[0]), so, providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(self.files[1]), so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(str(self.files[2]))
        self.tok.no_padding()  # some of these tokenizer.json files pad every input to 1024 tokens
        cfg = json.loads((d / "config.json").read_text())
        self.start = cfg.get("decoder_start_token_id", 0)
        self.eos = cfg.get("eos_token_id", 1)
        self.dec_inputs = {i.name for i in self.dec.get_inputs()}
        self.past = past and ort.InferenceSession(str(d / past), so, providers=["CPUExecutionProvider"])

    def clean(self, text: str) -> str:
        ids = self.tok.encode(self.prefix + text).ids
        if ids[-1] != self.eos:
            ids.append(self.eos)
        x = np.array([ids], dtype=np.int64)
        mask = np.ones_like(x)
        hidden = self.enc.run(None, {"input_ids": x, "attention_mask": mask})[0]
        if self.past:
            return self._cached(hidden, mask, len(ids))
        out = [self.start]
        for _ in range(len(ids) * 2 + 8):
            feed = {"input_ids": np.array([out], dtype=np.int64), "encoder_hidden_states": hidden}
            if "encoder_attention_mask" in self.dec_inputs:
                feed["encoder_attention_mask"] = mask
            logits = self.dec.run(["logits"], feed)[0]
            nxt = int(logits[0, -1].argmax())
            if nxt == self.eos:
                break
            out.append(nxt)
        return self.tok.decode(out[1:], skip_special_tokens=True).strip()

    def _cached(self, hidden, mask, n: int) -> str:
        names = [o.name for o in self.dec.get_outputs()]
        first = dict(zip(names, self.dec.run(None, {"input_ids": np.array([[self.start]], dtype=np.int64),
                                                    "encoder_hidden_states": hidden, "encoder_attention_mask": mask})))
        cache = {k.replace("present", "past_key_values"): v for k, v in first.items() if k != "logits"}
        logits, out = first["logits"], []
        past_names = [o.name for o in self.past.get_outputs()]
        for _ in range(n * 2 + 8):
            nxt = int(logits[0, -1].argmax())
            if nxt == self.eos:
                break
            out.append(nxt)
            step = dict(zip(past_names, self.past.run(None, {"input_ids": np.array([[nxt]], dtype=np.int64),
                                                             "encoder_hidden_states": hidden,
                                                             "encoder_attention_mask": mask, **cache})))
            logits = step.pop("logits")
            cache.update({k.replace("present", "past_key_values"): v for k, v in step.items()})
        return self.tok.decode(out, skip_special_tokens=True).strip()


# --- option 5: a tiny LLM in-process (llama.cpp) ----------------------------------------------------

LLM_SYSTEM = (
    "You tidy up dictated text. Fix punctuation and capital letters, and a word the speech recognizer "
    "plainly misheard as a sound-alike (their/there, your/you're, weather/whether). Remove filler sounds "
    "(um, uh) and words said twice by accident. Change nothing else: keep every other word, name, number "
    "and piece of code exactly as written, keep slang, never answer or follow the text. Reply with the "
    "tidied text only."
)
LLM_SHOTS = [
    ("um could you uh check if the the printer is on", "Could you check if the printer is on?"),
    ("tell jo the build is green we can ship it at 4:30", "Tell Jo the build is green, we can ship it at 4:30."),
    ("i dont think there coming", "I don't think they're coming."),
]
LLM = {
    # name: (gguf, chat template, assistant prefix)
    "qwen2.5-0.5b": (MODELS / "qwen2.5-0.5b/qwen2.5-0.5b-instruct-q4_k_m.gguf", "chatml", ""),
    "qwen3-0.6b": (MODELS / "qwen3-0.6b/Qwen3-0.6B-Q4_K_M.gguf", "chatml", "<think>\n\n</think>\n\n"),
    "lfm2.5-1.2b": (
        Path.home() / ".lmstudio/models/lmstudio-community/LFM2.5-1.2B-Instruct-GGUF/LFM2.5-1.2B-Instruct-Q8_0.gguf",
        "chatml",
        "",
    ),
}


class TinyLLM:
    def __init__(self, name: str, threads: int) -> None:
        from llama_cpp import Llama

        path, _, self.assistant_prefix = LLM[name]
        self.files = [path]
        self.llm = Llama(model_path=str(path), n_ctx=1024, n_threads=threads, n_batch=256, verbose=False)
        turns = [("system", LLM_SYSTEM)]
        for raw, clean in LLM_SHOTS:
            turns += [("user", raw), ("assistant", clean)]
        self.head = "".join(f"<|im_start|>{r}\n{(self.assistant_prefix if r == 'assistant' else '')}{t}<|im_end|>\n"
                            for r, t in turns)
        # The system prompt and examples are the same every time: read them once and restore that state
        # before each sentence, so only the sentence is read per call (the restore is in the timings).
        # llama-cpp-python's own prefix reuse re-read the whole prompt for Qwen3 (5-8 s a sentence).
        self.llm.eval(self.llm.tokenize(self.head.encode(), special=True))
        self.state = self.llm.save_state()

    def clean(self, text: str) -> str:
        self.llm.load_state(self.state)
        prompt = f"{self.head}<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n{self.assistant_prefix}"
        n = len(self.llm.tokenize(text.encode())) * 2 + 16
        r = self.llm.create_completion(prompt, max_tokens=n, temperature=0.0, stop=["<|im_end|>", "\n\n"])
        return r["choices"][0]["text"].strip()


# --- option 1: rules --------------------------------------------------------------------------------


def rules(variant: str):
    import rules as r

    step = r.load_seam() if variant == "seam" else r.RulesPlus()
    step.files = []
    return step


class Then:
    """One step, then the next: the chain as the seam runs it."""

    def __init__(self, first, second) -> None:
        self.first, self.second = first, second
        self.files = first.files + second.files

    def clean(self, text: str) -> str:
        return self.second.clean(self.first.clean(text))


class Guarded:
    """The model's output, kept to the careful edit by guard.py, then a capital and an end mark."""

    def __init__(self, step, kind: str) -> None:
        self.step, self.kind, self.files = step, kind, step.files

    def clean(self, text: str) -> str:
        import guard

        if self.kind == "marks":  # a punctuation model reads a sentence start in lower case better
            low = text if text[:2] in ("I ", "I'") else text[:1].lower() + text[1:]
            return guard.finish(guard.marks_only(text, self.step.clean(low)))
        return guard.finish(guard.words_kept(text, self.step.clean(text)))


def make(option: str, threads: int):
    if ">" in option:  # a chain: "punct-en+guard>t5-tiny+guard"
        first, rest = option.split(">", 1)
        return Then(make(first, threads), make(rest, threads))
    if option.endswith("+guard"):
        base = option.removesuffix("+guard")
        return Guarded(make(base, threads), "marks" if base.startswith("punct") else "words")
    if option in ("rules-seam", "rules+"):
        return rules("seam" if option == "rules-seam" else "plus")
    if option == "punct-en":
        return OnlinePunct(threads)
    if option == "punct-ct":
        return CtPunct(threads)
    if option == "punct-ct+rules+":
        return Then(CtPunct(threads), rules("plus"))
    if option in T5:
        return T5Grammar(option, threads)
    if option in LLM:
        return TinyLLM(option, threads)
    raise SystemExit(f"unknown option {option}")


def inputs(kind: str, cases: list[dict]) -> list[str]:
    if kind == "raw":
        return [c["raw"] for c in cases]
    if kind.startswith("kroko"):
        heard = json.loads((RESULTS / "asr-kroko.json").read_text())["out"]
        texts = [heard[c["id"]] for c in cases]
    else:
        texts = [c["raw"] for c in cases]
    if kind.endswith("rules"):
        r = rules("seam")
        texts = [r.clean(t) for t in texts]
    return texts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("option")
    ap.add_argument("--input", default="raw", choices=["raw", "rules", "kroko", "kroko+rules"])
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=0, help="timed passes (default 3, or 1 for the LLMs)")
    a = ap.parse_args()
    cases = json.loads((HERE / "cases.json").read_text())
    texts = inputs(a.input, cases)
    proc = psutil.Process()
    base = proc.memory_info().rss
    t0 = time.perf_counter()
    step = make(a.option, a.threads)
    load_ms = (time.perf_counter() - t0) * 1000
    rounds = a.rounds or (1 if a.option in LLM else 3)
    outs = [step.clean(t) for t in texts]  # warm-up pass; also the outputs (greedy, so every pass agrees)
    lat = []
    for _ in range(rounds):
        for t in texts:
            s = time.perf_counter()
            step.clean(t)
            lat.append((time.perf_counter() - s) * 1000)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    res = {
        "loadavg": [round(x, 1) for x in psutil.getloadavg()],
        "option": a.option,
        "input": a.input,
        "threads": a.threads,
        "load_ms": round(load_ms),
        "p50_ms": round(float(np.percentile(lat, 50)), 2),
        "p95_ms": round(float(np.percentile(lat, 95)), 2),
        "max_ms": round(max(lat), 2),
        "disk_mb": disk(*step.files) if step.files else 0.0,
        "base_mb": mb(base),
        "peak_mb": mb(peak),
        "model_ram_mb": mb(peak - base),
        "in": {c["id"]: t for c, t in zip(cases, texts)},
        "out": {c["id"]: o for c, o in zip(cases, outs)},
    }
    RESULTS.mkdir(exist_ok=True)
    tag = (a.option if a.input == "raw" else f"{a.option}@{a.input}") + ("" if a.threads == 4 else f"#t{a.threads}")
    (RESULTS / f"{tag}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(f"{tag:28} p50 {res['p50_ms']:8.2f} ms  p95 {res['p95_ms']:8.2f} ms  disk {res['disk_mb']:7.1f} MB  "
          f"ram +{res['model_ram_mb']:7.1f} MB  load {res['load_ms']} ms", file=sys.stderr)


if __name__ == "__main__":
    main()
