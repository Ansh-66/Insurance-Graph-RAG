# Stage 5: reads data/graph.json -> question to retrieved context.
import json
import re
from email.utils import parsedate_to_datetime
from pathlib import Path

from resolve import normalize, slug

# extract (the Groq client) is imported inside answer(), not here. It raises at
# import when GROQ_API_KEY is missing, and seed finding, traversal and context
# assembly need no key: api.py rebuilds demo-mode graph paths with them, and
# check_seeds.py uses find_seeds.

# Repo root, so data paths work no matter which folder Python runs from
# (the agents repo imports this module from outside this repo).
ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "data" / "graph.json", encoding="utf-8") as f:
    GRAPH = json.load(f)

with open(ROOT / "data" / "nodes.json", encoding="utf-8") as f:
    NODES = json.load(f)
LOOKUP = NODES["lookup"]


# ---------------------------------------------------------------------------
# Seed finding: which graph nodes does the question mention?
# ---------------------------------------------------------------------------

# Short names people type in questions that never appear on their own in the
# articles, so resolve.py never saw them as surfaces. Each value is a resolved
# key from nodes.json; a target that doesn't exist is reported at import.
QUERY_ALIASES = {
    "allianz": "allianz se",
    "lic": "life insurance corporation of india",
    "life insurance corporation": "life insurance corporation of india",
    # "General Insurance Corporation (GIC)" normalises to the generic key
    # "general insurance", which GENERIC_KEYS blocks; these keep GIC reachable.
    "gic": "general insurance",
    "general insurance corporation": "general insurance",
    # Pre-2025 names. The articles only use the new names, but readers still
    # type the old ones.
    "bajaj allianz life": "bajaj life insurance",
    "bajaj allianz general": "bajaj general insurance",
}

# Normalised keys that are generic phrases, not names. "Life Insurance
# Corporation (LIC)" normalises to "life insurance", which would otherwise
# seed LIC for every question containing those two words.
GENERIC_KEYS = {"life insurance", "general insurance", "health insurance", "insurance"}


def clean(text):
    """Lowercase, drop possessive 's, turn every non-alphanumeric run into one space.

    Applied identically to the question and to every key, so they compare
    like for like.
    """
    s = text.lower()
    s = re.sub(r"['’]s\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def build_matcher():
    """key -> node_id for every name a question may use to refer to a node."""
    matcher = {}
    for surface, node_id in LOOKUP.items():
        key = clean(normalize(surface))
        if key and key not in GENERIC_KEYS:
            matcher.setdefault(key, node_id)

    for alias, target in QUERY_ALIASES.items():
        node_id = slug(target)
        if node_id in NODES["nodes"]:
            matcher[clean(alias)] = node_id
        else:
            print(f"WARNING: query alias target not in graph: {alias!r} -> {target!r}")

    return matcher


MATCHER = build_matcher()


def find_seeds(question):
    # The question is NOT passed through normalize(): that function is built
    # for company names, and on a whole question it drops a leading possessive
    # word ("Prudential's ...") and strips trailing words that look like suffixes.
    q = f" {clean(question)} "

    hits = [(key, node_id) for key, node_id in MATCHER.items() if f" {key} " in q]
    hits.sort(key=lambda h: len(h[0]), reverse=True)

    # Longest match wins: once "bharti life insurance" is kept, the shorter
    # "bharti life" inside it is skipped.
    kept_keys = []
    kept_ids = []
    for key, node_id in hits:
        if any(f" {key} " in f" {k} " for k in kept_keys):
            continue
        kept_keys.append(key)
        kept_ids.append(node_id)

    return list(dict.fromkeys(kept_ids))


# ---------------------------------------------------------------------------
# Traversal: walk outward from the seeds.
# ---------------------------------------------------------------------------

EDGES = {e["id"]: e for e in GRAPH["edges"]}
ADJ = GRAPH["adjacency"]


def traverse(seeds, hops=2, include_denied=False):
    frontier = set(seeds)
    visited = set(seeds)
    collected = set()

    for _ in range(hops):
        next_frontier = set()
        for node in frontier:
            for entry in ADJ.get(node, []):
                edge = EDGES[entry["edge"]]
                if edge["status"] == "denied" and not include_denied:
                    continue
                collected.add(entry["edge"])
                if entry["neighbor"] not in visited:
                    visited.add(entry["neighbor"])
                    next_frontier.add(entry["neighbor"])
        frontier = next_frontier

    return [EDGES[eid] for eid in sorted(collected)]


# ---------------------------------------------------------------------------
# Stage 6 + 7: assemble context from traversed edges, then generate an answer.
# ---------------------------------------------------------------------------

ANSWER_PROMPT = """You answer questions about the Indian insurance sector using ONLY the
numbered passages provided. Each passage is a sentence from a news article.

Rules:
- Use only facts stated in the passages. Do not use outside knowledge.
- Cite every claim with the passage number in square brackets, like [3].
- If a passage describes talks, approvals, or a deal not yet completed, say so.
- If the passages do not contain the answer, say exactly: "The sources do not say."
- Be brief: two to four sentences."""


def short_date(rfc):
    """'Fri, 03 Jul 2026 07:00:00 GMT' -> '2026-07-03'."""
    try:
        return parsedate_to_datetime(rfc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return "unknown date"


def assemble_context(edges, seeds, max_passages=45, per_edge=2):
    """
    Turn traversed edges into numbered evidence passages for the LLM.

    Passages are taken round-robin: one from every edge first, then a
    second from each, and so on. Every edge gets represented before any
    edge gets repeated, so hop-2 facts are never crowded out by a
    heavily reported hop-1 deal.
    """
    seeds = set(seeds)
    ordered = sorted(edges, key=lambda e: e["src"] not in seeds and e["dst"] not in seeds)

    passages = []
    seen = set()
    for round_no in range(per_edge):
        for e in ordered:
            if len(passages) >= max_passages:
                break
            if round_no >= len(e["sources"]):
                continue
            s = e["sources"][round_no]
            sentence = s["evidence"].strip()
            if sentence in seen:
                continue
            seen.add(sentence)
            passages.append({
                "text": sentence,
                "date": short_date(s["pub_date"]),
                "url": s["url"],
                # Which edge this sentence came from. Not used in the prompt or by
                # run_eval; the frontend uses it to show the path behind an answer.
                "edge": {k: e[k] for k in ("id", "src", "dst", "relation", "status")},
            })

    lines = [f"[{i}] ({p['date']}) {p['text']}" for i, p in enumerate(passages, 1)]
    return "\n".join(lines), passages


def answer(question, hops=2):
    seeds = find_seeds(question)
    if not seeds:
        return {"answer": "No company in the question was found in the graph.",
                "seeds": [], "passages": []}

    edges = traverse(seeds, hops=hops)
    context, passages = assemble_context(edges, seeds)

    from extract import client, MODEL   # needs GROQ_API_KEY; see the note at the top

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": ANSWER_PROMPT},
            {"role": "user", "content": f"Passages:\n{context}\n\nQuestion: {question}"},
        ],
        temperature=0,
    )
    return {"answer": response.choices[0].message.content,
            "seeds": seeds, "passages": passages}


if __name__ == "__main__":
    r = answer("Which bank holds a stake in the life insurer that Prudential part-owns?")
    print("seeds:", r["seeds"])
    print(f"passages: {len(r['passages'])}")
    print()
    print(r["answer"])

    for i, p in enumerate(r["passages"], 1):
        print(f"[{i}] {p['text'][:110]}")