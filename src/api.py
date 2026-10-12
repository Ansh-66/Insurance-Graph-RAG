"""
Small HTTP API for the frontend.

    uvicorn api:app --reload --app-dir src

Endpoints
  GET  /api/examples         the eval questions, for the example picker
  GET  /api/demo/{qid}       stored eval answers for one question - free, no API key
  POST /api/ask              run a new question live through vector and graph

Demo mode reads data/eval_results.json, so the app works for anyone who clones
the repo, and costs nothing to click around. Live mode spends Groq tokens.
"""

import csv
import collections
import functools
import json
import logging
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

QUESTIONS_PATH = "data/eval_questions.json"
RESULTS_PATH = "data/eval_results.json"
SCORING_PATH = "data/eval_scoring.csv"
NODES_PATH = "data/nodes.json"

ARMS = ["no_context", "vector", "graph"]

CITATION = re.compile(r"[\[【](\d+)")

log = logging.getLogger("api")

app = FastAPI(title="Insurance Graph RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_scores():
    """(question id, arm) -> hand-scored verdict. Read per request so re-scoring shows up live."""
    if not os.path.exists(SCORING_PATH):
        return {}
    with open(SCORING_PATH, encoding="utf-8-sig", newline="") as f:
        return {
            (row["id"], row["arm"]): {
                # a blank cell becomes None (JSON null)
                "correct": row["correct"].strip() or None,
                "grounded": row["grounded"].strip() or None,
                "comment": row["comment"].strip() or None,
            }
            for row in csv.DictReader(f)
        }


@functools.lru_cache(maxsize=1)
def node_names():
    """node id -> canonical display name, from nodes.json."""
    nodes = load_json(NODES_PATH, {}).get("nodes", {})
    return {node_id: n["canonical"] for node_id, n in nodes.items()}


def name_edge(edge):
    """An edge from retrieve.assemble_context, plus display names for both ends."""
    if not edge:
        return None
    names = node_names()
    return {**edge,
            "src_name": names.get(edge["src"], edge["src"]),
            "dst_name": names.get(edge["dst"], edge["dst"])}


def build_path(seeds, traversed, shaped):
    """
    The route from the seeds to every edge the answer cited.

    BFS (breadth-first search, undirected) outward from the seeds over only the
    edges the traversal collected gives each node its shortest distance and the
    edge it was reached by. For each cited edge, the route is the chain of edges
    leading to its nearer endpoint, then the cited edge itself. Edges shared by
    several routes are listed once. Each entry has `cited`: the passage numbers
    that cite it, or [] for an edge that was only walked through.
    """
    by_id = {e["id"]: e for e in traversed}
    neighbors = {}
    for e in traversed:
        neighbors.setdefault(e["src"], []).append((e["dst"], e["id"]))
        neighbors.setdefault(e["dst"], []).append((e["src"], e["id"]))

    dist = {seed: 0 for seed in seeds}
    reached_by = {}  # node -> (previous node, edge id)
    queue = collections.deque(seeds)
    while queue:
        node = queue.popleft()
        for other, edge_id in neighbors.get(node, []):
            if other not in dist:
                dist[other] = dist[node] + 1
                reached_by[other] = (node, edge_id)
                queue.append(other)

    cited_by_edge = {}
    for p in shaped["passages"]:
        if p["n"] in shaped["cited"] and p["edge"]:
            cited_by_edge.setdefault(p["edge"]["id"], []).append(p["n"])

    order = []
    for edge_id in cited_by_edge:
        edge = by_id.get(edge_id)
        if edge is None:
            continue
        route = []
        ends = [n for n in (edge["src"], edge["dst"]) if n in dist]
        if ends:
            node = min(ends, key=lambda n: dist[n])
            while node in reached_by:
                node, step = reached_by[node]
                route.append(step)
            route.reverse()
        for step in route + [edge_id]:
            if step not in order:
                order.append(step)

    return [{**name_edge({k: by_id[i][k] for k in ("id", "src", "dst", "relation", "status")}),
             "cited": cited_by_edge.get(i, [])}
            for i in order]


def attach_edges(qid, stored, shaped):
    """
    Add edge info to a stored graph answer's passages.

    Stored results have no edge info, so the context is rebuilt from the stored
    seeds with the same deterministic traversal (no LLM). The edges are only
    attached if the rebuilt passage texts equal the stored ones, in order;
    otherwise the stored answer came from a different graph state and any
    mapping would be a guess.
    """
    seeds = stored.get("seeds", [])
    if not seeds or not stored.get("passages"):
        return
    try:
        import retrieve
        traversed = retrieve.traverse(seeds)
        _, fresh = retrieve.assemble_context(traversed, seeds)
    except Exception as e:
        log.warning("%s: could not rebuild graph path: %s", qid, e)
        return
    if [p["text"] for p in fresh] != [p["text"] for p in stored["passages"]]:
        log.warning("%s: rebuilt graph passages differ from stored ones; no path shown", qid)
        return
    for out, p in zip(shaped["passages"], fresh):
        out["edge"] = name_edge(p["edge"])
    shaped["path"] = build_path(seeds, traversed, shaped)


def shape(result):
    """
    One arm's answer in the form the frontend expects.

    `cited` lists the passage numbers the answer actually refers to, so the
    frontend can highlight those and leave the rest collapsed.
    """
    answer = result.get("answer", result.get("error", ""))
    passages = result.get("passages", [])
    nums = sorted({int(n) for n in CITATION.findall(answer or "")})
    return {
        "answer": answer,
        "seeds": result.get("seeds", []),
        "passages": [{"n": i, "text": p["text"], "url": p["url"],
                      "edge": name_edge(p.get("edge"))}
                     for i, p in enumerate(passages, 1)],
        "cited": [n for n in nums if 0 < n <= len(passages)],
        "path": [],  # filled in for graph answers by build_path
    }


@app.get("/api/examples")
def examples():
    return [{"id": q["id"], "type": q["type"], "question": q["question"]}
            for q in load_json(QUESTIONS_PATH, [])]


@app.get("/api/demo/{qid}")
def demo(qid: str):
    questions = {q["id"]: q for q in load_json(QUESTIONS_PATH, [])}
    if qid not in questions:
        raise HTTPException(404, f"no question {qid}")

    results = load_json(RESULTS_PATH, {})
    q = questions[qid]
    scores = load_scores()
    arms = {arm: {**shape(results.get(f"{qid}:{arm}", {})),
                  "score": scores.get((qid, arm))}
            for arm in ARMS}
    attach_edges(qid, results.get(f"{qid}:graph", {}), arms["graph"])
    return {
        "id": qid,
        "type": q["type"],
        "question": q["question"],
        "gold_answer": q["answer"],
        "arms": arms,
    }


class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
def ask(req: AskRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "empty question")

    out = {}
    for arm in ("vector", "graph"):
        try:
            # Imported here, inside the try: these load the graph, the embedding
            # model and the Groq client. Demo mode never needs them, and a failed
            # import (no GROQ_API_KEY, a missing package) shows as that arm's
            # error text instead of a bare 500 for the whole request.
            if arm == "vector":
                import vector_rag
                r = vector_rag.answer(question)
            else:
                import retrieve
                r = retrieve.answer(question)
            out[arm] = shape({
                "answer": r["answer"],
                "seeds": r.get("seeds", []),
                "passages": [{"text": p["text"], "url": p["url"], "edge": p.get("edge")}
                             for p in r.get("passages", [])],
            })
            if arm == "graph" and r.get("seeds"):
                out[arm]["path"] = build_path(r["seeds"], retrieve.traverse(r["seeds"]), out[arm])
        except Exception as e:
            out[arm] = shape({"error": f"{type(e).__name__}: {str(e)[:200]}"})

    return {"question": question, "arms": out}