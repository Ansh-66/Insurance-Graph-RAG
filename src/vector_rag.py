"""
Vector RAG baseline - the comparison arm for the eval.

Index   every article body is split into ~600-character chunks and embedded
        locally with sentence-transformers. Cached in data/vector_index/.
Query   embed the question, take the top-k chunks by cosine similarity,
        answer with the SAME prompt and model as the graph arm.

The only thing that differs between the two arms is how the context was
found. Everything after that - prompt, model, citation format - is shared,
so any difference in answers comes from retrieval.
"""

import json
import os
import re

import numpy as np
from sentence_transformers import SentenceTransformer

from extract import client, MODEL
from retrieve import ANSWER_PROMPT, short_date

ARTICLE_DIR = "data/articles"
INDEX_DIR = "data/vector_index"
EMB_PATH = os.path.join(INDEX_DIR, "embeddings.npy")
META_PATH = os.path.join(INDEX_DIR, "chunks.json")

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_CHARS = 600

# bge models are trained to expect this prefix on QUERIES (not on documents).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None


def embedder():
    """Load the embedding model once, on first use."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    return [p.strip() for p in parts if p.strip()]


def chunk_article(article):
    """
    Group sentences into ~CHUNK_CHARS chunks, carrying the last sentence of
    each chunk into the next so a fact on a boundary is never split.
    """
    sentences = split_sentences(article["body"])
    chunks, current = [], []

    for s in sentences:
        if current and sum(len(x) for x in current) + len(s) > CHUNK_CHARS:
            chunks.append(" ".join(current))
            current = [current[-1]]          # one sentence of overlap
        current.append(s)
    if current:
        chunks.append(" ".join(current))

    return [{
        "text": c,
        "article_id": article["id"],
        "title": article["title"],
        "url": article["url"],
        "pub_date": article["pub_date"],
    } for c in chunks]


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def article_files():
    return sorted(n for n in os.listdir(ARTICLE_DIR) if n.endswith(".json"))


def build_index():
    chunks = []
    for name in article_files():
        with open(os.path.join(ARTICLE_DIR, name), encoding="utf-8") as f:
            chunks.extend(chunk_article(json.load(f)))

    print(f"embedding {len(chunks)} chunks...", flush=True)
    emb = embedder().encode([c["text"] for c in chunks],
                            normalize_embeddings=True, show_progress_bar=True)

    os.makedirs(INDEX_DIR, exist_ok=True)
    np.save(EMB_PATH, emb)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump({"n_articles": len(article_files()), "chunks": chunks},
                  f, ensure_ascii=False)
    return emb, chunks


def load_index():
    """Load the cached index, rebuilding it if the corpus has changed."""
    if os.path.exists(EMB_PATH) and os.path.exists(META_PATH):
        with open(META_PATH, encoding="utf-8") as f:
            meta = json.load(f)
        if meta["n_articles"] == len(article_files()):
            return np.load(EMB_PATH), meta["chunks"]
        print("corpus changed - rebuilding index", flush=True)
    return build_index()


EMB, CHUNKS = None, None


def search(question, k=10):
    global EMB, CHUNKS
    if EMB is None:
        EMB, CHUNKS = load_index()

    q = embedder().encode([QUERY_PREFIX + question], normalize_embeddings=True)[0]
    scores = EMB @ q                          # cosine, since both are normalized
    top = np.argsort(-scores)[:k]
    return [{**CHUNKS[i], "score": float(scores[i])} for i in top]


# ---------------------------------------------------------------------------
# Answer
# ---------------------------------------------------------------------------

def answer(question, k=10):
    hits = search(question, k=k)

    passages = [{
        "text": h["text"],
        "date": short_date(h["pub_date"]),
        "url": h["url"],
        "title": h["title"],
        "score": h["score"],
    } for h in hits]

    context = "\n".join(f"[{i}] ({p['date']}) {p['text']}"
                        for i, p in enumerate(passages, 1))

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": ANSWER_PROMPT},
            {"role": "user", "content": f"Passages:\n{context}\n\nQuestion: {question}"},
        ],
        temperature=0,
    )
    return {"answer": response.choices[0].message.content, "passages": passages}


if __name__ == "__main__":
    q = "Which bank holds a stake in the life insurer that Prudential part-owns?"
    for i, h in enumerate(search(q), 1):
        print(f"[{i}] {h['score']:.3f}  {h['title'][:60]}")
        print(f"     {h['text'][:120]}")
