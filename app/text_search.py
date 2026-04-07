"""
BM25 text search over extracted handbook chunks.
Chunks are built at startup from chunks.json (pre-extracted from PDFs).
"""

import json
from pathlib import Path
from rank_bm25 import BM25Okapi

_CHUNKS_PATH = Path(__file__).parent.parent / "graphify-out" / "chunks.json"

# ---------------------------------------------------------------------------
# Load and index at module import
# ---------------------------------------------------------------------------

def _load():
    if not _CHUNKS_PATH.exists():
        print(f"WARNING: {_CHUNKS_PATH} not found — text search disabled")
        return [], None
    chunks = json.loads(_CHUNKS_PATH.read_text())
    corpus = [c["text"].lower().split() for c in chunks]
    index  = BM25Okapi(corpus)
    print(f"BM25 index built: {len(chunks)} chunks")
    return chunks, index

CHUNKS, BM25_INDEX = _load()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

SOURCE_LABELS = {
    "vol1-student-eligibility":        "Vol 1 – Student Eligibility",
    "vol2-school-eligibility":         "Vol 2 – School Eligibility",
    "vol3-calendars-coa-packaging":    "Vol 3 – COA & Packaging",
    "vol4-processing-aid":             "Vol 4 – Processing Aid",
    "vol5-withdrawals-r2t4":           "Vol 5 – Withdrawals & R2T4",
    "vol6-campus-based":               "Vol 6 – Campus-Based Programs",
    "vol7-pell-grant":                 "Vol 7 – Pell Grant",
    "vol8-direct-loan":                "Vol 8 – Direct Loans",
    "vol9-teach-grant":                "Vol 9 – TEACH Grant",
    "application-and-verification-guide": "Application & Verification Guide",
}


def search_chunks(query: str, top_k: int = 5) -> str:
    """
    Return a formatted string of the top_k most relevant handbook passages
    for use as LLM context.
    """
    if BM25_INDEX is None or not CHUNKS:
        return ""

    tokens = query.lower().split()
    scores = BM25_INDEX.get_scores(tokens)
    top_idx = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]

    lines = ["## Relevant handbook passages\n"]
    for rank, idx in enumerate(top_idx, 1):
        chunk  = CHUNKS[idx]
        source = SOURCE_LABELS.get(chunk["source"], chunk["source"])
        lines.append(f"### [{source}]\n{chunk['text']}\n")

    return "\n".join(lines)
