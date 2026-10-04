"""
Find two-hop chains that make good eval questions.

A chain is  A -- B -- C : the question names A, the answer is C, and B is the
bridge the question must never name.

It only counts as a real multi-hop test if NO SINGLE CHUNK mentions both A
and C. Chunks are the unit vector search retrieves, so if one chunk holds
both ends, vector search can answer from that one passage - which is exactly
what happened with the ICICI Bank question.

The test is per chunk, not per article: two facts in the same article but
far apart still land in different chunks, and the chunk with the B-C fact
never mentions A, so nothing about the question pulls it up.

Chains whose two hops are the same relation at the same stake are reported
separately: A and C are probably one company under two names - a
resolution split, not a question.

Reads   data/graph.json, data/articles/*.json
Writes  data/eval_candidates.txt
"""

import json
import os
import re
from itertools import combinations

GRAPH_PATH = "data/graph.json"
ARTICLE_DIR = "data/articles"
CHUNKS_PATH = "data/vector_index/chunks.json"   # the exact chunks vector search uses
OUT_PATH = "data/eval_candidates.txt"
CHUNK_CHARS = 600


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def chunk_text(body):
    """Same chunking as vector_rag.py, used only if its index isn't built yet."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body.replace("\n", " ")) if s.strip()]
    out, cur = [], []
    for s in sents:
        if cur and sum(len(x) for x in cur) + len(s) > CHUNK_CHARS:
            out.append(" ".join(cur))
            cur = [cur[-1]]
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


def mention_pattern(aliases):
    """One regex matching any alias as a whole word, case-insensitive."""
    alts = sorted({a for a in aliases if len(a) >= 3}, key=len, reverse=True)
    if not alts:
        return None
    # Lookarounds instead of \b: \b fails next to brackets, so an alias like
    # "General Insurance Corporation (GIC)" would never match anything.
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(a) for a in alts) + r")(?!\w)", re.I)


def describe(edge, nodes, from_id):
    """Render an edge as text, reading it in the direction it is stored."""
    src, dst = nodes[edge["src"]]["canonical"], nodes[edge["dst"]]["canonical"]
    extra = f" {edge['stake_pct']:g}%" if edge.get("stake_pct") is not None else ""
    status = "" if edge["status"] == "asserted" else f" [{edge['status']}]"
    return f"{src} -{edge['relation']}{extra}-> {dst}{status}"


def main():
    graph = load_json(GRAPH_PATH)
    nodes = graph["nodes"]
    edges = {e["id"]: e for e in graph["edges"]}
    adj = graph["adjacency"]

    # The chunks vector search retrieves. Use the real index if it exists,
    # otherwise rebuild the same chunks the same way.
    if os.path.exists(CHUNKS_PATH):
        chunks = [c["text"] for c in load_json(CHUNKS_PATH)["chunks"]]
    else:
        chunks = []
        for name in os.listdir(ARTICLE_DIR):
            if name.endswith(".json"):
                chunks.extend(chunk_text(load_json(os.path.join(ARTICLE_DIR, name))["body"]))

    mentions = {}
    for nid, n in nodes.items():
        pat = mention_pattern(n["aliases"])
        mentions[nid] = {i for i, text in enumerate(chunks) if pat and pat.search(text)}

    candidates = []
    for bridge in nodes:
        # Usable edges touching the bridge, grouped by the neighbour they reach.
        by_neighbor = {}
        for entry in adj.get(bridge, []):
            e = edges[entry["edge"]]
            if e["status"] == "denied":
                continue
            by_neighbor.setdefault(entry["neighbor"], []).append(e)

        for a, c in combinations(sorted(by_neighbor), 2):
            if nodes[a]["type"] == "person" and nodes[c]["type"] == "person":
                continue

            # Pick the best-supported edge on each side.
            e1 = max(by_neighbor[a], key=lambda e: e["support"])
            e2 = max(by_neighbor[c], key=lambda e: e["support"])

            # The test: no single chunk mentions both ends.
            if mentions[a] & mentions[c]:
                continue

            # Same relation, same stake, same direction on both hops: almost
            # certainly one company under two names.
            mirror = (e1["relation"] == e2["relation"]
                      and e1["stake_pct"] == e2["stake_pct"]
                      and (e1["src"] == bridge) == (e2["src"] == bridge))

            candidates.append({
                "a": a, "bridge": bridge, "c": c,
                "e1": e1, "e2": e2,
                "score": e1["support"] + e2["support"],
                "both_asserted": e1["status"] == "asserted" and e2["status"] == "asserted",
                "mirror": mirror,
            })

    real = [c for c in candidates if not c["mirror"]]
    mirrors = [c for c in candidates if c["mirror"]]
    real.sort(key=lambda x: (not x["both_asserted"], -x["score"]))

    def block(cnd, i):
        a, b, c = (nodes[cnd[k]]["canonical"] for k in ("a", "bridge", "c"))
        out = [f"[{i}]  {a}  --  ({b})  --  {c}",
               f"     hop 1: {describe(cnd['e1'], nodes, cnd['a'])}",
               f"            \"{cnd['e1']['sources'][0]['evidence'][:150]}\"",
               f"     hop 2: {describe(cnd['e2'], nodes, cnd['bridge'])}",
               f"            \"{cnd['e2']['sources'][0]['evidence'][:150]}\"",
               f"     sources: {cnd['e1']['support']} + {cnd['e2']['support']}"
               f"{'' if cnd['both_asserted'] else '   (includes a non-asserted hop)'}",
               ""]
        return out

    lines = [f"{len(real)} cross-chunk two-hop chains\n",
             "Each can be asked in either direction: name one end, the answer is the other.",
             "The bridge must NOT appear in the question.\n"]
    for i, cnd in enumerate(real, 1):
        lines += block(cnd, i)

    lines += ["", "=" * 70,
              f"{len(mirrors)} PROBABLE RESOLUTION SPLITS - not questions",
              "Both hops are the same fact: the two ends are likely one company.",
              "=" * 70, ""]
    for i, cnd in enumerate(mirrors, 1):
        lines += block(cnd, i)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"{len(real)} cross-chunk chains -> {OUT_PATH}")
    print(f"  both hops asserted : {sum(1 for c in real if c['both_asserted'])}")
    print(f"  probable splits    : {len(mirrors)}  (listed at the end of the file)")


if __name__ == "__main__":
    main()
