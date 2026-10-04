"""
Run the three-arm evaluation and produce a scoring sheet.

    python src/run_eval.py                       run every question through all three arms
    python src/run_eval.py summarize             read your scores and print the results table
    python src/run_eval.py rerun q02:no_context  discard specific answers and run them again

Arms
  no_context   the model alone          - catches answers it already knew
  vector       top-k chunks             - vector_rag.answer
  graph        seed -> traverse -> evidence - retrieve.answer

Resumable: results are saved after every single answer, and anything already
answered is skipped, so a run that stops on the daily cap picks up where it
left off.

Outputs
  data/eval_results.json   every answer, its seeds and its cited passages
  data/eval_scoring.csv    one row per answer, with empty columns for you to
                           score - open it in Excel
"""

import csv
import json
import os
import re
import sys
import time

from openai import APIError

import compare            # no_context()
import retrieve           # retrieve.answer  -> graph arm
import vector_rag         # vector_rag.answer -> vector arm

QUESTIONS_PATH = "data/eval_questions.json"
RESULTS_PATH = "data/eval_results.json"
SCORING_PATH = "data/eval_scoring.csv"

ARMS = {
    "no_context": compare.no_context,
    "vector": vector_rag.answer,
    "graph": retrieve.answer,
}

PAUSE_SECONDS = 25   # spacing between calls, to stay under the per-minute token limit


class DailyCapReached(Exception):
    pass


CITATION = re.compile(r"[\[\u3010](\d+)")   # "[2]" and gpt-oss style "\u30102\u2020L1\u3011"


def cited(answer_text, passages):
    """The passages an answer cites, in either citation style, by their number."""
    nums = sorted({int(n) for n in CITATION.findall(answer_text or "")})
    return [(n, passages[n - 1]) for n in nums if 0 < n <= len(passages)]


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def ask(arm_fn, question, attempts=4):
    """Call one arm, retrying per-minute limits and stopping on the daily cap."""
    for i in range(attempts):
        try:
            return arm_fn(question)
        except APIError as e:
            msg = str(e)
            if "per day" in msg or "TPD" in msg:
                raise DailyCapReached(msg[:200])
            wait = 30 * (2 ** i)
            print(f"      api error ({getattr(e, 'status_code', '')}), waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed after {attempts} attempts")


def run():
    questions = load_json(QUESTIONS_PATH, [])
    results = load_json(RESULTS_PATH, {})

    try:
        for q in questions:
            print(f"\n{q['id']}  [{q['type']}]  {q['question']}", flush=True)
            for arm, fn in ARMS.items():
                key = f"{q['id']}:{arm}"
                done = results.get(key, {})
                # Old-format results kept only the cited passages; vector and
                # graph answers saved that way are rerun so all passages exist.
                stale = arm != "no_context" and "passages" not in done
                if done and "error" not in done and not stale:
                    print(f"   {arm:11} already done", flush=True)
                    continue

                try:
                    r = ask(fn, q["question"])
                    results[key] = {
                        "answer": r["answer"],
                        "seeds": r.get("seeds", []),
                        # every passage the arm received, numbered as the model saw them
                        "passages": [{"text": p["text"], "url": p["url"]}
                                     for p in r.get("passages", [])],
                    }
                    print(f"   {arm:11} ok", flush=True)
                except DailyCapReached:
                    raise
                except Exception as e:
                    results[key] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
                    print(f"   {arm:11} ERROR {results[key]['error']}", flush=True)

                save_json(results, RESULTS_PATH)
                time.sleep(PAUSE_SECONDS)

    except DailyCapReached as e:
        print(f"\nDaily cap reached - progress saved. Run again tomorrow.\n  {e}")

    write_scoring_sheet(questions, results)


def write_scoring_sheet(questions, results):
    """One row per (question, arm). Keeps any scores you've already entered."""
    existing = {}
    if os.path.exists(SCORING_PATH):
        with open(SCORING_PATH, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                existing[(row["id"], row["arm"])] = row

    fields = ["id", "type", "arm", "question", "gold_answer", "answer",
              "citations", "seeds", "correct", "grounded", "comment"]

    rows = []
    for q in questions:
        for arm in ARMS:
            r = results.get(f"{q['id']}:{arm}", {})
            old = existing.get((q["id"], arm), {})
            rows.append({
                "id": q["id"],
                "type": q["type"],
                "arm": arm,
                "question": q["question"],
                "gold_answer": q["answer"],
                "answer": r.get("answer", r.get("error", "NOT RUN")),
                "citations": "\n".join(f"[{n}] {p['text']}  <{p['url']}>"
                                       for n, p in cited(r.get("answer", ""), r.get("passages", []))),
                "seeds": ", ".join(r.get("seeds", [])),
                "correct": old.get("correct", ""),
                "grounded": "NA" if arm == "no_context" else old.get("grounded", ""),
                "comment": old.get("comment", ""),
            })

    # utf-8-sig so Excel shows the rupee sign and curly quotes correctly
    with open(SCORING_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {SCORING_PATH} - fill in 'correct' and 'grounded' with Y or N")


def summarize():
    """Results table from the scored sheet: correct answers by question type and arm."""
    with open(SCORING_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    unscored = [r for r in rows if r["correct"].strip().upper() not in ("Y", "N")]
    if unscored:
        print(f"{len(unscored)} rows not scored yet, e.g. {unscored[0]['id']} / {unscored[0]['arm']}")

    types = list(dict.fromkeys(r["type"] for r in rows))
    arms = list(ARMS)

    def cell(rs):
        scored = [r for r in rs if r["correct"].strip().upper() in ("Y", "N")]
        right = [r for r in scored if r["correct"].strip().upper() == "Y"]
        grounded = [r for r in right if r["grounded"].strip().upper() == "Y"]
        if not scored:
            return "-"
        g = "" if rs and rs[0]["arm"] == "no_context" else f" ({len(grounded)} grounded)"
        return f"{len(right)}/{len(scored)}{g}"

    width = 26
    print(f"\n{'type':16}" + "".join(f"{a:>{width}}" for a in arms))
    for t in types + ["ALL"]:
        line = f"{t:16}"
        for a in arms:
            rs = [r for r in rows if r["arm"] == a and (t == "ALL" or r["type"] == t)]
            line += f"{cell(rs):>{width}}"
        print(line)
    print("\n'grounded' = correct AND the cited passage actually supports the claim.")


def rerun(keys):
    """
    Discard specific answers - and any scores entered for them - then run.

    Keys look like "q02:no_context". Use this whenever a question's wording
    changes: the old answer, and the score given to it, no longer apply.
    """
    results = load_json(RESULTS_PATH, {})
    for key in keys:
        if results.pop(key, None) is None:
            print(f"   {key}: no saved answer, nothing to discard")
        else:
            print(f"   {key}: discarded")
    save_json(results, RESULTS_PATH)

    # Blank the matching scores, so a score for the old answer can't carry over.
    if os.path.exists(SCORING_PATH):
        with open(SCORING_PATH, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        targets = {tuple(k.split(":", 1)) for k in keys}
        for row in rows:
            if (row["id"], row["arm"]) in targets:
                row["correct"] = ""
                row["grounded"] = "NA" if row["arm"] == "no_context" else ""
                row["comment"] = ""
        if rows:
            with open(SCORING_PATH, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)

    run()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summarize":
        summarize()
    elif len(sys.argv) > 2 and sys.argv[1] == "rerun":
        rerun(sys.argv[2:])
    else:
        run()