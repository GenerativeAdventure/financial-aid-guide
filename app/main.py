"""
US Financial Aid Guide — FastAPI backend
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI

from app.graph_engine import query_graph, all_communities, NODES, LINKS

app = FastAPI(title="US Financial Aid Guide")

# Serve static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

SYSTEM_PROMPT = """You are a knowledgeable and friendly US financial aid advisor. \
You help students, parents, and school administrators understand federal student aid — \
including FAFSA, Pell Grants, Direct Loans, work-study, Return to Title IV rules, \
eligibility requirements, and disbursement processes.

You are given a structured excerpt from the official FSA Handbook knowledge graph. \
Use it as your primary source. Be accurate, clear, and cite specific concepts from \
the graph when relevant. If the graph context doesn't cover a question, say so and \
give a general answer with appropriate caveats.

Format your answers in plain prose — no bullet-point walls. Keep answers under 300 words \
unless the question requires more depth. Always be helpful to non-experts."""


AVAILABLE_MODELS = {
    "gpt-4.1-mini": "GPT-4.1 Mini",
    "gpt-4.1-nano": "GPT-4.1 Nano (fastest)",
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/graph")
def get_full_graph():
    """Return the full graph for vis.js rendering."""
    nodes = [
        {
            "id": n["id"],
            "label": n.get("label", n["id"]),
            "community": n.get("community"),
            "source_file": n.get("source_file", ""),
            "source_location": n.get("source_location", ""),
        }
        for n in NODES.values()
    ]
    edges = [
        {
            "source": lnk.get("source") or lnk.get("_src"),
            "target": lnk.get("target") or lnk.get("_tgt"),
            "relation": lnk.get("relation", "related_to"),
        }
        for lnk in LINKS
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/api/communities")
def get_communities():
    return {"communities": all_communities()}


@app.get("/api/models")
def get_models():
    return {"models": [{"id": k, "label": v} for k, v in AVAILABLE_MODELS.items()]}


class QueryRequest(BaseModel):
    question: str
    model: str = "gpt-4.1-mini"
    history: list[dict] = []   # [{role: "user"|"assistant", content: "..."}]


@app.post("/api/query")
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if req.model not in AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")

    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # 1. Retrieve relevant subgraph
    result = query_graph(req.question)
    subgraph = result["subgraph"]
    context  = result["context"]

    # 2. Build message list for OpenAI
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Include last 6 turns of history for multi-turn context
    for turn in req.history[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    # Inject graph context into the current user message
    user_message = f"{context}\n\n---\n\nQuestion: {req.question}"
    messages.append({"role": "user", "content": user_message})

    # 3. Call OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=req.model,
        messages=messages,
        max_tokens=600,
        temperature=0.3,
    )

    answer = response.choices[0].message.content.strip()

    return {
        "answer": answer,
        "subgraph": subgraph,
        "model": req.model,
        "tokens_used": response.usage.total_tokens if response.usage else None,
    }
