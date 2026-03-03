#!/usr/bin/env python3
"""Ingest documents from the knowledge_base directory into ChromaDB.

Usage:
    python scripts/ingest_documents.py
    python scripts/ingest_documents.py --path /path/to/specific/file.pdf
    python scripts/ingest_documents.py --text "بيانات المشروع..." --source "project_info"
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services import rag


async def ingest_directory(directory: str) -> None:
    """Ingest all supported files from a directory."""
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"Directory not found: {directory}")
        return

    files = list(dir_path.glob("**/*.pdf")) + list(dir_path.glob("**/*.txt"))
    if not files:
        print(f"No PDF or TXT files found in {directory}")
        return

    total_chunks = 0
    for file_path in files:
        print(f"Ingesting: {file_path.name}...")
        try:
            if file_path.suffix.lower() == ".pdf":
                chunks = await rag.ingest_pdf(str(file_path))
            else:
                text = file_path.read_text(encoding="utf-8")
                chunks = await rag.ingest_text(text, source=file_path.stem)
            total_chunks += chunks
            print(f"  -> {chunks} chunks ingested")
        except Exception as e:
            print(f"  -> Error: {e}")

    print(f"\nTotal: {total_chunks} chunks ingested from {len(files)} files")


async def ingest_single_file(file_path: str) -> None:
    """Ingest a single file."""
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {file_path}")
        return

    print(f"Ingesting: {path.name}...")
    if path.suffix.lower() == ".pdf":
        chunks = await rag.ingest_pdf(str(path))
    else:
        text = path.read_text(encoding="utf-8")
        chunks = await rag.ingest_text(text, source=path.stem)

    print(f"  -> {chunks} chunks ingested")


async def ingest_text(text: str, source: str) -> None:
    """Ingest raw text."""
    print(f"Ingesting text from source: {source}...")
    chunks = await rag.ingest_text(text, source=source)
    print(f"  -> {chunks} chunks ingested")


async def main():
    parser = argparse.ArgumentParser(description="Ingest documents into the knowledge base")
    parser.add_argument("--path", help="Path to a specific file to ingest")
    parser.add_argument("--dir", default="knowledge_base", help="Directory to ingest (default: knowledge_base)")
    parser.add_argument("--text", help="Raw text to ingest")
    parser.add_argument("--source", default="manual", help="Source name for raw text")
    args = parser.parse_args()

    if args.text:
        await ingest_text(args.text, args.source)
    elif args.path:
        await ingest_single_file(args.path)
    else:
        await ingest_directory(args.dir)


if __name__ == "__main__":
    asyncio.run(main())
