"""
Graph traversal engine for FSA knowledge graph.
Loads graph.json once at startup; all queries run in-memory.
"""

import json
import math
from collections import defaultdict, deque
from pathlib import Path

# ---------------------------------------------------------------------------
# Load graph at module import time (fast, ~162KB)
# ---------------------------------------------------------------------------

_GRAPH_PATH = Path(__file__).parent.parent / "graphify-out" / "graph.json"

def _load():
    raw = json.loads(_GRAPH_PATH.read_text())
    nodes = {n["id"]: n for n in raw["nodes"]}

    # Build adjacency: node_id -> list of (neighbor_id, relation, weight)
    adj = defaultdict(list)
    for link in raw["links"]:
        src = link.get("source") or link.get("_src")
        tgt = link.get("target") or link.get("_tgt")
        rel = link.get("relation", "related_to")
        w   = link.get("weight", 1.0)
        if src in nodes and tgt in nodes:
            adj[src].append((tgt, rel, w))
            adj[tgt].append((src, rel, w))  # treat as undirected for search

    return nodes, adj, raw["links"]

NODES, ADJ, LINKS = _load()


# ---------------------------------------------------------------------------
# Community labels (from GRAPH_REPORT analysis)
# ---------------------------------------------------------------------------

COMMUNITY_LABELS = {
    0:  "Campus-Based Programs",
    1:  "Direct Loans & PLUS",
    2:  "Return to Title IV (R2T4)",
    3:  "School Eligibility & Certification",
    4:  "Student Eligibility",
    5:  "FAFSA & SAI Calculation",
    6:  "Disbursement & Verification",
    7:  "Pell Grant",
    8:  "Satisfactory Academic Progress",
    9:  "Graduate & Professional Aid",
    10: "TEACH Grant",
    11: "Iraq & Afghanistan Service Grant",
    12: "Consumer Information",
    13: "Study Abroad & Consortium",
}


# ---------------------------------------------------------------------------
# Query: keyword search → seed nodes, then BFS expansion
# ---------------------------------------------------------------------------

def _score_node(node: dict, terms: list[str]) -> float:
    label = node.get("label", "").lower()
    score = 0.0
    for term in terms:
        if term in label:
            score += 2.0 if label.startswith(term) else 1.0
    return score


def search_nodes(query: str, top_k: int = 8) -> list[dict]:
    """Return top_k nodes most relevant to the query string."""
    terms = [t.lower() for t in query.split() if len(t) > 2]
    scored = []
    for nid, node in NODES.items():
        s = _score_node(node, terms)
        if s > 0:
            scored.append((s, nid, node))
    scored.sort(key=lambda x: -x[0])
    return [{"id": nid, **node} for _, nid, node in scored[:top_k]]


def bfs_subgraph(seed_ids: list[str], depth: int = 2, max_nodes: int = 30) -> dict:
    """
    BFS from seed nodes up to `depth` hops. Returns a subgraph dict with
    nodes and edges suitable for both LLM context and vis.js rendering.
    """
    visited = set()
    queue = deque((sid, 0) for sid in seed_ids if sid in NODES)
    subgraph_nodes = {}
    subgraph_edges = []

    while queue and len(subgraph_nodes) < max_nodes:
        nid, d = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        subgraph_nodes[nid] = NODES[nid]

        if d < depth:
            for neighbor, rel, w in ADJ[nid]:
                if neighbor not in visited:
                    queue.append((neighbor, d + 1))
                if neighbor in visited or neighbor in {q[0] for q in queue}:
                    # record edge if both ends are (or will be) in subgraph
                    pass

    # Collect edges where both endpoints ended up in the subgraph
    seen_edges = set()
    for link in LINKS:
        src = link.get("source") or link.get("_src")
        tgt = link.get("target") or link.get("_tgt")
        if src in subgraph_nodes and tgt in subgraph_nodes:
            key = tuple(sorted([src, tgt]))
            if key not in seen_edges:
                seen_edges.add(key)
                subgraph_edges.append({
                    "source": src,
                    "target": tgt,
                    "relation": link.get("relation", "related_to"),
                })

    return {
        "nodes": [
            {
                "id": nid,
                "label": n.get("label", nid),
                "community": n.get("community"),
                "community_label": COMMUNITY_LABELS.get(n.get("community"), f"Topic {n.get('community')}"),
                "source_file": n.get("source_file", ""),
                "source_location": n.get("source_location", ""),
            }
            for nid, n in subgraph_nodes.items()
        ],
        "edges": subgraph_edges,
    }


def query_graph(question: str) -> dict:
    """
    Main entry point: takes a natural-language question, returns a subgraph
    and a plain-text context string ready to be passed to an LLM.
    """
    seeds = search_nodes(question, top_k=6)
    seed_ids = [s["id"] for s in seeds]
    subgraph = bfs_subgraph(seed_ids, depth=2, max_nodes=35)

    # Build LLM context: structured text describing relevant nodes + edges
    lines = ["## Relevant concepts from the FSA Handbook knowledge graph\n"]
    for n in subgraph["nodes"]:
        topic = n["community_label"]
        loc   = n.get("source_location") or ""
        src   = n.get("source_file", "").replace("handbook/", "").replace(".pdf", "")
        ref   = f" ({src}, {loc})" if loc else (f" ({src})" if src else "")
        lines.append(f"- **{n['label']}** [{topic}]{ref}")

    if subgraph["edges"]:
        lines.append("\n## Key relationships\n")
        for e in subgraph["edges"][:20]:
            src_label = NODES.get(e["source"], {}).get("label", e["source"])
            tgt_label = NODES.get(e["target"], {}).get("label", e["target"])
            rel       = e["relation"].replace("_", " ")
            lines.append(f"- {src_label} **{rel}** {tgt_label}")

    context = "\n".join(lines)
    return {"subgraph": subgraph, "context": context, "seed_nodes": seeds}


def all_communities() -> list[dict]:
    """Return community summary for the sidebar."""
    counts = defaultdict(int)
    for n in NODES.values():
        counts[n.get("community")] += 1
    return [
        {
            "id": cid,
            "label": COMMUNITY_LABELS.get(cid, f"Topic {cid}"),
            "count": counts[cid],
        }
        for cid in sorted(counts, key=lambda c: -counts[c])
        if cid is not None
    ]
