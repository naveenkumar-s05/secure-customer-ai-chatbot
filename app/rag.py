
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
    if not text or not str(text).strip():
        raise ValueError("Cannot embed empty text")

    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={
                "model": OLLAMA_EMBED_MODEL,
                "prompt": str(text),
            },
            timeout=120.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Embedding request failed: {exc}") from exc

    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError("Invalid embedding response") from exc

    embedding = data.get("embedding")
    if not embedding or not isinstance(embedding, list):
        raise RuntimeError("Ollama returned no embedding.")

    return embedding


def ensure_collection() -> None:
    """Create the Qdrant collection if it does not already exist."""
    try:
        existing = qdrant.get_collections().collections
    except Exception as exc:
        raise RuntimeError(f"Failed to access vector store: {exc}") from exc

    if any(collection.name == QDRANT_COLLECTION for collection in existing):
        return

    # Determine the vector size from the embedding model.
    sample_vector = embed_text("Determine vector dimension.")

    try:
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=models.VectorParams(
                size=len(sample_vector),
                distance=models.Distance.COSINE,
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to create vector collection: {exc}") from exc


def invoice_text(invoice: Any) -> str:
    """Turn an invoice record into searchable text."""
    return (
        f"Invoice number: {getattr(invoice, 'invoice_number', '')}. "
        f"Invoice date: {getattr(invoice, 'invoice_date', '')}. "
        f"Amount: {getattr(invoice, 'amount', '')} {getattr(invoice, 'currency', 'INR')}. "
        f"Payment status: {getattr(invoice, 'payment_status', '')}."
    )


def stable_point_id(customer_id: int, invoice_id: int) -> str:
    """Create a deterministic Qdrant point ID for each invoice."""
    value = f"customer:{int(customer_id)}:invoice:{int(invoice_id)}".encode("utf-8")
    digest = hashlib.md5(value).hexdigest()
    return str(uuid.UUID(digest))


def index_invoice(invoice: Any) -> None:
    """Embed and upsert one invoice, including its customer ownership."""
    try:
        ensure_collection()

        text = invoice_text(invoice)
        if not text.strip():
            raise ValueError("Cannot index empty invoice text")
        vector = embed_text(text)

        qdrant.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[
                models.PointStruct(
                    id=stable_point_id(getattr(invoice, "customer_id"), getattr(invoice, "id")),
                    vector=vector,
                    payload={
                        "customer_id": int(getattr(invoice, "customer_id")),
                        "source_type": "invoice",
                        "source_id": int(getattr(invoice, "id")),
                        "invoice_number": getattr(invoice, "invoice_number"),
                        "text": text,
                    },
                )
            ],
        )
    except Exception:
        raise


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
    if not query or not str(query).strip():
        return []
    try:
        ensure_collection()
    except Exception:
        return []

    try:
        vector = embed_text(query)
    except Exception:
        return []

    try:
        response = qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="customer_id",
                        match=models.MatchValue(value=int(customer_id)),
                    )
                ]
            ),
            limit=max(1, min(int(limit), 10)),
            with_payload=True,
        )
    except Exception:
        return []

    results = []

    try:
        for point in getattr(response, "points", []):
            payload = point.payload or {}

            results.append(
                {
                    "source_type": payload.get("source_type"),
                    "source_id": payload.get("source_id"),
                    "invoice_number": payload.get("invoice_number"),
                    "text": payload.get("text"),
                    "score": getattr(point, "score", None),
                }
            )
    except Exception:
        return []

    return results
