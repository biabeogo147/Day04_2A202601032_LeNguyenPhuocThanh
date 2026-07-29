from __future__ import annotations

import argparse

from app.agent.shared.catalog import Catalog
from app.agent.shared.providers import ProviderFactory
from app.agent.shared.vector_store import ChromaProductIndex
from app.config import Settings


def index_catalog(provider: str) -> None:
    settings = Settings()
    if provider not in {"openai", "gemini"}:
        raise SystemExit("provider phải là openai hoặc gemini")
    catalog = Catalog.from_csv(settings.resolved_path(settings.dataset_path))
    embeddings = ProviderFactory(settings).embeddings(provider)  # type: ignore[arg-type]
    model = (
        settings.openai_embedding_model
        if provider == "openai"
        else settings.gemini_embedding_model
    )
    index = ChromaProductIndex(
        catalog,
        persist_directory=settings.resolved_path(settings.chroma_persist_directory),
        embeddings=embeddings,
        embedding_provider=provider,
        embedding_model=model,
    )
    count = index.ensure_index()
    print(f"Indexed {count} products into {index.collection_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Day04 local maintenance commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    index_parser = subparsers.add_parser("index", help="Build or reuse the Chroma index")
    index_parser.add_argument("--provider", choices=("openai", "gemini"), default="openai")
    args = parser.parse_args()
    if args.command == "index":
        index_catalog(args.provider)


if __name__ == "__main__":
    main()
