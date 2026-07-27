"""Index the corpus normativo (reference documents) into ChromaDB."""
from pathlib import Path
from typing import Optional
import hashlib
import logging

from backend.rag.vector_store import get_chroma_client, get_or_create_collection, delete_collection

logger = logging.getLogger(__name__)


def index_corpus(
    corpus_dir: str | Path,
    collection_name: str = "corpus_normativo",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    reindex: bool = False,
) -> int:
    """Read all markdown files from corpus_dir, chunk them, and index into ChromaDB.

    Returns the number of chunks indexed.
    """
    corpus_path = Path(corpus_dir)
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

    client = get_chroma_client()

    if reindex:
        delete_collection(client, collection_name)

    collection = get_or_create_collection(client, collection_name)

    # Collect all .md files
    md_files = sorted(corpus_path.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found in {corpus_dir}")

    all_chunks: list[dict] = []

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        title = md_path.stem  # e.g. "01_termination_clause"

        # Split into sections by ## headings
        sections = text.split("\n## ")
        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue
            # Prepend the title back if it was split
            if i > 0:
                section = f"## {section}"

            # Sub-chunk if section is very long
            words = section.split()
            for j in range(0, len(words), chunk_size):
                chunk_words = words[j: j + chunk_size]
                chunk_text = " ".join(chunk_words)
                chunk_id = hashlib.md5(chunk_text.encode()).hexdigest()[:16]

                all_chunks.append({
                    "id": chunk_id,
                    "text": chunk_text,
                    "metadata": {
                        "source": md_path.name,
                        "title": title,
                        "section_idx": i,
                        "chunk_idx": j // chunk_size,
                    },
                })

    # Batch insert into ChromaDB
    batch_size = 100
    total = len(all_chunks)
    for start in range(0, total, batch_size):
        batch = all_chunks[start: start + batch_size]
        collection.add(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )

    logger.info(f"Indexed {total} chunks from {len(md_files)} corpus files into '{collection_name}'")
    return total
