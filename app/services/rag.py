"""RAG service using ChromaDB and multilingual embeddings."""

from __future__ import annotations

import os
from pathlib import Path

import chromadb
import structlog
from chromadb.config import Settings as ChromaSettings

from app.config import settings

logger = structlog.get_logger()

_chroma_client: chromadb.HttpClient | None = None
_collection: chromadb.Collection | None = None

COLLECTION_NAME = "osus_knowledge_base"


def get_chroma_client() -> chromadb.HttpClient:
    """Get or create ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return _chroma_client


def get_collection() -> chromadb.Collection:
    """Get or create the knowledge base collection."""
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks, respecting sentence boundaries."""
    # Split by sentences (Arabic and English)
    import re

    sentences = re.split(r"(?<=[.!?؟。])\s+", text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Keep overlap
            words = current_chunk.split()
            overlap_words = words[-overlap:] if len(words) > overlap else words
            current_chunk = " ".join(overlap_words) + " " + sentence
        else:
            current_chunk += " " + sentence if current_chunk else sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


async def ingest_text(text: str, source: str, metadata: dict | None = None) -> int:
    """Ingest a text document into the knowledge base."""
    collection = get_collection()
    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)

    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        chunk_id = f"{source}_{i}"
        ids.append(chunk_id)
        documents.append(chunk)
        meta = {"source": source, "chunk_index": i}
        if metadata:
            meta.update(metadata)
        metadatas.append(meta)

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    logger.info("Ingested document", source=source, chunks=len(chunks))
    return len(chunks)


async def ingest_pdf(file_path: str) -> int:
    """Ingest a PDF file into the knowledge base."""
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    full_text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            full_text += page_text + "\n"

    source = Path(file_path).stem
    return await ingest_text(full_text, source=source, metadata={"type": "pdf", "file": file_path})


async def search(query: str, n_results: int = 5) -> list[dict]:
    """Search the knowledge base for relevant information."""
    collection = get_collection()

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
        )
    except Exception as e:
        logger.error("RAG search failed", error=str(e))
        return []

    documents = []
    if results and results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            entry = {
                "text": doc,
                "source": results["metadatas"][0][i].get("source", "unknown") if results["metadatas"] else "unknown",
            }
            if results["distances"]:
                entry["relevance_score"] = 1 - results["distances"][0][i]
            documents.append(entry)

    logger.info("RAG search completed", query=query[:50], results=len(documents))
    return documents


async def get_project_data() -> str:
    """Get all project data as a single string for the system prompt."""
    collection = get_collection()

    try:
        all_docs = collection.get(limit=100)
    except Exception:
        return "لا تتوفر بيانات المشروع حاليًا."

    if not all_docs or not all_docs["documents"]:
        return "لا تتوفر بيانات المشروع حاليًا."

    return "\n\n".join(all_docs["documents"])
