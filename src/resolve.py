"""
Resolve raw surface names from extracted triples into canonical nodes.

Reads   data/triples/*.json
Writes  data/nodes.json          the node registry + raw-string lookup
        data/resolution_report.txt  human-readable merge report

Run this after every extraction batch. It is deterministic and cheap -
no API calls - so re-running it is always safe.
"""

import json
import os
import re
from collections import Counter, defaultdict

TRIPLE_DIR = "data/triples"
NODES_PATH = "data/nodes.json"
REPORT_PATH = "data/resolution_report.txt"

SUFFIXES = [
    "private limited", "private ltd", "pvt ltd", "pte ltd", "company limited", "company",
    "co", "group limited", "holdings", "limited", "ltd", "plc", "llc",
    "lp", "inc", "corporation", "corp", "sa", "nv",
]


ALIASES = {
    "360 one": "360 one asset management",
    "360 one asset": "360 one asset management",
    "aggne global": "aggne global it services",
    "guardian india": "guardian india operations",
    "qbe": "qbe insurance",
    "indiafirst life": "indiafirst life insurance",
    "raheja qbe":      "raheja qbe general insurance",

    # Confirmed by reading the edges - same deal, same stake, same price.
    "prudential group":          "prudential",
    "bharti life":               "bharti life insurance",
    "bharti axa life":           "bharti life insurance",   # older name, same company
    "bharti axa life insurance": "bharti life insurance",
    "dic":                       "dabur invest",            # "Dabur Invest Corp" -> "dabur invest"
    "dharampal satyapal group":  "ds group",
    "patanjali":                 "patanjali ayurved",
    "sundari investments":       "vama sundari investments",

    # Found in the full-corpus singles list.
    "360one asset management":     "360 one asset management",   # no space
    "greenlife":                   "greenlife insurance broking",
    "greenlife insurance":         "greenlife insurance broking",
    "greenlife insurance booking": "greenlife insurance broking", # extraction typo
    "icicipru life":               "icici prudential life insurance",

    # Found in the chain-finder's "probable splits" list.
    "life insurance":               "life insurance corporation of india",  # "Life Insurance Corporation (LIC)"
    "lic":                          "life insurance corporation of india",
    "aviva life insurance india":   "aviva life insurance company india",
    "raise financial":              "raise financial services",
    "singapore insurance business": "hsbc life singapore pte",               # "HSBC's Singapore insurance business"
}



BLOCKLIST = {
    "national stock exchange nse",
    "national stock exchange",
    "nse",
    "bombay stock exchange",
    "bse",
    # Not a company: "Prudential's India operations" with the possessive
    # stripped leaves only this description.
    "india operations",
    # Not a company: "Bajaj's insurance ventures" describes Bajaj Life and
    # Bajaj General together.
    "insurance ventures",
}


def normalize(name: str) -> str:
    """Lowercase, strip punctuation and legal suffixes, collapse whitespace."""
    s = re.sub(r"^\w+['\u2019]s\s+", "", name)   # drop "Japan's ", "Singapore's "
    s = re.sub(r"\([^)]*\)", " ", s)              # drop "(DIC)", "(Mauritius)", ...
    s = s.lower()
    s = re.sub(r"^the\s+", "", s)                  # drop a leading "the"
    s = re.sub(r"[.,'\u2019\"()&]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    changed = True
    while changed:
        changed = False
        for suf in SUFFIXES:
            if s.endswith(" " + suf):
                s = s[: -len(suf) - 1].strip()
                changed = True
    return s


def canonical_key(name: str) -> str:
    """Normalised key with the hand-built alias map applied."""
    key = normalize(name)
    return ALIASES.get(key, key)


def slug(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", key).strip("-")


def load_triples():
    """Yield (filename, triple dict) for every extracted triple."""
    for fname in sorted(os.listdir(TRIPLE_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(TRIPLE_DIR, fname), encoding="utf-8") as f:
            doc = json.load(f)
        for t in doc["triples"]:
            yield fname, t


def build():
    counts = Counter()
    variants = defaultdict(set)
    is_org = defaultdict(bool)

    for _, t in load_triples():
        subj, obj = t["subject_raw"], t["object_raw"]

        for raw in (subj, obj):
            counts[raw] += 1
            variants[canonical_key(raw)].add(raw)

        is_org[canonical_key(subj)] = True
        if t["relation"] != "APPOINTED":
            is_org[canonical_key(obj)] = True

    nodes = {}
    lookup = {}
    blocked = []

    for key, raws in variants.items():
        if key in BLOCKLIST:
            blocked.append(key)
            continue

        node_id = slug(key)
        canonical = max(raws, key=lambda r: (counts[r], len(r), r))

        nodes[node_id] = {
            "id": node_id,
            "key": key,
            "canonical": canonical,
            "type": "org" if is_org[key] else "person",
            "aliases": sorted(raws),
            "mentions": sum(counts[r] for r in raws),
        }

        for raw in raws:
            lookup[raw] = node_id

    # Every alias target must survive normalisation and exist in the data.
    # A target that doesn't is a silent no-op - this has bitten twice.
    missing = sorted(set(ALIASES.values()) - set(variants))
    if missing:
        print(f"WARNING: alias targets not found in data: {missing}")

    return nodes, lookup, blocked, counts, variants


def write_report(nodes, blocked, counts, variants):
    lines = []

    merged = {k: v for k, v in variants.items() if len(v) > 1 and k not in BLOCKLIST}
    lines.append(f"MERGES ({len(merged)})")
    lines.append("Read every one. A wrong merge fuses two companies silently.\n")
    for key in sorted(merged):
        lines.append(f"  {key}")
        for raw in sorted(variants[key], key=lambda r: -counts[r]):
            lines.append(f"      {counts[raw]:3}  {raw}")
        lines.append("")

    people = [n for n in nodes.values() if n["type"] == "person"]
    lines.append(f"\nPEOPLE ({len(people)})")
    lines.append("Only ever seen as the object of APPOINTED.\n")
    for n in sorted(people, key=lambda n: n["canonical"]):
        lines.append(f"  {n['canonical']}")

    singles = [n for n in nodes.values() if n["mentions"] == 1]
    lines.append(f"\n\nSINGLE-MENTION NODES ({len(singles)})")
    lines.append("Leaves. They can be a seed or an answer, never a bridge.\n")
    for n in sorted(singles, key=lambda n: n["canonical"]):
        lines.append(f"  {n['canonical']}")

    if blocked:
        lines.append(f"\n\nBLOCKED ({len(blocked)})")
        for key in sorted(blocked):
            lines.append(f"  {key}")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    nodes, lookup, blocked, counts, variants = build()

    with open(NODES_PATH, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "lookup": lookup}, f, indent=2, ensure_ascii=False)

    write_report(nodes, blocked, counts, variants)

    orgs = sum(1 for n in nodes.values() if n["type"] == "org")
    people = sum(1 for n in nodes.values() if n["type"] == "person")
    multi = sum(1 for n in nodes.values() if n["mentions"] > 1)

    print(f"raw surface strings : {len(counts)}")
    print(f"nodes               : {len(nodes)}  ({orgs} org, {people} person)")
    print(f"blocked             : {len(blocked)}")
    print(f"mentioned >1 time   : {multi}   <- bridge-capable")
    print(f"\nwrote {NODES_PATH} and {REPORT_PATH}")    