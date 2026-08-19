# Project: Biomedical Corrective RAG Agent

## Goal
An agentic RAG system over PubMed abstracts that self-corrects when retrieval
is weak or generation is ungrounded, built as a portfolio project demonstrating
LangGraph state machines with conditional loops.

## Domain
Corpus: PubMed abstracts on psychological coping strategies for depression,
anxiety, and stress — specifically CBT, mindfulness-based interventions,
and behavioral activation. This is an informational/research synthesis tool,
not a clinical tool. Every response should carry a disclaimer that it's not
medical advice.

## Stack
- Python 3.11+, FastAPI for the serving layer (SSE streaming enabled)
- LangGraph for the agent state machine (StateGraph, conditional edges)
- LangChain for LLM/embedding integrations
- Chroma for the vector store (local, Docker-friendly)
- PubMed E-utilities API for data ingestion
- RAGAS for offline evaluation
- React (Vite) + Tailwind for the frontend, deployed on Vercel
- Docker + docker-compose for backend deployment
- pytest for tests

## Architecture (see docs/architecture.md once written)
[safety guardrail] -> retrieve -> grade_documents ->
  [generate | transform_query loop] -> generate -> check_groundedness ->
  [END | generate loop | transform_query loop]

State schema: question, original_question, documents, generation,
retry_count, grounded

## Safety guardrail
Before the retrieve node, a lightweight check screens the incoming question
for signs of acute distress or crisis (self-harm, suicidal ideation, and
similar). If flagged, bypass the RAG pipeline entirely and return a fixed
response pointing to real crisis resources (e.g. 988 Suicide & Crisis
Lifeline in the US) instead of generating from the literature. This is a
simple keyword/pattern check for this portfolio project, not a clinical-
grade system — note this limitation explicitly in the README.

## Current phase
Data pipeline, corrective graph, FastAPI backend (with SSE streaming), 
and the React + Tailwind frontend are all complete — chat interface, 
live reasoning trace, clickable citations, disclaimer banner, retry 
badges, and a deliberate visual design pass (not default Tailwind), 
responsive down to mobile. Frontend consumes /query/stream successfully 
end to end.

Remaining work to ship this as a full portfolio project:
1. RAGAS eval comparing linear vs. corrective graph performance 
   (faithfulness, answer relevancy, context precision) on a ~15-question 
   eval set
2. Docker + docker-compose for the backend (FastAPI + persisted Chroma 
   volume)
3. Deploy: backend to Render/Fly.io, frontend to Vercel
4. GitHub Actions CI: lint + a smoke test hitting the compiled graph
5. README: architecture diagram, eval numbers table, demo 
   screen-recording of the reasoning trace in action, setup instructions

## Decisions log
- Embedding model: [fill in]
- Chunk strategy: one Document per abstract, page_content = title + 
  abstract, metadata = {pmid, title, journal, year}
- PubMed query: (
    '("Adaptation, Psychological"[MeSH] OR "coping"[tiab]) '
    'AND ("Depression"[MeSH] OR "Anxiety"[MeSH] OR "stress, psychological"[MeSH]) '
    'AND ("Cognitive Behavioral Therapy"[MeSH] OR "Mindfulness"[MeSH] OR "self-care"[tiab])'
)
- Retry limit: 2 retries max before fallback response
- FastAPI response shape: {answer, citations, disclaimer, retries_used}
- Streaming: SSE, events per LangGraph node transition
- Frontend: React + Vite + Tailwind, deployed on Vercel

## Conventions
- Type hints everywhere
- Small, single-purpose functions (these become graph nodes later)
- .env for API keys, never hardcoded
- Keep PMID, title, journal, year as metadata on every chunk — needed for
  citations later
- Write a short docstring on every function explaining what it does and why