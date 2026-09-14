"""Agent tool interfaces for the CareClaw / NemoClaw RAG pipeline.

Exposes MongoDB text-retrieval as a structured, JSON-in/JSON-out tool callable
by Hermes, OpenClaw, or custom agent runtimes inside the OpenShell sandbox.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from rag.config import Config, load_config
from rag.pipeline import retrieve
from rag.store import Hit, RagStore


def query_protocol_knowledge_base(
    query: str,
    top_k: int | None = None,
    store: RagStore | None = None,
    config: Config | None = None,
) -> dict[str, Any]:
    """Query the clinical protocol knowledge base stored in MongoDB.

    Returns a JSON-serializable dictionary with matching protocol sections,
    relevance scores, and file paths.
    """
    cfg = config or load_config()
    rag_store = store or RagStore(cfg.mongodb)

    hits: list[Hit] = retrieve(rag_store, query, top_k=top_k or cfg.retrieval.top_k)

    results = []
    for hit in hits:
        results.append({
            "path": hit.path,
            "start_line": hit.start_line,
            "end_line": hit.end_line,
            "score": hit.score,
            "text": hit.text.strip(),
        })

    return {
        "query": query,
        "hits_count": len(results),
        "results": results,
    }


# Tool definition adhering to OpenAI-compatible function calling specifications
PROTOCOL_QUERY_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "query_protocol_knowledge_base",
        "description": "Search the clinical trial protocol (eligibility criteria, prohibited medications, visit windows, and toxicity holding rules) indexed in MongoDB.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search term or clinical question (e.g. 'prohibited CYP3A4 inhibitors' or 'Cycle 1 Day 14 visit window')."
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of protocol sections to retrieve (default 3)."
                }
            },
            "required": ["query"]
        }
    }
}
