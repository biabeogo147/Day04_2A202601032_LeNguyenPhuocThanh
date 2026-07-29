from __future__ import annotations

from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import Settings


ProviderName = Literal["openai", "gemini"]


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def chat_model(self, provider: ProviderName):
        if provider == "openai":
            if not self.settings.openai_api_key.strip():
                raise ProviderConfigurationError(
                    "Thiếu OPENAI_API_KEY. Hãy sao chép .env.example thành .env và điền key."
                )
            return ChatOpenAI(
                api_key=self.settings.openai_api_key,
                model=self.settings.openai_chat_model,
                temperature=0,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=2,
            )
        if provider == "gemini":
            if not self.settings.gemini_api_key.strip():
                raise ProviderConfigurationError(
                    "Thiếu GEMINI_API_KEY. Gemini live test sẽ tự skip khi chưa có key."
                )
            return ChatGoogleGenerativeAI(
                google_api_key=self.settings.gemini_api_key,
                model=self.settings.gemini_chat_model,
                temperature=0,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=2,
            )
        raise ProviderConfigurationError(f"Provider không được hỗ trợ: {provider}")

    def embeddings(self, provider: ProviderName):
        if provider == "openai":
            if not self.settings.openai_api_key.strip():
                raise ProviderConfigurationError(
                    "Thiếu OPENAI_API_KEY. Không thể tạo Chroma index."
                )
            return OpenAIEmbeddings(
                api_key=self.settings.openai_api_key,
                model=self.settings.openai_embedding_model,
                request_timeout=self.settings.tool_timeout_seconds,
                max_retries=2,
            )
        if provider == "gemini":
            if not self.settings.gemini_api_key.strip():
                raise ProviderConfigurationError(
                    "Thiếu GEMINI_API_KEY. Không thể tạo Chroma index."
                )
            return GoogleGenerativeAIEmbeddings(
                google_api_key=self.settings.gemini_api_key,
                model=self.settings.gemini_embedding_model,
                request_options={"timeout": self.settings.tool_timeout_seconds},
            )
        raise ProviderConfigurationError(f"Provider không được hỗ trợ: {provider}")
