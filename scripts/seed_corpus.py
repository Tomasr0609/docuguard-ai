"""Seed the corpus normativo into ChromaDB.

Usage:
    python scripts/seed_corpus.py          # index (safe, skip existing)
    python scripts/seed_corpus.py --reindex  # delete and reindex
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.rag.indexer import index_corpus


def main() -> None:
    reindex = "--reindex" in sys.argv
    corpus_dir = os.path.join(os.path.dirname(__file__), "..", "data", "corpus_normativo")

    print(f">>> Indexing corpus from: {corpus_dir}")
    total = index_corpus(corpus_dir, reindex=reindex)
    print(f">>> Done. {total} chunks indexed in ChromaDB (./chroma_db)")


if __name__ == "__main__":
    main()
