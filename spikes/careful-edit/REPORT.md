# The careful edit: what to run after the recognizer

Date: 2026-10-26. Machine: AMD Ryzen 7 4800H (8 cores, 16 threads, AVX2, no AVX-512/VNNI), 14 GiB.
Software: Python 3.12, sherpa-onnx 1.13.8, onnxruntime 1.31 (CPU), tokenizers 0.23, llama-cpp-python 0.3.36 (built for
this CPU), in a throwaway venv at `~/.cache/mei-spikes/careful-edit/venv`. Nothing was added to the
project's dependencies, and the microphone and speakers were never touched.

**The question.** After Kroko writes what was heard, what should tidy it up? The edit should do light
cleanup, punctuation and grammar that doesn't change the meaning, and keep the raw words. I tried five
kinds of option on the same 43 sentences.

## Recommendation

1. **Ship `rules+` as the always-on step.** It costs 0.03 ms and no RAM, and changed nothing that
   mattered in 43 sentences. It is the seam's `Rules` with three additions:
   - drop "like" after a modal ("we could like move");
   - add an end mark ("?" when the sentence opens like a question, otherwise ".");
   - capitalize the days, the months and Mei.

   This one step does most of the work. On real Kroko output it is as good as anything else measured
   (character error 0.102; the best model chain scored 0.101–0.110).
2. **Never let a model's sentence through as it is.** Every grammar model and every LLM tried changed
   the meaning somewhere: 3 to 31 of 43 sentences by script, and at least one real change by eye in
   every model except Qwen2.5-0.5B (whose 3 flags were rewordings, not changes of meaning). The worst:
   - Qwen3-0.6B: "transfer 40 dollars to sam not 400" became "Transfer $40 to Sam."
   - T5-tiny and T5-mini: "Sam" became "the same", and "don't delete" became "no delete".
   - T5-base invented "go to the park".
   - LFM2.5-1.2B answered the text ("Sure, here it is:").

   The fix is the **guard** in `guard.py`, about 80 lines with no model. It lines up the words and keeps
   a model's change only where the careful edit allows it:
   - punctuation;
   - a capital added, never taken away;
   - a filler or an accidental doubled word removed;
   - a sound-alike swapped for its twin (their/they're, then/than…).

   Anywhere else, the words that were said come back. Behind the guard, **every** option scored 0
   meaning changes, and every one did better than it did on its own.
3. **If a model is wanted on top, use T5-efficient-tiny behind the guard** (visheratin, about 16M
   parameters, int8 ONNX, **33 MB on disk, about 108 MB RAM, about 29 ms p50 and 62–69 ms p95** per
   sentence on 2–4 threads). On typed raw text it is the best quality per cost:
   - exact match 22/43 against 13 for `rules+`;
   - character error 0.031 against 0.041;
   - 4 of 8 sound-alikes fixed.

   On Kroko's own output it adds almost nothing (0.103 against 0.102), because **Kroko already writes
   casing, punctuation and the right spelling of sound-alikes from context**. My advice is to start
   with `rules+` alone, and add T5-tiny behind the guard only if text from other sources (typed, or a
   recognizer that writes lower case) goes through the chain.
4. **Not worth it here:**
   - **Bigger grammar models.** T5-base, 10× the cost of tiny, is no better once guarded.
   - **The 0.5B LLM.** Guarded Qwen2.5-0.5B is the best on paper (26/43 exact, character error 0.026),
     but it costs 469 MB on disk, about 1 GB RAM, 530–670 ms p50 and 2–6 s p95 on this shared CPU.
     That is 20× slower and 10× heavier than tiny for 4 more exact sentences.
   - **Moonshine as a second pass.** It is a different transcript, not an edit. It writes digits
     ("six" becomes "6"), rewrites "gonna/wanna" as "going to", and mishears names and code ("May",
     "cubectle", "pm" for npm), so it doesn't keep the raw words.
   - **CT-Transformer punctuation.** It writes full-width Chinese marks and splits "3:45", "2.5" and
     "user_id" into pieces. Guarded it is fine, but it is 72 MB for what the 7 MB English model does.

Also found, outside this question: **Kroko drops the last words unless about 1.5 s of audio follows
them** (details at the end). The runtime's `finish()` doesn't pad.

## Headline table

All 43 cases, each model fed **after the seam's rules** (the chain as `cleanup.Chain` runs it), 4
threads, latency per sentence after a warm-up pass. "Exact" means character for character against the
reference. "Words" means the right words, ignoring case and punctuation. "Char err" is the character
error rate against the reference (raw text scores 0.132). "Meaning" is the script's flag (see Method),
followed by my count by eye.

| Option | Exact /43 | Words /43 | Char err | Meaning (script / eye) | p50 ms | p95 ms | Disk MB | RAM MB | Load ms |
|---|---|---|---|---|---|---|---|---|---|
| raw words, untouched | 0 | 26 | 0.132 | 0 | — | — | — | — | — |
| 1. rules (seam, as is) | 0 | 32 | 0.073 | 0 / 0 | 0.02 | 0.03 | 0 | 0 | 10 |
| **1. rules+** | 13 | 33 | 0.041 | 0 / 0 | **0.03** | **0.05** | 0 | 0 | 13 |
| 2. punct-en (sherpa CNN-BiLSTM), alone on raw | 2 | 26 | 0.104 | 1 / 0 | 9.9 | 14.3 | 7.3 | 40 | 117 |
| 2. punct-en + guard | 22 | 32 | 0.036 | 0 / 0 | 7.0 | 7.7 | 7.3 | 40 | 91 |
| 2. punct-ct (CT-Transformer int8), alone on raw | 0 | 11 | 0.151 | 18 / 4 | 4.6 | 6.3 | 72 | 161 | 676 |
| 2. punct-ct + guard | 15 | 32 | 0.043 | 0 / 0 | 3.5 | 5.3 | 72 | 162 | 449 |
| 4. T5-efficient-tiny (16M) | 15 | 21 | 0.102 | 12 / 11 | 28.8 | 62.4 | 33 | 108 | 315 |
| **4. T5-efficient-tiny + guard** | 22 | 37 | 0.031 | 0 / 0 | **28.8** | **62.4** | **33** | **108** | 315 |
| 4. T5-efficient-mini (31M) | 15 | 21 | 0.090 | 13 / 12 | 34.5 | 71.5 | 56 | 133 | 326 |
| 4. T5-efficient-mini + guard | 20 | 37 | 0.034 | 0 / 0 | 34.5 | 71.5 | 56 | 133 | 326 |
| 4. T5-small GEC (Unbabel, 60M) | 11 | 30 | 0.057 | 5 / 3 | 52.7 | 135.4 | 92 | 178 | 573 |
| 4. T5-small GEC + guard | 21 | 36 | 0.033 | 0 / 0 | 52.7 | 135.4 | 92 | 178 | 573 |
| 4. T5-small grammar-synthesis (77M) | 8 | 9 | 0.416 | 31 / ~31 | 41.3 | 74.5 | 146 | 267 | 840 |
| 4. T5-small grammar-synthesis + guard | 14 | 33 | 0.043 | 0 / 0 | 41.3 | 74.5 | 146 | 267 | 840 |
| 4. T5-base grammar (vennify, 223M) | 19 | 30 | 0.076 | 7 / 4 | 290 | 514 | 360 | 917 | 1524 |
| 4. T5-base + guard | 21 | 34 | 0.034 | 0 / 0 | 290 | 514 | 360 | 917 | 1524 |
| 5. Qwen2.5-0.5B Q4_K_M | 25 | 35 | 0.033 | 3 / 0 | 672 | 6264 | 469 | 1020 | 2728 |
| 5. Qwen2.5-0.5B + guard | **26** | **37** | **0.026** | 0 / 0 | 672 | 6264 | 469 | 1020 | 2728 |
| 5. Qwen3-0.6B Q4_K_M (no thinking) | 24 | 34 | 0.047 | 3 / 1 | 499 | 3359 | 378 | 1274 | 8259 |
| 5. Qwen3-0.6B + guard | 24 | 36 | 0.029 | 0 / 0 | 499 | 3359 | 378 | 1274 | 8259 |
| 5. LFM2.5-1.2B Q8_0 (one size up, already on disk) | 8 | 25 | 0.211 | 12 / 9 | 1743 | 4174 | 1189 | 1456 | 4900 |
| 5. LFM2.5-1.2B + guard | 17 | 34 | 0.038 | 0 / 0 | 1743 | 4174 | 1189 | 1456 | 4900 |
| chain: punct-en+guard → T5-tiny+guard | 25 | 36 | 0.028 | 0 / 0 | 39.6 | 72.5 | 41 | 148 | 355 |
| chain: T5-tiny+guard → punct-en+guard | 20 | 37 | 0.036 | 1 / 1 | 38.3 | 70.2 | 41 | 146 | 425 |

The same finalists at **2 threads** (what the runtime gives Kroko):

| Option | p50 ms | p95 ms |
|---|---|---|
| punct-en + guard | 9.0 | 11.1 |
| T5-tiny + guard | 29.7 | 68.7 |
| T5-mini + guard | 48.4 | 112.9 |
| T5-small GEC + guard | 73.1 | 209.8 |
| punct-en+guard → T5-tiny+guard | 43.0 | 88.1 |
| Qwen2.5-0.5B + guard | 532 | 2161 |

**Grammar model size ladder** (int8 unless marked; the guard adds microseconds):

| Model | Params | Disk | RAM | p50 / p95 | Meaning changes, unguarded (eye) | Guarded: exact / char err |
|---|---|---|---|---|---|---|
| T5-efficient-tiny | ~16M | 33 MB | 108 MB | 29 / 62 ms | 11 | 22 / 0.031 |
| T5-efficient-mini | ~31M | 56 MB | 133 MB | 34 / 71 ms | 12 | 20 / 0.034 |
| T5-small GEC (Unbabel) | ~60M | 92 MB | 178 MB | 53 / 135 ms | 3 | 21 / 0.033 |
| T5-small grammar-synthesis | ~77M | 146 MB | 267 MB | 41 / 74 ms | ~31 (rewrites freely) | 14 / 0.043 |
| T5-base (vennify) | ~223M | 360 MB | 917 MB | 290 / 514 ms | 4 | 21 / 0.034 |
| Qwen2.5-0.5B Q4_K_M (LLM) | ~494M | 469 MB | 1020 MB | 672 / 6264 ms | 0 (3 rewordings) | 26 / 0.026 |

Bigger is not better here. Once guarded, every T5 lands within 0.031–0.043, and the tiny one is the
best of them.

### On real Kroko output (audio track)

There is no recorded dictation, so Kokoro (the TTS from spike 0c, int8, voice 0) read each case's raw
words, fillers and all, into WAV files. Those files went through Kroko the way the runtime feeds it
(100 ms chunks, then 2 s of silence) and through Moonshine v2 tiny and base (quantized, 2026-02-27) as
a second pass on the whole clip.

| Option | Exact /43 | Char err | WER against the spoken words | p50 / p95 ms | Disk MB | RAM MB |
|---|---|---|---|---|---|---|
| Kroko as heard (cased, punctuated) | 3 | 0.134 | 0.177 | 94 / 182 † | 68 | 147 |
| Kroko → seam rules | 6 | 0.123 | | 0.02 | 0 | 0 |
| **Kroko → rules+** | 18 | **0.102** | | **0.03** | 0 | 0 |
| Kroko → rules → punct-en + guard | 17 | 0.110 | | 7.2 / 7.9 | 7 | 40 |
| Kroko → rules → T5-tiny + guard | 18 | 0.103 | | 27 / 66 | 33 | 107 |
| Kroko → rules → T5-small GEC + guard | 19 | 0.104 | | 52 / 122 | 92 | 178 |
| Kroko → rules → T5-base + guard | 19 | 0.102 | | 302 / 515 | 360 | 915 |
| Kroko → rules → Qwen2.5-0.5B + guard | 19 | 0.101 | | 735 / 5887 | 469 | 1020 |
| Moonshine v2 tiny (second pass) | 14 | 0.102 | 0.137 (0.126 with digits read as words) | 61 / 113 | 42 | 131 |
| Moonshine v2 base (second pass) | 14 | 0.088 | 0.131 (0.120) | 102 / 199 | 135 | 338 |

† Kroko streams while the person speaks. Its figure is only the compute left once speech ends.

On Kroko text every remaining "meaning" flag (16 in every row) is a **recognition** error that no
edit can recover: "Depriya", "New Yen … Zachado", "May" for Mei, "get rebase", "user ID". None is an
edit error. Kroko also writes numbers as words ("forty dollars", "three forty five"), which is a job
for text normalization, not this edit. Moonshine has a lower WER on these synthetic voices and puts
in its own punctuation. But it is a second transcript, not an edit of the first: it writes digits,
turns "gonna/wanna" into "going to", writes "uh-huh", and breaks code words. Using it would mean
choosing between two transcripts, which is a different question from "the careful edit". For voices
this clean, Moonshine base doesn't justify 102 ms and 338 MB on top of Kroko.

## What each option gets wrong (by eye)

Every output, case by case, is in `results/side_by_side.md`.

- **rules+**
  - Can't add commas inside a sentence, can't capitalize names, and leaves sound-alikes alone.
  - "like" stays unless it follows a modal. "it was like twenty minutes" and "I like the second one"
    are rightly kept.
  - Never wrong in a way that matters.
- **punct-en (sherpa CNN-BiLSTM)**
  - Alone it upper-cases odd tokens ("UM", "15TH", "ADD" when the input starts with a capital) and
    leaves the end unmarked or ends on a comma.
  - With the guard (fed with a lower-case first letter, then given an end mark) it is good:
    - names get capitals: Siobhan, Nguyen, Xochitl, Firefox, Tokyo, Monday;
    - run-ons are split well.
  - Its faults: some stray commas ("grab, lunch, wanna, come"), and it capitalizes code words ("Npm",
    "Git Rebase").
- **CT-Transformer**
  - Writes full-width "，。？" and splits "3:45", "2.5", "1,200" and "user_id" into pieces. That damages
    numbers and code (4 cases).
  - No casing.
  - Fine behind the guard (the guard rebuilds every word from the original).
- **T5 grammar models**, on their own:
  - Tiny and mini replace names they don't know (Priya→"the party", Sam→"the same", Xochitl→"the
    account"/"a doctor") and break code (`useEffect`→"perfect", `src/main.ts`→"the scripts").
  - Tiny and mini also drop the negation in "no no don't delete" ("no, no, no delete").
  - Every T5 tokenizer splits `_` and `/`, so `user_id` comes out as "user _ id".
  - T5-base invents objects ("go to the park", "go to a school", "make a call").
  - grammar-synthesis-small rewrites freely ("the build failed again…" → "The builder died a few days
    ago.").
  - The guard fixes all of this. The fixes that survive are the one-for-one sound-alikes: its, whether,
    than, hear.
- **LLMs**
  - Qwen2.5-0.5B is the most careful. Its 3 flags are rewordings: "$40 … $400", "that the plan", and
    "No, don't delete" for "no no don't delete".
  - Qwen3-0.6B **dropped "not 400"** from a money transfer.
  - LFM2.5-1.2B follows or answers the text instead of tidying it ("Sure, let me know.", "Hey there!").
  - None of them fixed "their going" / "your welcome" / "go to" (too), even with an example in the
    prompt.
- **Not fixed by anything with the guard:** "their"→"they're" when a model writes "they are" (two words
  for one, so the guard refuses it), and "right this down"→"write". Kroko spells these right from the
  audio anyway.

## Method

- **Test set** (`cases.json`): 43 dictation-like sentences in 9 groups:
  - fillers (6);
  - stutters, including doubled words meant on purpose: "very very", "no no", "that that" (5);
  - run-ons (4);
  - missing punctuation (5);
  - misheard sound-alikes (8);
  - names (3);
  - numbers, including "not 400" and a self-correction "four no wait five" (4);
  - code words: `npm run build`, `user_id`, `src/main.ts`, `useEffect`, `localhost:8080`, `kubectl` (4);
  - meaning traps: "never said", "don't turn off", "gonna/wanna", "lets eat grandma" (4).

  Each case has a reference careful edit, the tokens that must survive (`keep`), and the sound-alike
  fixes allowed. The raw text is written the way a lower-case recognizer would: no punctuation, fillers
  as words.
- **Meaning-changed flag** (`score.py`). It is raised when any of these happens:
  - a must-keep token is missing (case-sensitive for code like `useEffect`; a comma between "very,
    very" is allowed);
  - the negations or numbers differ from the reference;
  - a content word appears that is in neither the raw words nor the reference;
  - a content word that was said is gone.

  A dropped or added function word counts only as "reworded". I then read every flag for the rows in
  the table. The "eye" count removes script mistakes: full-width punctuation, "$40" for "40 dollars",
  "No, don't" for "no no don't", and "very, very".
- **Latency**: one process per option, one warm-up pass, then 3 timed passes (1 for LLMs). Wall clock
  per sentence, p50 and p95 over all timed sentences.
- **RAM**: the process's peak RSS minus its RSS after imports, so it covers model, runtime arenas and
  KV cache. For GGUF this counts mmapped pages that were touched.
- **Disk**: the files loaded.
- **The machine was shared.** Other sessions were running voice tests the whole time, with a load
  average between 5 and 21 on 16 threads. Absolute latencies are inflated, LLM p95 most of all: the
  OpenMP threads of llama.cpp wait on busy cores. The ordering is clear. On a quiet machine expect lower
  numbers, not a different winner.
- **LLM prompt.** One system prompt and three examples (not from the test set). Its rules: fix
  punctuation, capitals and clear sound-alikes; drop fillers and accidental repeats; change nothing
  else; keep names, numbers, code and slang; never answer the text. Greedy decoding, max tokens 2× the
  input plus 16. The prompt's state is evaluated once and restored before each sentence, and the
  restore is in the timings. llama-cpp-python's own prefix reuse re-read the whole prompt for Qwen3,
  taking 5–8 s per sentence.
- **T5.** Greedy decoding on onnxruntime with a hand-written loop (`bench.py`): a KV cache where the
  export has one (grammar-synthesis-small, base), otherwise the whole prefix each step. Two traps:
  - several `tokenizer.json` files **pad every input to 1024 tokens**. That made the Unbabel model
    write "fg. fg. fg." and everything 10× slower until `no_padding()`;
  - Unbabel's model wants the `gec: ` prefix and vennify's wants `grammar: `.

## Kroko loses the end of a sentence without trailing audio

Found while building the audio track. The Kokoro clips were streamed into Kroko in 100 ms chunks, then
N seconds of zeros, then `input_finished()`, then decoded until nothing was ready. Compared with a 3 s
tail:

| Silence after the clip | 0.5 s | 0.8 s | 1.0 s | 1.2 s | 1.5 s |
|---|---|---|---|---|---|
| Sentences whole /43 | 14 | 21 | 32 | 40 | 43 |
| Words lost /357 | 55 | 35 | 14 | 3 | 0 |

With no padding at all, none came out whole. For example, "open the downloads folder" came out as
"open the downloads f".

`KrokoTranscription.finish()` in `runtime/src/mei/voice/local.py` calls `input_finished()` with no
padding. A turn that ends on a long pause has the silence in the stream already. A turn ended by Enter,
or by a short endpoint (0c measured about 0.8 s), probably loses words.

Feeding about 1.5 s of zeros before `input_finished()` costs about 90 ms of compute and no waiting. I
didn't change the voice code; it belongs to the session building the seam.

## Files

| File | What |
|---|---|
| `fetch_models.sh` | Every model, into `~/.cache/mei-spikes/careful-edit/models` (outside the repository) |
| `cases.json` | The 43 sentences, references and must-keep tokens |
| `rules.py` | `rules+`: the seam's `Rules`, loaded read-only from the runtime, with "like" after a modal, end marks and day/month/Mei capitals |
| `guard.py` | `marks_only` for punctuation models, `words_kept` for T5 and LLMs, `finish` |
| `bench.py` | One option per process: rules, sherpa punctuation, T5 on onnxruntime, LLMs on llama.cpp, chains (`a>b`), `+guard` |
| `audio.py` | Kokoro to WAV (never aloud), then Kroko and Moonshine |
| `score.py` | Flags and scores into `results/summary.json`, `results/side_by_side.md`, `results/table.txt` |
| `run_all.sh` | Everything, one process after another |

To reproduce:

```bash
./fetch_models.sh
```

Then create the venv (Python 3.12, outside the repository):

```bash
uv venv ~/.cache/mei-spikes/careful-edit/venv --python 3.12
```

```bash
CMAKE_ARGS=-DGGML_NATIVE=ON uv pip install --python ~/.cache/mei-spikes/careful-edit/venv/bin/python sherpa-onnx==1.13.8 sherpa-onnx-core==1.13.8 numpy onnxruntime tokenizers psutil llama-cpp-python
```

Then the audio track, one step at a time (`tts`, then `kroko`, `moonshine-tiny`, `moonshine-base`):

```bash
~/.cache/mei-spikes/careful-edit/venv/bin/python audio.py tts
```

Then everything else:

```bash
./run_all.sh
```

The audio track also needs spike 0c's Kokoro and Kroko models in `~/.cache/mei-spikes/0c/models`. The
LFM2.5 row uses a GGUF already in LM Studio's folder.
