import json
import os
import time
from typing import Literal, Optional

from dotenv import load_dotenv
from openai import OpenAI, APIError
from pydantic import BaseModel, ValidationError
from json_repair import repair_json

load_dotenv()

# ---- provider: change this ONE line to switch ----
PROVIDER = "groq"          # "groq" | "ollama" | "openrouter"

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "key_env": None,
        "model": "qwen2.5:7b-instruct",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "model": "deepseek/deepseek-v4-flash-0731:free",
    },
}

cfg = PROVIDERS[PROVIDER]

if cfg["key_env"]:
    api_key = os.getenv(cfg["key_env"])
    if not api_key:
        raise RuntimeError(f"{cfg['key_env']} not set — check .env")
else:
    api_key = "local"

MODEL = cfg["model"]

# Article bodies are cut to this length so prompt + body stays under Groq's
# per-minute token limit. Normal news stories are well under it; long
# listicles and roundups get truncated. See docs/scope.md.
MAX_BODY_CHARS = 6000

client = OpenAI(base_url=cfg["base_url"], api_key=api_key, timeout=180.0)

with open("docs/extraction_prompt.md", encoding="utf-8") as f:
    system_instruction = f.read()


class Triple(BaseModel):
    subject_raw: str
    relation: Literal["ACQUIRED", "DISTRIBUTES_FOR", "SUBSIDIARY_OF",
                      "OWNS_STAKE_IN", "APPOINTED"]
    object_raw: str
    status: Literal["asserted", "prospective", "denied"]
    stake_pct: Optional[float] = None
    start_date: Optional[int] = None
    end_date: Optional[int] = None
    role: Optional[str] = None
    evidence: str


class ExtractionResult(BaseModel):
    triples: list[Triple]


def failed_generation(e):
    """The model's rejected output, if Groq included it in a 400 error."""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            return err.get("failed_generation")
    return None


def call_with_retry(messages, attempts=5):
    """
    Call the model and return its raw text output.

    Three kinds of failure are handled differently:
      - daily cap (TPD): give up at once - nothing works until it resets
      - JSON rejected by Groq (400): the model DID produce an answer, Groq
        just refused to pass it on. Return that rejected text so it can be
        repaired locally, instead of paying for another full generation.
      - anything else (per-minute 413/429, server errors): back off and retry
    """
    last = None
    for i in range(attempts):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
            return response.choices[0].message.content
        except APIError as e:
            msg = str(e)
            if "per day" in msg or "TPD" in msg:
                raise RuntimeError(f"daily cap: {msg[:200]}")

            salvage = failed_generation(e)
            if salvage:
                print("    JSON rejected by provider - salvaging its output", flush=True)
                return salvage

            last = e
            wait = 10 * (2 ** i)          # 10, 20, 40, 80, 160 seconds
            print(f"api error ({type(e).__name__} {getattr(e, 'status_code', '')}): "
                  f"{msg[:400]}", flush=True)
            print(f"    waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed after {attempts} attempts: {last}")


def parse(raw):
    """Strict JSON first; if that fails, repair common breakage and try again."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        repaired = repair_json(raw, return_objects=True)
        print("    output repaired before parsing", flush=True)
        return repaired


def extract_triples(article):
    content = (
        f"pub_date: {article['pub_date']}\n"
        f"title: {article['title']}\n"
        f"body: {article['body'][:MAX_BODY_CHARS]}"
    )

    raw = call_with_retry([
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": content},
    ])

    try:
        return ExtractionResult(**parse(raw))
    except (TypeError, ValidationError) as e:
        print(f"parse failed: {e}", flush=True)
        print(str(raw)[:500], flush=True)
        return None


if __name__ == "__main__":
    with open("tests/fixtures/01_jv_buyout.json", encoding="utf-8") as f:
        article = json.load(f)
    print(extract_triples(article))