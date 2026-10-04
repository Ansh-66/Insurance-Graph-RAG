# Insurance Graph RAG

Multi-hop question answering over Indian insurance-sector news, built as a knowledge graph and measured against a vector RAG baseline on the same articles.

The question this project asks is narrow: **when the facts needed to answer a question sit in different articles, does walking a knowledge graph find the answer where similarity search does not?** Everything here exists to answer that with a measurement rather than a demo.

## Result

Eleven questions, three ways of answering each, one run per answer.

| Question type | Model alone | Vector RAG | Graph RAG |
|---|---|---|---|
| Cross-chunk multi-hop | 1/4 | 3/4 | **4/4** |
| Same-chunk multi-hop | 1/3 | 2/3 | **3/3** |
| Single-hop lookup | 0/2 | 2/2 | 2/2 |
| Extraction gap | 1/1 | **1/1** | 0/1 |
| Unanswerable | 0/1 | 1/1 | 1/1 |
| **All** | **3/11** | **9/11** | **10/11** |

Of the correct answers, 8 of vector's and 9 of graph's cite a passage that actually supports the claim. The remaining correct answers are refusals on the unanswerable question, which have nothing to cite.

**How to read this.** Graph RAG answered one more question than vector RAG. On eleven questions, each run once, that is a direction rather than a proof. Output varies between runs even at temperature 0 (see [Extraction](#extraction)), and rewording one question during the eval flipped vector's answer from wrong to right. The honest summary is narrower than "graph beats vector":

- **Where the graph won:** a cross-chunk question where vector search never retrieved the needed passage, and a same-chunk question where vector misread who was buying whom.
- **Where vector won:** the one article the graph lost during extraction. Vector indexed all 115 articles; the graph only has the 110 that extracted cleanly.
- **The clearest finding is the first column.** Without retrieval the model scored 3/11, and its wrong answers were confident and specific: a 49% stake that was really 75%, the wrong seller of a stake, and an acquisition of Star Health that never happened. Both retrieval arms refused that last one. Its three correct answers are facts it already knew or could guess from a company name, which is why they cannot count as wins for either retrieval method.

## Why multi-hop is hard for vector search

Vector retrieval scores each passage against the question independently. A two-hop question names one company and asks about another that is connected to it through a third, which the question never names. The passage holding the second hop mentions the bridge and the answer, but not the company in the question, so nothing about the question pulls it up.

A graph handles this by structure instead of similarity: start at the company the question names, walk to its neighbours, then to theirs.

**But news is redundant.** Journalists restate background constantly ("ICICI Bank, which holds 50.9%...") so many questions that look multi-hop are answered by a single paragraph. The first test question in this project turned out to be one of them, and vector answered it correctly. That shaped the evaluation: questions are labelled by whether a single passage holds the whole chain, and a script finds chains where none does.

## Pipeline

```
collect -> extract -> resolve -> build -> traverse -> assemble -> generate
                                                         \
                                     vector baseline ----> evaluate
```

| Stage | File | What it does |
|---|---|---|
| Collect | `src/collect.py` | Google News RSS queries, link decoding, page fetch, body extraction. Cached at every step. |
| Extract | `src/extract.py`, `src/run_extraction.py` | LLM turns each article into typed relations, validated with Pydantic. Resumable across days. |
| Test extraction | `src/fixtures.py` | Scores the extractor against 11 hand-built test articles. |
| Resolve | `src/resolve.py` | Collapses name variants into canonical companies. |
| Build | `src/graph.py` | Deduplicated edges, each carrying its source sentences. |
| Retrieve | `src/retrieve.py` | Finds the companies a question names, walks two hops, assembles evidence, generates a cited answer. |
| Baseline | `src/vector_rag.py` | Chunk, embed locally, top-k by cosine, same prompt and model. |
| Compare | `src/compare.py` | One question, three answers side by side. |
| Choose questions | `src/find_chains.py` | Lists two-hop chains no single passage can answer. |
| Evaluate | `src/run_eval.py` | Runs all arms, writes a scoring sheet, summarises scores. |

## Data

115 articles collected from Google News RSS, using queries aimed at acquisitions and partnerships in the Indian insurance sector. Queries targeted relations rather than the sector as a whole: a sector-wide query returns market commentary and rulings that contain no relations between companies, while relation-targeted queries returned named company pairs in 15 of 20 headlines.

The articles themselves are not in this repository. `data/` is git-ignored except for the evaluation files.

## Extraction

Each article is sent to `openai/gpt-oss-120b` (via Groq) with a specification in `docs/extraction_prompt.md`. The output is validated against a Pydantic schema; anything that fails is logged, never silently dropped.

### Schema

Five relations: `OWNS_STAKE_IN`, `ACQUIRED`, `SUBSIDIARY_OF`, `DISTRIBUTES_FOR`, `APPOINTED`.

Each relation carries properties rather than encoding them in the label:

- **status**: `asserted`, `prospective` or `denied`. Indian deal news is full of announced-but-unapproved deals; recording those as completed would systematically report ownership changes that have not happened.
- **start and end years**: a relation is a fact about an interval. Holdings are closed, never deleted, so the graph can answer both "who owns this now" and "who used to".
- **stake percentage**, where stated.
- **evidence**: one sentence copied verbatim from the article. This is what the answering model eventually reads, and what makes every answer checkable.

`ACQUIRED` fires only when an event takes the buyer across 50%. A stake edge records a level; it never records a crossing, so this is the one fact `ACQUIRED` carries that no other edge can. An earlier version fired at 100% ownership and was removed because it duplicated the stake edge.

Regulators, government bodies and advisers (law firms, banks running a process) never become nodes. They are the two most common false positives in deal coverage, and they appear as the grammatical subject of most approval sentences.

### Testing the extractor

`tests/fixtures/` holds 11 short articles written to plant specific traps: a law firm named in a deal, a denial, an unnamed buyer, an approval that is not a completion, a market roundup that should yield nothing. Each has an expected-output file listing what must and must not be extracted.

On the frozen prompt: **9/11 exact, 10/11 structural** (structural means the right companies and relation, ignoring dates and percentages). One run.

- One failure is a name written as "Japan's Sompo Holdings Inc". Entity resolution strips the possessive downstream, so the graph gets one node.
- The other is a start year that sits in a different sentence from the evidence. This weakness persisted across every prompt version; it produces an incomplete edge, never a false one.

**The model is not deterministic at temperature 0.** The same fixture run three times produced three different outputs. The harness supports multi-run pass rates for this reason, though the figures above are single runs.

### Coverage

110 of 115 articles extracted. The other five failed every attempt because the reasoning model exhausted its output budget before finishing valid JSON. Three of the five are covered by other articles. Two facts were lost: Liberty Mutual raising its stake in Liberty General Insurance, and Bain Capital's interest in IndusInd's insurer. Lowering the model's reasoning effort would probably have recovered them, but would have meant five articles extracted under different settings from the rest. Consistency was kept, and the loss was measured instead: it is the one question vector answered and graph could not.

## Entity resolution

The extractor sees one article at a time, so the same company arrives under many spellings. Bharti Life Insurance appeared as five different strings.

1. **Normalise**: lowercase, strip punctuation, bracketed acronyms, a leading "the", possessives, and legal suffixes.
2. **Alias**: a hand-built map for short forms that normalisation cannot connect. Every entry was confirmed by reading the source articles.
3. **Guard**: a check that warns when an alias points at a key that does not exist in the data. That mistake happened three times before the check existed.

Automatic fuzzy matching was deliberately avoided. "Prudential" and "Prudential plc" are one company; "Aviva" and "Aviva Life Insurance Company India" are a parent and the venture it owns. No string rule separates those cases, and merging the second creates a company that owns itself. The hardest case was a renamed company: "Bharti AXA Life" and "Bharti Life" share no rule-visible link, and were matched only because both were the target of the same 75% stake at the same price.

**222 raw names became 136 nodes.**

## Graph

| | |
|---|---|
| Nodes | 126 |
| Edges | 166, from 333 supporting mentions |
| Edges confirmed by 2+ articles | 65 |

Two triples are the same edge when subject, relation, object, status and stake percentage all match. Six articles about one deal become one edge with six sources. Stake percentage is part of the key so that a 74% holding and a later 100% holding stay separate facts.

The cost of that choice: one holding reported as 22%, 21.91% and "nearly 22%" becomes three edges. Prudential has 8 neighbours but produced 20 edges.

Every edge is indexed from both ends. Ownership points from owner to owned, but a question can start from either side.

## Retrieval and generation

1. **Seeding.** Find which known company names appear in the question, as whole words. When one match sits inside another ("Prudential" inside "ICICI Prudential Life"), the longer one wins.
2. **Traversal.** Breadth-first, two hops, skipping denied relations entirely so the walk never crosses a relationship that does not exist.
3. **Assembly.** Each edge contributes its evidence sentences. **The model never sees a triple**, only the sentences triples came from, so every claim can cite a real article.
4. **Generation.** One call, instructed to use only the passages, cite every claim, flag pending deals, and say exactly "The sources do not say." when they do not. The fixed phrase turns a refusal into something an evaluation can count.

### The assembly bug

The first version took the first 30 passages, edges touching the seed first. On a question about ICICI Bank, 14 of the 30 slots repeated one heavily reported deal, and the sentence stating ICICI Bank's 50.89% stake, two hops away, never reached the model. The answer was correct but weakly supported.

Capping sources per edge was not enough, because of the duplicate edges described above. The working version is round-robin: one passage from every edge before a second from any. Every edge is represented, and the supporting sentence arrived.

It looked at first like the small model was reasoning badly. It was a retrieval problem: the evidence never arrived. Once it did, the same model answered correctly.

**Traversal favours recall over precision.** It reliably reaches the bridge but brings everything within two hops along with it, and leaves precision to the assembly step and the model.

## Vector baseline

- 600-character chunks, with one sentence of overlap so a fact on a boundary lands whole in one chunk.
- `BAAI/bge-small-en-v1.5` embeddings, run locally.
- Cosine similarity as a NumPy dot product over normalised vectors; top 10.
- **The same answer prompt, model and citation format as the graph arm.** Context sizes are comparable. The only difference between the arms is how the context was found.

## Evaluation

### Choosing questions

`src/find_chains.py` lists two-hop chains A, B, C where **no single chunk mentions both A and C**. Chunks are what vector search retrieves, so this is the test that matches what vector can see. Candidates were then sorted by hand: chains built on a mis-extracted edge, on a description rather than a company, or off-domain were dropped.

The set mixes types deliberately. A set made only of the case the graph was designed to win would only show that it wins there.

| Type | Count | Expectation |
|---|---|---|
| Cross-chunk | 4 | Graph should win |
| Same-chunk | 3 | Both should succeed |
| Single-hop | 2 | Both should succeed |
| Extraction gap | 1 | Vector should win |
| Unanswerable | 1 | Neither should invent an answer |

Rules: the bridge company never appears in a question; every gold answer comes from a source sentence, recorded in the question file; type labels are predictions, and were not changed after results came in. One question labelled cross-chunk was answered by vector from a single passage. It keeps its label, and that is reported here rather than corrected.

The unanswerable question is a trap. Star Health appears in an article about speculation that LIC might acquire a health insurer, a plan LIC later shelved. Nobody acquired Star Health, but a passage exists that sounds as if someone might have.

### Scoring

Each answer was scored by hand on two columns:

- **correct**: matches the gold answer, including saying a deal is pending where it is.
- **grounded**: the cited passage actually says what the answer claims. An answer can name the right company while citing a passage about something else; this column catches it.

Judgement calls are recorded in `data/eval_scoring.csv`.

## Limitations

- **Small evaluation.** Eleven questions, one run each. Output varies between runs even at temperature 0.
- **One domain, 115 articles.** Results say nothing about other corpora.
- **5 articles not extracted**, losing two facts not covered elsewhere.
- **Asset and portfolio purchases produce no edge.** The schema models equity only.
- **Stock exchanges are excluded.** Their shareholder lists are true but would create a large hub outside the domain.
- **Article bodies are truncated at 6,000 characters** to fit the provider's per-minute token limit. This mostly affects long roundups.
- **A year stated in a different sentence from the evidence is often missed**, giving incomplete edges.
- **Duplicate edges for one holding** reported at slightly different percentages inflate the context.
- **Generic names seed wrongly.** "Life Insurance Corporation (LIC)" normalises to "life insurance" and matches ordinary words in questions. It changed no result but adds noise.
- **Some extraction errors remain in the graph**, including two executives attached to Prudential plc rather than the Prudential Health venture they joined.
- **The chunk test only knows spellings the extractor produced.** An article writing "PNB" is invisible to it if the graph only knows "Punjab National Bank".
- **The possessive rule can leave a description** ("Bajaj's insurance ventures") where it was meant to leave a company name. Known cases are blocked or aliased.
- **Scraping artefacts**: some characters were mis-decoded at fetch time.
- **Free-tier inference**: a 200,000 token daily limit set the pace of extraction and the size of the evaluation.

## Running it

Python 3.13. One key is needed, from [Groq](https://console.groq.com):

```
GROQ_API_KEY=...
```

```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

The provider is set in one place, `PROVIDER` in `src/extract.py`, which also drives answering. A local model via Ollama is supported for testing, but extraction quality drops sharply with a 7B model.

Each stage reads the previous stage's files, so run them in order. Every step caches or resumes, so reruns are cheap.

```
python src/collect.py
python src/run_extraction.py      # stops on the daily limit; rerun to resume
python src/resolve.py
python src/graph.py
python src/vector_rag.py          # builds the vector index
python src/find_chains.py
python src/run_eval.py            # resumable; then score data/eval_scoring.csv
python src/run_eval.py summarize
```

After changing anything in `src/resolve.py`, rerun it, then `graph.py`. Editing the file changes nothing until it runs and rewrites `data/nodes.json`.

To ask a single question three ways:

```
python src/compare.py "Which bank holds a stake in the life insurer that Prudential part-owns?"
```

## Repository layout

```
src/                     pipeline code, one file per stage
docs/extraction_prompt.md  the frozen extraction specification
docs/scope.md            decisions about what the graph does and does not model
tests/fixtures/          11 extraction test articles with expected outputs
data/eval_questions.json the evaluation questions and gold answers
data/eval_results.json   every answer, with the passages each arm received
data/eval_scoring.csv    hand scores and judgement calls
```

## What I would do next

- **More questions, several runs each.** The single biggest weakness of the result.
- **Rank traversed edges against the question** before assembly, instead of including the whole two-hop neighbourhood.
- **Fix seeding on generic names**, by ignoring keys made only of common sector words.
- **Recover the five failed articles** in a separate, labelled extraction pass, keeping them distinguishable from the main corpus.
