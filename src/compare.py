"""
Ask one question three ways and print the answers side by side.

  no context   the model alone - catches answers it already knew
  vector       top-k chunks by similarity
  graph        seed -> traverse -> evidence sentences

This is the seed of the eval harness and of the side-by-side view in the
frontend. Each question costs three model calls.
"""

import sys

from extract import client, MODEL
import retrieve
import vector_rag

NO_CONTEXT_PROMPT = """Answer the question about the Indian insurance sector from your own
knowledge. If you do not know, say exactly: "I don't know." Be brief."""


def no_context(question):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": NO_CONTEXT_PROMPT},
                  {"role": "user", "content": question}],
        temperature=0,
    )
    return {"answer": r.choices[0].message.content, "passages": []}


def cited(answer_text, passages):
    """Only the passages the answer actually cites, by their [n] number."""
    import re
    nums = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer_text)})
    return [(n, passages[n - 1]) for n in nums if 0 < n <= len(passages)]


def show(name, result):
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    print(result["answer"])
    for n, p in cited(result["answer"], result["passages"]):
        print(f"\n  [{n}] {p['text'][:140]}")
        print(f"      {p['url']}")


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else \
        "Which bank holds a stake in the life insurer that Prudential part-owns?"
    print("QUESTION:", q)

    show("NO CONTEXT", no_context(q))
    show("VECTOR RAG", vector_rag.answer(q))
    show("GRAPH RAG", retrieve.answer(q))
