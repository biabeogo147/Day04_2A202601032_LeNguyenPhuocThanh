from __future__ import annotations

import hashlib
import re
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from .catalog import Catalog


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", value.casefold()).strip("_")


class ChromaProductIndex:
    def __init__(
        self,
        catalog: Catalog,
        *,
        persist_directory: str | Path,
        embeddings: Embeddings,
        embedding_provider: str,
        embedding_model: str,
    ) -> None:
        self.catalog = catalog
        model_identity = hashlib.sha256(
            f"{embedding_provider}:{embedding_model}".encode("utf-8")
        ).hexdigest()[:8]
        provider_slug = _slug(embedding_provider)[:16] or "embedding"
        self.collection_name = (
            f"tpcn_{catalog.dataset_fingerprint[:8]}_{provider_slug}_{model_identity}"
        )
        path = Path(persist_directory)
        path.mkdir(parents=True, exist_ok=True)
        self.store = Chroma(
            collection_name=self.collection_name,
            embedding_function=embeddings,
            persist_directory=str(path),
            collection_metadata={
                "hnsw:space": "cosine",
                "dataset_fingerprint": catalog.dataset_fingerprint,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
            },
        )

    def ensure_index(self) -> int:
        existing = set(self.store.get(include=[])["ids"])
        missing = [product for product in self.catalog.products if product.id not in existing]
        if missing:
            documents = [
                Document(
                    id=product.id,
                    page_content=product.embedding_text(),
                    metadata={
                        "product_id": product.id,
                        "name": product.name,
                        "source_row": product.source_row,
                        "price_vnd": product.price_vnd,
                        "dosage_form": product.dosage_form,
                    },
                )
                for product in missing
            ]
            self.store.add_documents(documents=documents, ids=[product.id for product in missing])
        return self.count()

    def count(self) -> int:
        return int(self.store._collection.count())

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        if not query.strip() or limit <= 0:
            return []
        results = self.store.similarity_search_with_relevance_scores(query, k=limit)
        return [
            (
                str(document.metadata["product_id"]),
                round(max(0.0, min(float(score), 1.0)), 4),
            )
            for document, score in results
        ]
