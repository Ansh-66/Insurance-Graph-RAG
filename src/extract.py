import json
import os
import time
from typing import Literal, Optional

from dotenv import load_dotenv
from openai import OpenAI, APIError
from pydantic import BaseModel, ValidationError

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


def call_with_retry(messages, attempts=5):
    for i in range(attempts):
        try:
            return client.chat.completions.create(
                model=MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
        except APIError as e:
            wait = 2 ** i
            print(f"api error ({type(e).__name__}), waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed after {attempts} attempts")


def extract_triples(article):
    content = (
        f"pub_date: {article['pub_date']}\n"
        f"title: {article['title']}\n"
        f"body: {article['body']}"
    )

    response = call_with_retry([
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": content},
    ])

    raw = response.choices[0].message.content

    try:
        return ExtractionResult(**json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"parse failed: {e}", flush=True)
        print(raw[:500], flush=True)
        return None


if __name__ == "__main__":
    with open("tests/fixtures/01_jv_buyout.json", encoding="utf-8") as f:
        article = json.load(f)
    print(extract_triples(article))