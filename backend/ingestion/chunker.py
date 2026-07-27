from pathlib import Path
from typing import Optional

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document as LlamaDocument


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    metadata: Optional[dict] = None,
) -> list[dict]:
    """Split text into chunks using LlamaIndex's SentenceSplitter.

    Returns a list of dicts with keys: text, chunk_id, metadata.
    """
    if metadata is None:
        metadata = {}

    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    llama_doc = LlamaDocument(text=text, metadata=metadata)
    nodes = splitter.get_nodes_from_documents([llama_doc])

    chunks: list[dict] = []
    for i, node in enumerate(nodes):
        chunks.append({
            "text": node.text,
            "chunk_id": i,
            "metadata": {**metadata, **(node.metadata or {})},
        })

    return chunks


def chunk_document(
    file_path: str | Path,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[dict]:
    """Convenience: read a text file and chunk its contents."""
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8")
    return chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap, metadata={"source": str(file_path)})
