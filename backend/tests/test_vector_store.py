from pathlib import Path

from langchain_core.embeddings import Embeddings

from app.agent.shared.catalog import Catalog
from app.agent.shared.vector_store import ChromaProductIndex


DATASET = Path(__file__).parents[2] / "data" / "DataTPCN.csv"


class DeterministicEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        lowered = text.casefold()
        return [
            float(lowered.count("omega") + lowered.count("fish")),
            float(lowered.count("canxi")),
            float(lowered.count("ngủ") + lowered.count("sleep")),
        ]


def test_collection_identity_includes_dataset_and_embedding_model(tmp_path):
    catalog = Catalog.from_csv(DATASET)

    first = ChromaProductIndex(
        catalog,
        persist_directory=tmp_path,
        embeddings=DeterministicEmbeddings(),
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    second = ChromaProductIndex(
        catalog,
        persist_directory=tmp_path,
        embeddings=DeterministicEmbeddings(),
        embedding_provider="openai",
        embedding_model="text-embedding-3-large",
    )

    assert catalog.dataset_fingerprint[:8] in first.collection_name
    assert first.collection_name != second.collection_name


def test_indexing_is_idempotent_and_search_returns_catalog_ids(tmp_path):
    catalog = Catalog.from_csv(DATASET)
    index = ChromaProductIndex(
        catalog,
        persist_directory=tmp_path,
        embeddings=DeterministicEmbeddings(),
        embedding_provider="fake",
        embedding_model="deterministic",
    )

    assert index.ensure_index() == 100
    assert index.ensure_index() == 100
    assert index.count() == 100

    results = index.search("Omega fish oil", limit=3)

    assert results
    assert catalog.get(results[0][0]).id == results[0][0]
    assert 0 <= results[0][1] <= 1
