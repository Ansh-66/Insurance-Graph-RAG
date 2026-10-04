# Stage 5: reads data/graph.json -> question to retrieved context.
import json
from email.utils import parsedate_to_datetime

from resolve import normalize
from extract import client, MODEL

with open("data/graph.json", encoding="utf-8")as f:
    GRAPH = json.load(f)

with open("data/nodes.json", encoding="utf-8") as f:
    LOOKUP = json.load(f)["lookup"]

def find_seeds(question):
    q = normalize(question.replace("?", ""))

    hits = []
    for surface, node_id in LOOKUP.items():
        key = normalize(surface)
        if key and f" {key} " in f" {q} ":
            hits.append((key, node_id))

    hits.sort(key=lambda h: len(h[0]), reverse=True)

    kept_keys = []
    kept_ids = []
    for key, node_id in hits:
        if any(f" {key} "  in f" {k} " for k in kept_keys):
            continue
        kept_keys.append(key)
        kept_ids.append(node_id)
    
    return list(dict.fromkeys(kept_ids))


EDGES = {e["id"]: e for e in GRAPH["edges"]}
ADJ = GRAPH["adjacency"]

def traverse(seeds, hops=2, include_denied = False):
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
                if entry['neighbor'] not in visited:
                    visited.add(entry['neighbor'])
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