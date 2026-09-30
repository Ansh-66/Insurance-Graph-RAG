# Stage 4: reads resolved triples -> writes data/graph.json; traversal lives here.
"""
Build the knowledge graph from extracted triples and the resolved node registry.

Reads   data/triples/*.json      (from run_extraction.py)
        data/nodes.json          (from resolve.py)
Writes  data/graph.json          nodes, deduplicated edges, adjacency index

Deterministic and free - re-run after every extraction batch.
"""

import json
import os
from collections import Counter, defaultdict

TRIPLE_DIR = "data/triples"
NODES_PATH = "data/nodes.json"
GRAPH_PATH = "data/graph.json"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def edge_key(src, relation, dst, status, stake_pct):
    """
    Two triples are the same edge if all five of these match.

    stake_pct is part of the key so that a 74% holding and a 100% holding
    between the same two companies stay separate edges - they are different
    facts about different points in time.
    """
    return (src, relation, dst, status, stake_pct)


def merge_year(existing, incoming):
    """Keep a known year over an unknown one. Report a genuine conflict."""
    if existing is None:
        return incoming, False
    if incoming is None or incoming == existing:
        return existing, False
    return existing, True    # two different years for one edge


def build():
    registry = load_json(NODES_PATH)
    nodes = registry["nodes"]
    lookup = registry["lookup"]

    edges = {}               # edge_key -> edge record
    dropped = Counter()      # why triples were discarded
    date_conflicts = []

    for fname in sorted(os.listdir(TRIPLE_DIR)):
        if not fname.endswith(".json"):
            continue
        doc = load_json(os.path.join(TRIPLE_DIR, fname))

        for t in doc["triples"]:
            src = lookup.get(t["subject_raw"])
            dst = lookup.get(t["object_raw"])

            # An endpoint with no lookup entry was blocked in resolve.py
            # (e.g. a stock exchange). The whole triple goes.
            if src is None or dst is None:
                dropped["unresolved endpoint"] += 1
                continue

            if src == dst:
                dropped["self-loop"] += 1
                print(f"SELF-LOOP: {t['subject_raw']!r} -> {t['object_raw']!r}  [{doc['title'][:60]}]")
                continue

            key = edge_key(src, t["relation"], dst, t["status"], t["stake_pct"])

            source = {
                "article_id": doc["article_id"],
                "url": doc["url"],
                "pub_date": doc["pub_date"],
                "evidence": t["evidence"],
            }

            if key not in edges:
                edges[key] = {
                    "src": src,
                    "relation": t["relation"],
                    "dst": dst,
                    "status": t["status"],
                    "stake_pct": t["stake_pct"],
                    "start_date": t["start_date"],
                    "end_date": t["end_date"],
                    "role": t["role"],
                    "sources": [source],
                }
                continue

            # Seen before: add the source, and fill in any year we lacked.
            e = edges[key]
            if not any(s["article_id"] == source["article_id"] for s in e["sources"]):
                e["sources"].append(source)

            for field in ("start_date", "end_date"):
                merged, conflict = merge_year(e[field], t[field])
                e[field] = merged
                if conflict:
                    date_conflicts.append((key, field, e[field], t[field]))

    # Assign stable ids now that the edge set is final.
    edge_list = []
    for i, key in enumerate(sorted(edges, key=lambda k: tuple(str(x) for x in k))):
        e = edges[key]
        e["id"] = f"e{i}"
        e["support"] = len(e["sources"])
        edge_list.append(e)

    # Adjacency in BOTH directions. Traversal seeded on the object of an
    # edge must be able to walk it backwards to reach the subject.
    adjacency = defaultdict(list)
    for e in edge_list:
        adjacency[e["src"]].append({"edge": e["id"], "neighbor": e["dst"], "dir": "out"})
        adjacency[e["dst"]].append({"edge": e["id"], "neighbor": e["src"], "dir": "in"})

    # Keep only nodes that actually carry an edge.
    used = {e["src"] for e in edge_list} | {e["dst"] for e in edge_list}
    graph_nodes = {nid: nodes[nid] for nid in used}

    return graph_nodes, edge_list, dict(adjacency), dropped, date_conflicts


def components(adjacency, node_ids):
    """Connected components, ignoring edge direction."""
    seen = set()
    comps = []
    for start in node_ids:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            n = stack.pop()
            comp.append(n)
            for a in adjacency.get(n, []):
                if a["neighbor"] not in seen:
                    seen.add(a["neighbor"])
                    stack.append(a["neighbor"])
        comps.append(comp)
    return sorted(comps, key=len, reverse=True)


def report(nodes, edges, adjacency, dropped, date_conflicts):
    raw_triples = sum(e["support"] for e in edges)
    print(f"nodes             : {len(nodes)}")
    print(f"edges             : {len(edges)}   (from {raw_triples} supporting mentions)")
    print(f"multi-source edges: {sum(1 for e in edges if e['support'] > 1)}")
    for reason, n in dropped.items():
        print(f"dropped           : {n}  ({reason})")
    if date_conflicts:
        print(f"date conflicts    : {len(date_conflicts)}  (first year kept)")

    # Distinct neighbours, not adjacency entries - two edges to the same
    # company count once for fan-out purposes.
    degree = {n: len({a["neighbor"] for a in adjacency.get(n, [])}) for n in nodes}

    print("\nhighest-degree nodes (fan-out risk at traversal time):")
    for nid, d in sorted(degree.items(), key=lambda x: -x[1])[:8]:
        print(f"  {d:3}  {nodes[nid]['canonical']}")

    comps = components(adjacency, list(nodes))
    print(f"\nconnected components: {len(comps)}")
    print(f"  largest : {len(comps[0])} nodes")
    print(f"  sizes   : {[len(c) for c in comps[:10]]}{' ...' if len(comps) > 10 else ''}")


if __name__ == "__main__":
    nodes, edges, adjacency, dropped, date_conflicts = build()

    with open(GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges, "adjacency": adjacency},
                  f, indent=2, ensure_ascii=False)

    report(nodes, edges, adjacency, dropped, date_conflicts)
    print(f"\nwrote {GRAPH_PATH}")