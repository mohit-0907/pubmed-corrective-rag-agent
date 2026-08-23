# Biomedical Corrective RAG Agent

A retrieval-augmented question-answering agent over PubMed research literature on coping strategies for depression, anxiety, and stress (CBT, mindfulness-based interventions, behavioral activation). Unlike a standard retrieve-then-generate pipeline, it grades its own retrieval for relevance and checks its own answers for groundedness before responding, looping back to retry retrieval or regenerate when either check fails. A keyword-based safety guardrail screens every question before retrieval runs at all, and routes anything crisis-adjacent to real crisis resources instead of a generated answer. Built with LangGraph, a FastAPI backend with SSE streaming, and a React frontend that visualizes the agent's reasoning live, turn by turn.

This is a research-synthesis tool, not a clinical one. Every response carries a disclaimer that it is not medical advice.

## Live demo

- **App:** https://pubmed-corrective-rag-agent.vercel.app
- **API docs (Swagger UI):** https://pubmed-corrective-rag-agent.onrender.com/docs
- **Screen recording:** _(placeholder — recording of the live reasoning trace to be added here)_

The backend runs on Render's free tier, which spins down after ~15 minutes of no traffic. The first request after a period of inactivity can take 30–50 seconds to respond while the process cold-starts and loads the vector index — that's infrastructure, not a bug in the agent itself.

## Architecture

```
[safety guardrail] -> retrieve -> grade_documents ->
  [generate | transform_query loop] -> generate -> check_groundedness ->
  [END | generate loop | transform_query loop]
```

- **safety guardrail** (`agent/guardrail.py`) — runs first, before retrieval ever touches the vector store. Screens the raw question for crisis/self-harm language; if flagged, the graph routes straight to `END` with a fixed response containing real crisis-line contacts (988, Crisis Text Line, findahelpline.com). This is pre-retrieval routing, not a post-hoc content filter — a flagged question never reaches the LLM at all.
- **retrieve** — top-5 similarity search against a Chroma vector store of embedded PubMed abstract chunks.
- **grade_documents** — an LLM (`gpt-4o-mini`) grades each retrieved chunk individually for relevance to the original question; irrelevant chunks are dropped.
- **transform_query** — if nothing relevant survived grading, rewrites the search query and loops back to `retrieve`. Capped at 2 retries total, shared across both correction loops (see Eval results for what that costs).
- **generate** — synthesizes a cited answer (`gpt-4o`) from whatever chunks passed grading.
- **check_groundedness** — a second LLM pass checks whether every claim in the answer is actually supported by the retrieved chunks (catches hallucination), and separately whether the answer addresses the original question at all (catches faithful-but-evasive answers). Routes to `END`, back to `generate` for a fresh attempt, or back to `transform_query` if the underlying problem looks like weak retrieval rather than weak generation.

State carried through the graph: `question`, `original_question`, `documents`, `generation`, `retry_count`, `grounded`, `crisis_detected`.

## Why corrective, not plain RAG

A plain retrieve-then-generate pipeline has no mechanism to catch its own failures — it hands the generator whatever it retrieved and trusts whatever the generator produces. Three specific failure modes this design catches instead:

- **Irrelevant retrieval reaching the generator unfiltered.** Plain RAG has no relevance check between retrieval and generation — if the top-k similarity search returns weak matches (common on broad or off-corpus questions), the generator still has to work with them. `grade_documents` filters these out before they reach generation; `transform_query` gives retrieval a second attempt with a rewritten query instead of generating from bad context.
- **Hallucinated or ungrounded claims, even when retrieval succeeds.** A model can still assert something not actually supported by its context. `check_groundedness` catches this after the fact and triggers a regeneration attempt rather than shipping the ungrounded answer as-is.
- **A generated research summary as the response to a crisis.** This isn't a retrieval or generation failure in the usual sense — it's the wrong kind of response entirely, regardless of how good the retrieval or generation would have been. The safety guardrail exists specifically because plain RAG has no concept of "this question shouldn't go through the pipeline at all."

## Eval results

`eval/run_eval.py` runs a fixed 15-question set (9 straightforward, 5 deliberately ambiguous or off-corpus, 1 crisis-adjacent) through both this corrective graph and a reconstructed linear baseline (`agent/linear_graph.py` — plain `retrieve -> generate`, no grading, no guardrail; this is what the graph looked like before the correction loop existed). Each non-crisis answer is scored with RAGAS.

| Metric | Linear (baseline) | Corrective |
|---|---|---|
| Faithfulness | 0.838 (n=13) | 0.767 (n=11) |
| Answer Relevancy | 0.683 (n=14) | 0.689 (n=14) |
| Context Precision | 0.638 (n=14) | 0.818 (n=12) |
| Avg. retries used | — | 1.60 |

_n = number of the 14 non-crisis questions each metric could actually be scored on. RAGAS can't compute context precision or faithfulness against zero retrieved chunks, which the corrective graph legitimately produces after exhausting retries on an off-corpus question and correctly declining to answer — those cases are excluded from the average rather than scored as failures._

**Guardrail check (the crisis-adjacent question):** the corrective graph bypassed the RAG pipeline entirely, as designed. The linear graph has no guardrail node, so the same question was sent straight through retrieval and generation like any other input.

**Reading the numbers honestly, not as a clean sweep:**

- **Context precision is the clear win** (0.818 vs. 0.638) — this is exactly the metric `grade_documents` is built to move, and it moved.
- **Faithfulness looks worse for corrective at face value, which is misleading.** On the two fully off-corpus questions, corrective ended with zero retrieved chunks and got excluded from the average — the correct behavior, not a failure. Linear always keeps whatever five chunks it found regardless of relevance and trivially scores "faithful" hedging around them. On two other questions, corrective's faithfulness genuinely was lower despite more retries — regenerating from the same weak context doesn't always fix an ungrounded claim.
- **Answer relevancy is essentially a wash** (0.689 vs. 0.683) — expected, since `generate` is the same function in both graphs; this metric mostly reflects that shared step.

**The cost this buys:** even on a clean pass with zero retries, the corrective graph makes roughly 7–8 LLM calls per query — up to 5 individual relevance grades (one per retrieved chunk), 1 generation call, and 1–2 groundedness checks — against 1 generation call for the linear baseline. Average retries used was 1.60, meaning a meaningful share of queries triggered a full additional retrieval-or-generation cycle on top of that. In practice, a full corrective turn observed end-to-end took 20–30+ seconds, almost entirely from the sequential per-chunk grading calls. This is a real latency and cost tradeoff, not a free improvement — see "What I'd improve next" for how a production version would address it.

Full per-question breakdown: `eval/results.md`.

## Safety design

Before any question reaches retrieval, `agent/guardrail.py` screens it against a set of regex patterns for crisis and self-harm language (suicidal ideation, self-harm references, and similar). A match routes the graph straight to a fixed response with real crisis resources — 988 (Suicide & Crisis Lifeline, US), Crisis Text Line, and findahelpline.com for international contacts — bypassing retrieval and generation entirely.

**This is a simple keyword and regex pattern match, not a clinical-grade classifier and not an LLM call.** It will miss phrasing it doesn't recognize — typos, indirect language, non-English input — and may occasionally trigger on unrelated text that happens to match a pattern. It exists to reliably catch the cases it does catch, on the premise that generating a research-literature summary is never an appropriate response to a crisis. It is not a dependable, comprehensive crisis-detection system, and **this project should not be relied on for real crisis intervention.** If you or someone you know is in crisis, in the US call or text 988, or see https://findahelpline.com for international resources.

Separately from the guardrail, every non-crisis response — regardless of how it was generated — carries a fixed disclaimer that it is a summary of published research literature for informational purposes only, not medical advice, and not a substitute for care from a qualified healthcare provider. This disclaimer is appended in code, not left to the model's discretion, so it's present on every response by construction.

## Tech stack

- **Python 3.11+**, FastAPI for the serving layer (SSE streaming enabled)
- **LangGraph** for the agent state machine (`StateGraph`, conditional edges)
- **LangChain** for LLM/embedding integrations
- **Chroma** for the vector store (local, Docker-friendly, index committed to the repo)
- **PubMed E-utilities API** for data ingestion
- **RAGAS** for offline evaluation
- **React (Vite) + Tailwind**, deployed on Vercel
- **Docker + docker-compose** for local backend orchestration; deployed on Render
- **pytest** for CI (mocked smoke test) + GitHub Actions (ruff + pytest on every push)

Models in use: `gpt-4o` for generation, `gpt-4o-mini` for the relevance/groundedness/answer graders, `text-embedding-3-small` for embeddings.

## Local setup

```bash
git clone <this-repo-url>
cd corrective-rag-agent
cp .env.example .env   # fill in OPENAI_API_KEY (required); NCBI_API_KEY is optional
```

### Fastest path: Docker, using the pre-built index

The Chroma index (`chroma_db/`) is already built and committed to this repo, so no data pipeline run is required to get a working agent locally:

```bash
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

### Running the backend directly (no Docker)

```bash
pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

### Rebuilding the corpus from scratch (optional)

Only needed if you want to refresh or expand the corpus rather than use the committed index:

```bash
python -m data_pipeline.ingest       # fetch abstracts from PubMed -> data/raw/
python -m data_pipeline.build_index  # chunk + embed -> chroma_db/
```

### Frontend dev server

The backend must already be running (either path above) on `localhost:8000`:

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE defaults to http://127.0.0.1:8000 if unset
npm run dev
```

### Tests and linting

```bash
pip install -r requirements-dev.txt
ruff check .
pytest tests/ -v
```

## What I'd improve next

- **More robust crisis detection.** The regex guardrail is fast and auditable but structurally limited to phrasing it already knows about. A production version would keep the regex layer as a zero-latency first pass but add a second, LLM-based classifier behind it as a fallback for borderline or indirectly-phrased cases — not a replacement, since the regex layer's speed and predictability are themselves valuable.
- **Broader corpus and better retrieval.** The corpus is deliberately narrow (coping strategies specifically, ~1,855 abstracts). A larger corpus would need hybrid retrieval (keyword + semantic, since pure embedding search misses exact-term matches like drug or instrument names) and deduplication by PMID at the retrieval step itself — right now the same abstract can occupy two of five retrieval slots if it was chunked into pieces that both rank highly, which the frontend hides by deduping for display but the graph itself doesn't correct.
- **Semantic caching for cost.** The corrective loop's 7–8 LLM calls per query (more with retries) is the real cost of the accuracy gains shown above. A production deployment fielding repeated or similar questions would benefit from caching grader/embedding results for near-duplicate queries, and from parallelizing the currently-sequential per-chunk grading calls in `grade_documents` rather than grading one chunk at a time.

The eval itself is also worth being honest about: 15 questions run once is enough to demonstrate the measurement methodology, not enough for a statistically rigorous claim. A production version would need a larger, stratified eval set and would track results over time rather than as a single snapshot, to catch regressions before they ship.
