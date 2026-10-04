import json
import os
import time

from extract import extract_triples

ARTICLE_DIR = "data/articles"
TRIPLE_DIR = "data/triples"
FAILURE_LOG = "data/extraction_failures.json"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def run(limit=None):
    os.makedirs(TRIPLE_DIR, exist_ok=True)

    names = sorted(n for n in os.listdir(ARTICLE_DIR) if n.endswith(".json"))
    failures = []
    done = 0
    skipped = 0

    for i, name in enumerate(names, 1):
        out_path = os.path.join(TRIPLE_DIR, name)

        if os.path.exists(out_path):
            skipped += 1
            continue

        article = load_json(os.path.join(ARTICLE_DIR, name))
        print(f"[{i}/{len(names)}] {article['title'][:70]}", flush=True)

        try:
            result = extract_triples(article)
        except Exception as e:
            msg = str(e)
            failures.append({"id": name, "reason": f"{type(e).__name__}: {msg[:200]}"})

            # Only the DAILY cap is worth stopping for - nothing will succeed
            # until it resets. Anything else (one oversize article, a burst of
            # per-minute limits) is logged and skipped, and the run carries on.
            if "per day" in msg or "TPD" in msg:
                print("    daily cap reached, stopping", flush=True)
                break
            print("    skipped this article, continuing", flush=True)
            continue

        if result is None:
            failures.append({"id": name, "reason": "parse_failed"})
            continue

        save_json({
            "article_id": article["id"],
            "url": article["url"],
            "title": article["title"],
            "pub_date": article["pub_date"],
            "triples": [t.model_dump() for t in result.triples],
        }, out_path)

        done += 1
        print(f"    {len(result.triples)} triples", flush=True)

        if limit and done >= limit:
            print("limit reached", flush=True)
            break

    if failures:
        existing = load_json(FAILURE_LOG) if os.path.exists(FAILURE_LOG) else []
        save_json(existing + failures, FAILURE_LOG)

    remaining = len(names) - skipped - done
    print(f"\nextracted {done}   skipped {skipped}   remaining ~{remaining}")
    print(f"failures this run: {len(failures)}")


if __name__ == "__main__":
    run()