# Biomedical Corrective RAG Agent

A question-answering agent over PubMed research on coping strategies for depression, anxiety, and stress (CBT, mindfulness-based interventions, behavioral activation). Unlike a standard retrieve-then-generate pipeline, it grades its own retrieval for relevance and checks its own answers against their sources before responding, looping back to retry when either check fails. Answers are written for a general reader rather than a specialist, cite numbered sources, and are drawn from full article text — not just abstracts — where the paper is openly available. A keyword-based safety guardrail screens every question before retrieval runs at all, routing anything crisis-adjacent to real crisis resources instead of a generated answer.

This is a research-synthesis tool, not a clinical one. Every response carries a disclaimer that it is not medical advice.

## Live demo

- **App:** https://pubmed-corrective-rag-agent.vercel.app
- **API docs (Swagger UI):** https://pubmed-corrective-rag-agent.onrender.com/docs
- **Screen recording:** _(placeholder — recording of the live reasoning trace to be added here)_

The backend runs on Render's free tier, which spins down after ~15 minutes of no traffic. The first request after idle can take 30–50 seconds to cold-start. That's infrastructure, not the agent.

## Architecture

```
[safety guardrail] -> retrieve -> grade_documents ->
  [generate | transform_query loop] ->
  generate -> simplify -> check_groundedness ->
  [END | generate loop | transform_query loop]
```

- **safety guardrail** (`agent/guardrail.py`) — runs before retrieval touches the vector store. Crisis/self-harm language routes straight to `END` with fixed crisis-line contacts (988, Crisis Text Line, findahelpline.com). Pre-retrieval routing, not a post-hoc filter: a flagged question never reaches an LLM.
- **retrieve** — fetches 40 candidates from Pinecone, then keeps at most 2 chunks per source paper and takes the top 12. The cap matters because full-text papers produce ~37 chunks against ~1.7 for abstract-only ones, so without it a single well-matched paper would crowd out every other source.
- **grade_documents** — an LLM (`gpt-4o-mini`) grades each retrieved chunk for relevance, concurrently. Irrelevant chunks are dropped.
- **transform_query** — if nothing survived grading, rewrites the search query and loops back. Capped at 2 retries, shared across both correction loops.
- **generate** — synthesizes a cited but still technical answer (`gpt-4o`) from the surviving chunks.
- **simplify** — rewrites that draft into plain language, preserving the `[1]`-style citation markers. Runs *before* verification, so the text that gets checked is the text the reader actually sees.
- **check_groundedness** — verifies every claim traces back to the retrieved chunks, and separately that the answer addresses the question. Routes to `END`, back to `generate`, or back to `transform_query`.

Citation numbers are assigned once in `agent/citations.py` and shared by both the generation prompt and the API response, so `[1]` in the answer and the first entry in the source list always refer to the same paper — the model never invents its own numbering. Sources that the answer doesn't actually cite are filtered out of the response.

## The corpus

| | |
|---|---|
| Papers | 1,868 |
| With PMC full text | 505 (27%) |
| Indexed chunks | 20,854 |

Full text is the reason this version answers questions the previous one couldn't. A PubMed abstract averages ~1,500 characters; the full article averages ~38,500 — roughly 26× more text, including methods, sample sizes, effect sizes, and limitations. Ask "what sample sizes and dropout rates are typical in CBT caregiver trials?" and the retrieved chunks are actual `Sample size` and `Recruitment and Attrition` sections, which an abstract-only corpus simply does not contain.

Only 27% of the corpus clears both gates (the paper has a PMCID *and* PMC serves a body for it), so most records remain abstract-only. Ingestion drops references, funding, and acknowledgements by construction, filters out non-English full text (PubMed indexes translated titles but PMC serves the original language), and normalizes section headings so `4. DISCUSSION` and `Discussion` don't become separate embedding signals.

## Why corrective, not plain RAG

Plain retrieve-then-generate has no mechanism to catch its own failures. Three specific ones this design addresses:

- **Irrelevant retrieval reaching the generator unfiltered.** `grade_documents` filters weak matches before generation; `transform_query` gives retrieval a second attempt rather than generating from bad context.
- **Ungrounded claims even when retrieval succeeds.** `check_groundedness` catches these after the fact and triggers a regeneration rather than shipping them.
- **A research summary as the response to a crisis.** Not a retrieval or generation failure — the wrong *kind* of response entirely. Plain RAG has no concept of "this question shouldn't enter the pipeline."

## Eval results

`eval/run_eval.py` runs a fixed 15-question set (9 straightforward, 5 deliberately ambiguous or off-corpus, 1 crisis-adjacent) through two graphs, producing three comparable arms:

- **Linear** — `retrieve -> generate`, no grading, retries, guardrail, or rewrite (`agent/linear_graph.py`)
- **Corrective (draft)** — the corrective loop's technical synthesis
- **Corrective (final)** — the same run after `simplify`

The last two come from a single run, so a shared question, context, and draft separate them by exactly one rewrite — which is what makes the plain-language step measurable in isolation.

| Metric | Linear | Corrective (draft) | Corrective (final) |
|---|---|---|---|
| Faithfulness | 0.98 (n=14) | 1.00 (n=12) | 0.95 (n=12) |
| Answer relevancy | 0.71 (n=14) | 0.71 (n=14) | 0.78 (n=14) |
| Context precision | 0.55 (n=14) | _shared_ | **0.71** (n=12) |
| Flesch-Kincaid grade | 17.85 | 16.81 | **13.10** |
| Flesch reading ease | 8.88 | 13.12 | **36.20** |
| Avg. retries | — | — | 1.29 |
| Avg. latency | — | — | 14.4s |

**What holds up, and what doesn't.** Running this eval five times exposed that the metrics differ a lot in stability. Context precision barely moves between runs (final: 0.71, 0.73, 0.74, 0.71, 0.71). Faithfulness and answer relevancy do not: the *linear* arm's relevancy — which never changed — came in at 0.82, 0.78, 0.81, 0.70, and 0.71 across those runs. That 0.12 swing is larger than most of the differences between arms.

So, stated honestly:

- **Readability improved substantially and reliably.** ~4.8 grade levels easier than plain RAG (17.85 → 13.10), of which the draft→final comparison attributes ~3.7 to the simplify step specifically. Reading ease roughly 4×.
- **Context precision improved substantially and reliably** — 0.55 → 0.71, a ~29% gain. This is the metric `grade_documents` exists to move, and it moves.
- **Faithfulness and answer relevancy are roughly comparable across all three arms.** With n=14 and this much run-to-run variance, the small differences are not evidence of anything. Reporting them as precise deltas would be overclaiming.

**Prose costs a little measured readability, and is worth it.** Answers used to come back as numbered lists. Rendered in the UI that put list ordinals ("1.", "2.") directly beside the `[1]` citation markers, where they stop matching after the first couple of items — item 3 citing `[4]` — which made the citations hard to follow. Constraining generation to prose fixed that and cost ~1 grade level (final Flesch-Kincaid 12.08 → 13.10, reading ease 39.32 → 36.20): list items are short fragments, and both metrics key heavily on sentence length. All three arms shifted, since they share the `generate` node (linear +0.47, draft +0.76, final +1.02 grades), so the gain over plain RAG narrowed only slightly — 5.3 grades to 4.8.

`n` is how many questions a metric could be scored on. RAGAS cannot score faithfulness or context precision against zero retrieved chunks, which the corrective graph legitimately produces when it correctly declines an off-corpus question.

**A note on how RAGAS scores refusals.** Answer relevancy returns exactly 0.00 when it judges an answer noncommittal — there is no partial credit, so a single hedged answer moves the mean by ~0.07. Three questions hit it in this run: the two off-corpus ones (where "the sources don't contain this" is the correct answer), and "Does a CBT-based mobile intervention help reduce nurse burnout?", which the literature genuinely answers as *yes, but the effects are modest and variable*. Faithful reporting of a weak finding reads as noncommittal to the metric.

*Which* questions trip it shifts between runs — an earlier run zeroed "What's the best way to cope with stress?" instead, and scored the nurse-burnout question 0.99. So the 0.00s are better read as a property of the metric than as a ranking of the answers. In each case it penalises behavior the system was deliberately built to have.

**Safety guardrail check.** On the crisis-adjacent question, the corrective graph bypassed the pipeline entirely, as designed. The linear graph has no guardrail node, so the same question went straight through retrieval and generation.

Full per-question breakdown: `eval/results.md`. Raw scores and answers: `eval/results_raw.json`.

## A deliberate tradeoff: plain-language glosses

The simplify step is instructed to explain technical terms on first use. In practice that produces sentences like:

> "Cognitive-behavioral therapy is a type of talk therapy that helps people change negative thought patterns and behaviors."

That statement is true and useful to a lay reader — and it is **not in the retrieved sources**, because papers rarely define their own field's vocabulary. The groundedness grader correctly flags it as unsupported, which measurably lowers faithfulness on questions where a gloss appears. In the published run, the two questions carrying a CBT gloss both fell from 1.00 on the draft to 0.77 on the final answer (Q6 and Q9 in `eval/results_raw.json`), and they are the only two of the fourteen that carry one.

This is a deliberate product decision, not an unnoticed defect. A plain-language research tool that cannot explain "cognitive behavioral therapy" to the audience it's written for has failed at its actual job. The alternative — restricting explanations to wording present in the sources — scores better and reads worse, drifting back toward the specialist register this version exists to get away from.

Worth knowing when reading the faithfulness numbers above: some of that gap is bought on purpose.

## Safety design

Before any question reaches retrieval, `agent/guardrail.py` screens it against regex patterns for crisis and self-harm language. A match routes straight to a fixed response with real crisis resources — 988 (Suicide & Crisis Lifeline, US), Crisis Text Line, and findahelpline.com — bypassing retrieval and generation entirely.

**This is a simple keyword and regex match, not a clinical-grade classifier and not an LLM call.** It will miss phrasing it doesn't recognize — typos, indirect language, non-English input — and may occasionally trigger on unrelated text. It exists to reliably catch the cases it does catch, on the premise that generating a research summary is never an appropriate response to a crisis. It is not a dependable crisis-detection system, and **this project should not be relied on for real crisis intervention.** If you or someone you know is in crisis, in the US call or text 988, or see https://findahelpline.com for international resources.

Separately, every non-crisis response carries a fixed disclaimer that it is a summary of published research for informational purposes only. The disclaimer is appended in code, not left to the model, so it is present by construction.

## Tech stack

- **Python 3.11+**, FastAPI for the serving layer (SSE streaming)
- **LangGraph** for the agent state machine (`StateGraph`, conditional edges)
- **LangChain** for LLM/embedding integrations
- **Pinecone** (serverless) for the vector index
- **PubMed E-utilities + PubMed Central** for ingestion (abstracts and JATS full text)
- **RAGAS** + **textstat** for offline evaluation
- **React (Vite) + Tailwind**, deployed on Vercel
- **Docker + docker-compose** for local orchestration; deployed on Render
- **pytest** + **ruff** in GitHub Actions on every push

Models: `gpt-4o` for generation and simplification, `gpt-4o-mini` for the relevance/groundedness/answer graders, `text-embedding-3-small` for embeddings.

The index lives in Pinecone rather than the repo because it outgrew it: 20,854 chunks came to ~315 MB on disk, of which the Chroma SQLite file alone was ~187 MB — past GitHub's 100 MB per-file limit, and not closable by shrinking chunks or truncating embeddings without degrading retrieval on both axes at once.

## Local setup

```bash
git clone <this-repo-url>
cd corrective-rag-agent
cp .env.example .env   # fill in OPENAI_API_KEY and PINECONE_API_KEY
```

`NCBI_API_KEY` is optional but recommended if you plan to re-ingest — it raises NCBI's rate limit from 3 to 10 requests/second, and full-text ingestion makes ~560 additional calls.

### Backend

```bash
pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

Or with Docker:

```bash
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

### Building the index

The app expects a populated Pinecone index. To build one from scratch:

```bash
python -m data_pipeline.ingest       # PubMed + PMC full text -> data/raw/pubmed_corpus.json
python -m data_pipeline.build_index  # chunk, embed, upsert to Pinecone
```

Ingestion takes ~10 minutes (rate-limited by NCBI); embedding ~21k chunks costs roughly $0.10. `build_index.py` accepts `--chunk-size` and `--dimensions` if you want to trade retrieval quality against index size.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE defaults to http://127.0.0.1:8000
npm run dev
```

### Tests and linting

```bash
pip install -r requirements-dev.txt
ruff check .
pytest tests/ -v
```

The smoke test mocks every LLM, embedding, and vector-store call, so CI needs no API keys and no network.

## What I'd improve next

- **A larger eval set.** The variance analysis above is the clearest argument for this: at n=14, run-to-run noise on the LLM-judged metrics is as large as the effects being measured. Fifty to a hundred questions with stratified sampling would let faithfulness and relevancy differences mean something, and would turn the eval into a regression gate rather than a snapshot.
- **More robust crisis detection.** The regex guardrail is fast and auditable but structurally limited to phrasing it already knows. A production version would keep it as a zero-latency first pass and add an LLM classifier behind it for indirect or non-English phrasing — not a replacement, since the regex layer's predictability is itself the point.
- **Broader corpus coverage.** The current MeSH query caps out at ~1,986 papers, and only 27% of those have retrievable full text. Widening the query, or adding Europe PMC and OpenAlex to reach psychology journals MEDLINE doesn't index, would deepen coverage — at the cost of cross-source deduplication work.
- **Cost and latency.** A turn makes roughly 15 LLM calls (12 concurrent relevance grades, generation, simplification, groundedness) and takes ~17 seconds. Semantic caching for near-duplicate questions, and a cheaper model for the simplify pass, are the obvious levers — the latter would need measuring, since simplification drift is what the groundedness check has to catch.
