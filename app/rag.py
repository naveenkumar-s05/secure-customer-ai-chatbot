
import hashlib
import uuid
from typing import Any

import httpx
from qdrant_client import QdrantClient, models

from app.config import (
    OLLAMA_URL,
    OLLAMA_EMBED_MODEL,
    QDRANT_COLLECTION,
)

# Persistent local Qdrant storage.
# This creates qdrant_data/ in your project directory.
qdrant = QdrantClient(path="./qdrant_data")


def embed_text(text: str) -> list[float]:
    """Generate a vector embedding using the local Ollama model."""
    response = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={
            "model": OLLAMA_EMBED_MODEL,
            "prompt": text,
        },
        timeout=120.0,
    )
    response.raise_for_status()

    embedding = response.json().get("embedding")
    if not embedding:
        raise RuntimeError("Ollama returned no embedding.")

    return embedding


def ensure_collection() -> None:
    """Create the Qdrant collection if it does not already exist."""
    existing = qdrant.get_collections().collections

    if any(collection.name == QDRANT_COLLECTION for collection in existing):
        return

    # Determine the vector size from the embedding model.
    sample_vector = embed_text("Determine vector dimension.")

    qdrant.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=models.VectorParams(
            size=len(sample_vector),
            distance=models.Distance.COSINE,
        ),
    )


def invoice_text(invoice: Any) -> str:
    """Turn an invoice record into searchable text."""
    return (
        f"Invoice number: {invoice.invoice_number}. "
        f"Invoice date: {invoice.invoice_date}. "
        f"Amount: {invoice.amount} {invoice.currency}. "
        f"Payment status: {invoice.payment_status}."
    )


def stable_point_id(customer_id: int, invoice_id: int) -> str:
    """Create a deterministic Qdrant point ID for each invoice."""
    value = f"customer:{customer_id}:invoice:{invoice_id}".encode("utf-8")
    digest = hashlib.md5(value).hexdigest()
    return str(uuid.UUID(digest))


def index_invoice(invoice: Any) -> None:
    """Embed and upsert one invoice, including its customer ownership."""
    ensure_collection()

    text = invoice_text(invoice)
    vector = embed_text(text)

    qdrant.upsert(
        collection_name=QDRANT_COLLECTION,
        points=[
            models.PointStruct(
                id=stable_point_id(invoice.customer_id, invoice.id),
                vector=vector,
                payload={
                    "customer_id": invoice.customer_id,
                    "source_type": "invoice",
                    "source_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "text": text,
                },
            )
        ],
    )


def search_records(
    customer_id: int,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """
    Search indexed records for one customer only.

    customer_id must come from the authenticated user on the server,
    not from a customer ID supplied by the chat user.
    """
    ensure_collection()

    vector = embed_text(query)

    response = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="customer_id",
                    match=models.MatchValue(value=customer_id),
                )
            ]
        ),
        limit=max(1, min(limit, 10)),
        with_payload=True,
    )

    results = []

    for point in response.points:
        payload = point.payload or {}

        results.append(
            {
                "source_type": payload.get("source_type"),
                "source_id": payload.get("source_id"),
                "invoice_number": payload.get("invoice_number"),
                "text": payload.get("text"),
                "score": point.score,
            }
        )

    return results
