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
from app.text_search import search_chunks

app = FastAPI(title="US Financial Aid Guide")

# Serve static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

SYSTEM_PROMPT = """You are a US financial aid expert. Answer questions using ONLY the handbook \
passages provided. Be direct, specific, and lead with the actual numbers or rules.

Rules:
- Lead with the direct answer and the specific dollar amounts, percentages, or rules — no preamble
- Use a short table or simple bullet list when the answer is a set of values (e.g. loan limits by year)
- Never say "the passages don't include" or "I can't quote from this source" — just answer from what you have
- If the exact figure is in the passages, quote it; if not, give the closest answer from the passages
- Keep the total response under 200 words
- Plain language — avoid jargon, explain acronyms on first use
- No hedging, no disclaimers, no "it depends" without immediately following with what it depends on"""


AVAILABLE_MODELS = {
    "gpt-5.4-mini": "GPT-5.4 Mini",
    "gpt-5.4-nano": "GPT-5.4 Nano",
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
    model: str = "gpt-5.4-mini"
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
    result    = query_graph(req.question)
    subgraph  = result["subgraph"]
    graph_ctx = result["context"]

    # Expand BM25 query with graph node labels (fixes vocabulary mismatch)
    node_labels = " ".join(n["label"] for n in result["seed_nodes"][:6])
    expanded_query = f"{req.question} {node_labels}"
    text_ctx = search_chunks(expanded_query, top_k=6)

    context = f"{text_ctx}\n\n{graph_ctx}" if text_ctx else graph_ctx

    # 2. Build message list for OpenAI
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Include last 6 turns of history for multi-turn context
    for turn in req.history[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    # Inject graph + text context into the current user message
    user_message = f"{context}\n\n---\n\nQuestion: {req.question}"
    messages.append({"role": "user", "content": user_message})

    # 3. Call OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=req.model,
        messages=messages,
        max_completion_tokens=800,
        temperature=0.3,
    )

    answer = response.choices[0].message.content.strip()

    return {
        "answer": answer,
        "subgraph": subgraph,
        "model": req.model,
        "tokens_used": response.usage.total_tokens if response.usage else None,
    }
