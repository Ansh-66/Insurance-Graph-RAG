"""
Checks that the graph seeds are unchanged since the eval was scored.

For every question in data/eval_questions.json, runs retrieve.find_seeds and
compares the result with the seeds stored for that question's graph answer in
data/eval_results.json. If they all match, the published scores still describe
what the current code would retrieve. A CHANGED line means that answer should
be re-run and re-scored.

No LLM calls are made: only the seed matcher runs.

Run from the repo root:

    python check_seeds.py
"""
import json, sys
sys.path.insert(0, "src")
import retrieve

with open("data/eval_questions.json", encoding="utf-8") as f:
    questions = json.load(f)
with open("data/eval_results.json", encoding="utf-8") as f:
    results = json.load(f)

changed = 0
for q in questions:
    stored = results.get(f"{q['id']}:graph", {}).get("seeds")
    new = retrieve.find_seeds(q["question"])
    if stored is None:
        print(f"{q['id']}  no stored seeds   new={new}")
    elif sorted(stored) == sorted(new):
        print(f"{q['id']}  same  {new}")
    else:
        changed += 1
        print(f"{q['id']}  CHANGED  stored={stored}  new={new}")

print(f"\n{changed} eval question(s) changed seeds")
print("live:", retrieve.find_seeds("Who acquired Allianz's stake in Bajaj Allianz Life?"))