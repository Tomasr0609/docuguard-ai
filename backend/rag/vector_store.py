from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.config import settings


def get_chroma_client(path: Optional[str] = None) -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=path or settings.chroma_db_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_or_create_collection(
    client: chromadb.PersistentClient,
    name: str = "corpus_normativo",
) -> chromadb.Collection:
    """Get existing collection or create a new one."""
    try:
        return client.get_collection(name)
    except (ValueError, chromadb.errors.NotFoundError):
        return client.create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )


def delete_collection(client: chromadb.PersistentClient, name: str = "corpus_normativo") -> None:
    try:
        client.delete_collection(name)
    except (ValueError, chromadb.errors.NotFoundError):
        pass
