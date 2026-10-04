from app.ingestion.chunker import chunk_text


def test_chunker_preserves_content() -> None:
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = chunk_text(text, chunk_size=35, overlap=5)
    assert chunks
    combined = " ".join(chunks)
    assert "Paragraph one." in combined
    assert "Paragraph two." in combined
    assert "Paragraph three." in combined
