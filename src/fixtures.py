import json
import os
from extract import extract_triples

FIXTURE_DIR = "tests/fixtures"

NAMES = [
    "01_jv_buyout", "02_clean_acquisition", "03_stake_increase",
    "04_denial", "05_prospective_deal", "06_law_firm_advisers",
    "07_unnamed_counterparty", "08_regulatory_approval",
    "09_market_roundup", "10_appointment", "11_bancassurance",
]


def load(name, suffix=""):
    path = os.path.join(FIXTURE_DIR, f"{name}{suffix}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def num(v):
    """Normalise numbers so 51 and 51.0 compare equal; keep None as None."""
    return None if v is None else float(v)


def key_model(t):
    return (t.subject_raw, t.relation, t.object_raw, t.status,
            num(t.stake_pct), num(t.start_date), num(t.end_date))


def key_expected(t):
    return (t["subject_raw"], t["relation"], t["object_raw"], t["status"],
            num(t.get("stake_pct")), num(t.get("start_date")), num(t.get("end_date")))


def structural(k):
    """Just subject, relation, object — attributes stripped."""
    return k[0], k[1], k[2]


def compare(actual, expected):
    a = {key_model(t) for t in actual.triples}
    e = {key_expected(t) for t in expected["expected_triples"]}

    a_struct = {structural(k) for k in a}
    e_struct = {structural(k) for k in e}

    return {
        "exact": a == e,
        "struct": a_struct == e_struct,
        "missing": e - a,
        "extra": a - e,
        "missing_struct": e_struct - a_struct,
        "extra_struct": a_struct - e_struct,
    }


def run_fixture(name, n=1):
    print(f"running {name}...", flush=True)
    article = load(name)
    expected = load(name, "_expected")

    runs = []
    for _ in range(n):
        result = extract_triples(article)
        if result is None:
            runs.append(None)
        else:
            runs.append(compare(result, expected))

    exact = sum(1 for r in runs if r and r["exact"])
    struct = sum(1 for r in runs if r and r["struct"])
    failed = sum(1 for r in runs if r is None)

    return {"name": name, "n": n, "exact": exact, "struct": struct,
            "parse_failed": failed, "runs": runs}


def show(report):
    r = report
    print(f"\n{r['name']}   exact {r['exact']}/{r['n']}   "
          f"structural {r['struct']}/{r['n']}"
          + (f"   PARSE FAILED {r['parse_failed']}" if r["parse_failed"] else ""))

    first_bad = next((x for x in r["runs"] if x and not x["exact"]), None)
    if not first_bad:
        return

    for k in sorted(first_bad["missing"], key=str):
        print(f"    MISSING  {k}")
    for k in sorted(first_bad["extra"], key=str):
        print(f"    EXTRA    {k}")


if __name__ == "__main__":
    reports = [run_fixture(n) for n in NAMES]

    for r in reports:
        show(r)

    total = sum(r["n"] for r in reports)
    print(f"\n{'='*60}")
    print(f"exact      {sum(r['exact'] for r in reports)}/{total}")
    print(f"structural {sum(r['struct'] for r in reports)}/{total}")    