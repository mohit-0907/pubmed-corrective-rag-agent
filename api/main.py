"""FastAPI serving layer over the corrective RAG graph.

The graph is built once at startup (lifespan), not per-request - node-level
resources (vector store, LLM clients) are themselves cached lazily, see
agent/nodes.py, so a fresh build_graph() call here is cheap and just wires
already-cached pieces together.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agent.graph import build_graph
from api.schemas import QueryRequest, QueryResponse, Source
from api.streaming import stream_graph_events

# Vite's default dev server port. This is a local portfolio project, not a
# deployed multi-origin service, so a small fixed allowlist is enough -
# revisit if a deployed frontend origin needs adding later.
DEV_FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173","https://pubmed-corrective-rag-agent.vercel.app/"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    app.state.graph = build_graph()
    yield


app = FastAPI(title="Corrective RAG Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    result = app.state.graph.invoke(
        {
            "question": request.question,
            "original_question": request.question,
            "retry_count": 0,
        }
    )

    sources = [
        Source(
            pmid=doc.metadata["pmid"],
            title=doc.metadata["title"],
            journal=doc.metadata["journal"],
            year=doc.metadata["year"],
        )
        for doc in result.get("documents", [])
    ]

    return QueryResponse(
        answer=result["generation"],
        sources=sources,
        crisis_detected=result.get("crisis_detected", False),
        grounded=result.get("grounded"),
        retry_count=result["retry_count"],
    )


@app.post("/query/stream")
async def query_stream(request: QueryRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_graph_events(app.state.graph, request.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
