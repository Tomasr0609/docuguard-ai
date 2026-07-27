from typing import Any, Optional

from backend.rag.vector_store import get_chroma_client, get_or_create_collection


def retrieve(
    query: str,
    collection_name: str = "corpus_normativo",
    k: int = 5,
) -> list[dict[str, Any]]:
    """Query the ChromaDB collection and return top-k results.

    Each result contains: id, text (document), metadata, distance.
    """
    client = get_chroma_client()
    collection = get_or_create_collection(client, collection_name)

    results = collection.query(
        query_texts=[query],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict[str, Any]] = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            hits.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })

    return hits


def retrieve_context(
    query: str,
    collection_name: str = "corpus_normativo",
    k: int = 3,
    max_chars: int = 3000,
) -> str:
    """Convenience: retrieve top-k results and concatenate into a single context string."""
    hits = retrieve(query, collection_name=collection_name, k=k)

    parts: list[str] = []
    total_chars = 0
    for h in hits:
        snippet = f"[Fuente: {h['metadata'].get('title', 'desconocida')}]\n{h['text']}"
        if total_chars + len(snippet) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 100:
                parts.append(snippet[:remaining])
            break
        parts.append(snippet)
        total_chars += len(snippet)

    return "\n\n---\n\n".join(parts)
