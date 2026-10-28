"""Score every results/*.json against cases.json and write results/summary.json and results/side_by_side.md.

Per option:
  exact      the output is the reference, character for character
  words_ok   the words are the reference's words (case and punctuation aside)
  cer        character error rate against the reference, lower is better (raw text scores it too)
  meaning    "meaning changed": a must-keep token is gone or altered, a negation or a number differs from
             the reference, or a content word was dropped or appeared that is in neither raw nor reference
  reworded   a function word was added or dropped that the reference doesn't (raw words not kept, meaning
             probably intact)
The flags are a script's; REPORT.md says where reading by eye disagrees.
"""

import difflib
import json
import re
from pathlib import Path

import guard

HERE = Path(__file__).parent
FUNCTION = frozenset(
    "a an the to of in on at for by with and or but so if is are was were be been am it its it's this that these "
    "those i you he she we they me him her us them my your his our their there they're you're do does did "
    "can could will would should has have had just then than as from up out about into over too also".split()
)
NEGATION = re.compile(r"\b(?:not|never|no|none|nothing|nobody|\w+n't)\b", re.I)
NUMBER = re.compile(
    r"\b(?:\d[\d,.:]*\w*|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|"
    r"forty|fifty|hundred|thousand|twice)\b", re.I)


def words(s: str) -> list[str]:
    return [w for w in (re.sub(r"^[^\w']+|[^\w']+$", "", t.lower()) for t in s.split()) if w]


def cer(out: str, ref: str) -> float:
    sm = difflib.SequenceMatcher(a=ref, b=out, autojunk=False)
    edits = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    return edits / max(len(ref), 1)


def keep_ok(token: str, out: str) -> bool:
    sensitive = token[1:] != token[1:].lower() or bool(re.search(r"[^A-Za-z' ]", token))
    # "very, very" still keeps "very very": a comma between the words is the careful edit's to add
    pat = r"(?<![\w])" + r"[\s,;:.!?]+".join(map(re.escape, token.split())) + r"(?![\w])"
    return re.search(pat, out, 0 if sensitive else re.I) is not None


def judge(case: dict, out: str) -> dict:
    raw_w, ref_w, out_w = words(case["raw"]), words(case["ref"]), words(out)
    why = [f"lost '{k}'" for k in case.get("keep", []) if not keep_ok(k, out)]
    if sorted(NEGATION.findall(out.lower())) != sorted(NEGATION.findall(case["ref"].lower())):
        why.append("negation differs")
    if sorted(n.lower() for n in NUMBER.findall(out)) != sorted(n.lower() for n in NUMBER.findall(case["ref"])):
        why.append("numbers differ")
    reworded = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=ref_w, b=out_w, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        for w in out_w[j1:j2]:  # written but not in the reference
            if w not in raw_w:
                (reworded if w in FUNCTION else why).append(f"+{w}")
        for w in ref_w[i1:i2]:  # in the reference but not written
            if w in raw_w and w not in out_w[j1:j2]:
                (reworded if w in FUNCTION else why).append(f"-{w}")
    return {"meaning": sorted(set(why)), "reworded": reworded}


def main() -> None:
    cases = json.loads((HERE / "cases.json").read_text())
    rows, sides = {}, {c["id"]: {"raw": c["raw"], "ref": c["ref"]} for c in cases}
    rows["(raw words, untouched)"] = {"out": {c["id"]: c["raw"] for c in cases}}
    for f in sorted((HERE / "results").glob("*.json")):
        if f.name == "summary.json":
            continue
        r = json.loads(f.read_text())
        rows[f.stem] = r
        opt = r["option"]
        if opt.startswith(("t5-", "qwen", "lfm")) and ">" not in opt:  # the guard costs microseconds, so it is applied here
            rows[f"{opt}+guard" + f.stem[len(opt):]] = {
                **r, "out": {k: guard.finish(guard.words_kept(r["in"][k], o)) for k, o in r["out"].items()}}
    summary = {}
    for name, r in rows.items():
        js = {c["id"]: judge(c, r["out"][c["id"]]) for c in cases}
        n = len(cases)
        summary[name] = {
            **{k: r[k] for k in ("p50_ms", "p95_ms", "max_ms", "disk_mb", "model_ram_mb", "peak_mb", "load_ms")
               if k in r},
            "exact": sum(r["out"][c["id"]] == c["ref"] for c in cases),
            "words_ok": sum(words(r["out"][c["id"]]) == words(c["ref"]) for c in cases),
            "cer": round(sum(cer(r["out"][c["id"]], c["ref"]) for c in cases) / n, 3),
            "meaning": sum(bool(j["meaning"]) for j in js.values()),
            "reworded": sum(bool(j["reworded"]) for j in js.values()),
            "flags": {cid: j for cid, j in js.items() if j["meaning"] or j["reworded"]},
            "n": n,
        }
        for c in cases:
            sides[c["id"]][name] = r["out"][c["id"]]
    (HERE / "results/summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    lines = []
    for c in cases:
        lines.append(f"### {c['id']} ({c['cat']})\n")
        lines.append("| option | output | flag |\n|---|---|---|")
        for name in ["ref"] + list(rows):
            out = sides[c["id"]].get(name, "")
            j = summary[name]["flags"].get(c["id"]) if name in summary else None
            flag = ""
            if j and j["meaning"]:
                flag = "MEANING " + ", ".join(j["meaning"])
            elif j and j["reworded"]:
                flag = "reworded " + ", ".join(j["reworded"])
            lines.append(f"| {name} | {out.replace('|', '/')} | {flag} |")
        lines.append("")
    (HERE / "results/side_by_side.md").write_text("# Every output, case by case\n\n" + "\n".join(lines))
    print(f"{'option':34} {'exact':>5} {'words':>5} {'cer':>6} {'mean':>4} {'rewd':>4} {'p50':>8} {'p95':>8} "
          f"{'disk':>7} {'ram':>7}")
    for name, s in summary.items():
        print(f"{name:34} {s['exact']:5} {s['words_ok']:5} {s['cer']:6.3f} {s['meaning']:4} {s['reworded']:4} "
              f"{s.get('p50_ms', 0):8.2f} {s.get('p95_ms', 0):8.2f} {s.get('disk_mb', 0):7.1f} "
              f"{s.get('model_ram_mb', 0):7.1f}")


if __name__ == "__main__":
    main()
