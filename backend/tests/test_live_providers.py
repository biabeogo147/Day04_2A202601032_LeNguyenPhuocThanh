import pytest

from app.agent.shared.providers import ProviderFactory
from app.config import Settings

SETTINGS = Settings()

@pytest.mark.live
@pytest.mark.skipif(not SETTINGS.openai_api_key, reason="OPENAI_API_KEY is not set")
async def test_openai_live_model_responds():
    model = ProviderFactory(SETTINGS).chat_model("openai")
    response = await model.ainvoke("Reply with exactly: ok")
    assert "ok" in str(response.content).lower()


@pytest.mark.live
@pytest.mark.skipif(not SETTINGS.gemini_api_key, reason="GEMINI_API_KEY is not set")
async def test_gemini_live_model_responds():
    model = ProviderFactory(SETTINGS).chat_model("gemini")
    response = await model.ainvoke("Reply with exactly: ok")
    assert "ok" in str(response.content).lower()
