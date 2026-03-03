"""Tests for RAG service."""

import pytest

from app.services.rag import chunk_text


def test_chunk_text_basic():
    """Test basic text chunking."""
    text = "هذا نص تجريبي. هذه جملة ثانية. وهذه جملة ثالثة."
    chunks = chunk_text(text, chunk_size=30, overlap=5)
    assert len(chunks) >= 1
    # All original text should be covered
    full = " ".join(chunks)
    assert "نص تجريبي" in full


def test_chunk_text_short():
    """Test chunking with text shorter than chunk size."""
    text = "نص قصير."
    chunks = chunk_text(text, chunk_size=512, overlap=50)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_arabic_sentences():
    """Test chunking respects Arabic sentence boundaries."""
    text = (
        "مشروع عين أُسُس يقع في موقع متميز. "
        "يتوفر فيه وحدات سكنية متنوعة. "
        "الأسعار تبدأ من مليون ريال. "
        "المشروع قريب من جميع الخدمات."
    )
    chunks = chunk_text(text, chunk_size=80, overlap=10)
    assert len(chunks) >= 2
