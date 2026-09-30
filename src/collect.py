from os import mkdir
from time import time
from urllib.parse import quote_plus
import feedparser
import hashlib
import requests
import os
from googlenewsdecoder import gnewsdecoder
import json
import trafilatura


def build_feed_url(query: str, after: str, before: str) -> str:
    q = quote_plus(f"{query} after:{after} before:{before}")
    return f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def fetch_feed(url: str) -> list[dict]:
    feed = feedparser.parse(url)
    items = []

    for entry in feed.entries:
        source = entry.get("source", {})
        items.append({
            "encoded_link": entry.get("link"),
            "title": entry.get("title"),
            "pub_date": entry.get("published"),
            "publisher": source.get("title"),
            "publisher_url": source.get("href"),
        })

    return items

def load_cache(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def save_cache(cache: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


DECODE_CACHE = "data/cache/decoded.json"

def decode_link(encoded: str) -> str | None:
    cache = load_cache(DECODE_CACHE)

    if encoded in cache:
        return cache[encoded]

    try:
        result = gnewsdecoder(encoded, interval=2)
    except Exception as e:
        print(f"decode failed: {e}")
        return None

    if result.get("status"):
        decoded = result.get("decoded_url")
    else:
        decoded = None

    cache[encoded] = decoded
    save_cache(cache, DECODE_CACHE)
    return decoded


def fetch_html(url: str)->str | None:
    os.makedirs("data/cache/html", exist_ok=True)
    name = hashlib.md5(url.encode()).hexdigest()
    path = f"data/cache/html/{name}.html"
    
    if os.path.exists(path):
        print(f"Cache hit {url}")
        with open(path, encoding="utf-8") as f:
            contents = f.read()
            return contents

    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if response.status_code != 200:
            return None
    except Exception as e:
        print(f"fetch failed: {e}")
        return None

    html = response.text
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return html

def extract_text(html: str) -> str | None:
    return trafilatura.extract(html)

QUERIES = [
    "insurance India acquisition",
    "insurance India partnership",
]

WINDOWS = [
    ("2026-05-01", "2026-06-01"),
    ("2026-06-01", "2026-07-01"),
    ("2026-07-01", "2026-08-01"),
    ("2026-08-01", "2026-09-01"),
]


def save_failures(failures: list) -> None:
    with open("data/failures.json", "w", encoding="utf-8") as f:
        json.dump(failures, f, indent=2, ensure_ascii=False)


def collect(limit = 30):
    os.makedirs("data/articles", exist_ok=True)
    failures = []
    saved = len(os.listdir("data/articles"))

    for query in QUERIES:
        for after, before in WINDOWS:
            items = fetch_feed(build_feed_url(query, after, before))
            for item in items:
                real_url = decode_link(item["encoded_link"])
                if real_url is None:
                    failures.append({"url": item["encoded_link"], "title": item["title"], "reason": "decode_failure"})
                    continue

                name = hashlib.md5(real_url.encode()).hexdigest()
                path = f"data/articles/{name}.json"
                if os.path.exists(path):
                    continue

                html = fetch_html(real_url)
                if html is None:
                    failures.append({"url": item["encoded_link"], "title": item["title"], "reason": "fetch_failed"})
                    continue

                body = extract_text(html)
                if body is None:
                    failures.append({"url": item["encoded_link"], "title": item["title"], "reason": "extraction_failed"})
                    continue

                article = {
                    "id": name,
                    "url": real_url,
                    "title": item["title"],
                    "pub_date": item["pub_date"],
                    "publisher": item["publisher"],
                    "query": query,
                    "collected_at": int(time()),
                    "body": body,
                }

                with open(path, "w", encoding="utf-8") as f:
                    json.dump(article, f, indent=2, ensure_ascii=False)

                saved += 1
                if saved >= limit:
                    save_failures(failures)
                    return

    save_failures(failures)


            
if __name__ == "__main__":
    collect(limit=80)