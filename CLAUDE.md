# Project: Biomedical Corrective RAG Agent

## Goal
An agentic RAG system over PubMed abstracts that self-corrects when retrieval
is weak or generation is ungrounded, built as a portfolio project demonstrating
LangGraph state machines with conditional loops.

## Domain
Corpus: PubMed abstracts plus PubMed Central full text (where openly
available) on psychological coping strategies for depression, anxiety, and
stress — specifically CBT, mindfulness-based interventions, and behavioral
activation. 1,868 papers, 505 (27%) with full text, 20,854 indexed chunks. This is an informational/research synthesis tool,
not a clinical tool. Every response should carry a disclaimer that it's not
medical advice.

## Stack
- Python 3.11+, FastAPI for the serving layer (SSE streaming enabled)
- LangGraph for the agent state machine (StateGraph, conditional edges)
- LangChain for LLM/embedding integrations
- Pinecone (serverless) for the vector store; the index is ~315MB, too large for the repo
- PubMed E-utilities + PubMed Central (JATS full text) for data ingestion
- RAGAS + textstat (readability) for offline evaluation
- React (Vite) + Tailwind for the frontend, deployed on Vercel
- Docker + docker-compose for backend deployment
- pytest for tests

## Architecture (see docs/architecture.md once written)
[safety guardrail] -> retrieve -> grade_documents ->
  [generate | transform_query loop] ->
  generate -> simplify -> check_groundedness ->
  [END | generate loop | transform_query loop]

retrieve over-fetches 40 candidates, caps at 2 chunks per paper, keeps top 12.
generate produces a technical draft; simplify rewrites it for a general reader
before check_groundedness verifies the text the reader actually sees.

State schema: question, original_question, documents, draft_generation,
generation, retry_count, grounded, crisis_detected

## Safety guardrail
Before the retrieve node, a lightweight check screens the incoming question
for signs of acute distress or crisis (self-harm, suicidal ideation, and
similar). If flagged, bypass the RAG pipeline entirely and return a fixed
response pointing to real crisis resources (e.g. 988 Suicide & Crisis
Lifeline in the US) instead of generating from the literature. This is a
simple keyword/pattern check for this portfolio project, not a clinical-
grade system — note this limitation explicitly in the README.

## Current phase
v2 shipped through Phase 5: PMC full-text ingestion, Pinecone migration,
per-paper retrieval caps with concurrent grading, two-stage plain-language
answers with numbered citations, and a three-arm eval with readability metrics.

Known open items:
1. Frontend pass - [1] markers render as plain text, not links to the source list
2. Eval set is n=14; run-to-run variance on LLM-judged metrics is as large as
   the effects being measured (see README)
3. Corpus capped at ~1,986 papers by the MeSH query; 27% full-text coverage

## Decisions log
- Embedding model: text-embedding-3-small (1536 dims; `dimensions` is
  configurable for Matryoshka truncation if index size ever matters)
- Chunk strategy: section-aware, 1200 chars / 150 overlap. Abstract is always
  its own chunk; full-text sections are split separately and prefixed with
  their section label. metadata = {pmid, title, journal, year, section,
  has_full_text, chunk_index}
- Section filtering: denylist (drop Introduction/Background/ethics/funding/
  acknowledgements/references), not an allowlist - real section titles vary
  far more than IMRaD
- PubMed query: (
    '("Adaptation, Psychological"[MeSH] OR "coping"[tiab]) '
    'AND ("Depression"[MeSH] OR "Anxiety"[MeSH] OR "stress, psychological"[MeSH]) '
    'AND ("Cognitive Behavioral Therapy"[MeSH] OR "Mindfulness"[MeSH] OR "self-care"[tiab])'
)
- Retry limit: 2 retries max before fallback response
- FastAPI response shape: {answer, citations, disclaimer, retries_used};
  citations carry number + url, filtered to those the answer actually cites
- Streaming: SSE, events per LangGraph node transition
- Plain-language glosses are kept even though they lower measured
  faithfulness - deliberate product decision, documented in the README
- Frontend: React + Vite + Tailwind, deployed on Vercel

## Conventions
- Type hints everywhere
- Small, single-purpose functions (these become graph nodes later)
- .env for API keys, never hardcoded
- Keep PMID, title, journal, year as metadata on every chunk — needed for
  citations later
- Write a short docstring on every function explaining what it does and why