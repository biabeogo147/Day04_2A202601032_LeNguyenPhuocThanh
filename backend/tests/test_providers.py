import pytest

from app.agent.shared.providers import ProviderConfigurationError, ProviderFactory
from app.config import Settings


def test_openai_provider_requires_key(tmp_path):
    settings = Settings(
        openai_api_key="",
        dataset_path=tmp_path / "data.csv",
        chroma_persist_directory=tmp_path / "chroma",
        checkpoint_database_path=tmp_path / "checkpoints.db",
    )

    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        ProviderFactory(settings).chat_model("openai")


def test_gemini_provider_requires_key(tmp_path):
    settings = Settings(
        gemini_api_key="",
        dataset_path=tmp_path / "data.csv",
        chroma_persist_directory=tmp_path / "chroma",
        checkpoint_database_path=tmp_path / "checkpoints.db",
    )

    with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY"):
        ProviderFactory(settings).embeddings("gemini")
