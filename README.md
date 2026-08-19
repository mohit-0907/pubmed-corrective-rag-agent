# Biomedical Corrective RAG Agent

An agentic RAG system over PubMed abstracts on psychological coping strategies
(CBT, mindfulness-based interventions, behavioral activation) for depression,
anxiety, and stress. Built with LangGraph: retrieval is graded for relevance,
generation is checked for groundedness, and both loop back to self-correct
before answering.

This is an informational/research-synthesis tool, not a clinical tool.
Every response carries a disclaimer that it is not medical advice.

## Architecture

```
[safety guardrail] -> retrieve -> grade_documents ->
  [generate | transform_query loop] -> generate -> check_groundedness ->
  [END | generate loop | transform_query loop]
```

- **safety guardrail**: screens the incoming question for crisis language
  before retrieval runs at all. See Safety limitations below.
- **grade_documents**: an LLM grades each retrieved chunk for relevance to
  the question; irrelevant chunks are dropped.
- **transform_query**: if nothing relevant was retrieved, rewrites the
  question for better retrieval and tries again (capped retries).
- **check_groundedness**: an LLM checks whether the generated answer is
  actually supported by the retrieved abstracts (catches hallucination) and
  whether it addresses the original question.

## Safety guardrail limitations

The guardrail that screens for acute distress / suicidal ideation / self-harm
language (`agent/guardrail.py`) is a **simple keyword and regex pattern
match**, not a clinical-grade classifier and not an LLM call. It will miss
phrasing it doesn't recognize (typos, indirect language, non-English input)
and may occasionally trigger on unrelated text that happens to match a
pattern. It exists to reliably bypass the RAG pipeline for the cases it does
catch - generating a research-literature summary is never an appropriate
response to a crisis - not to serve as a dependable crisis-detection system.
**Do not rely on this project for real crisis intervention.** If you or
someone you know is in crisis, in the US call or text 988 (Suicide & Crisis
Lifeline), or see https://findahelpline.com for international resources.

## Setup

```
pip install -r requirements.txt
cp .env.example .env  # fill in OPENAI_API_KEY (and optionally NCBI_API_KEY)
```

Data pipeline (run once to build the corpus and vector index):

```
python -m data_pipeline.ingest       # fetch abstracts from PubMed -> data/raw/
python -m data_pipeline.build_index  # chunk + embed -> chroma_db/
```

Run the agent:

```
python -m agent.run_agent
```
