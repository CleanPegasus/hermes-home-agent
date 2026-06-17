from __future__ import annotations

import math
import os
from typing import Protocol

import httpx

# Best price/performance default: OpenAI text-embedding-3-small is 1536-dim
# (matching the vector(1536) column already declared in db/schema.sql), costs
# ~$0.02/1M tokens, and needs only httpx + an API key. Swap via EMBEDDING_PROVIDER
# (e.g. a Voyage provider) without touching the index schema.
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSION = 1536


class EmbeddingProvider(Protocol):
    name: str
    dimension: int

    def configured(self) -> bool: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class NullProvider:
    """Used when no embedding API is configured. Search falls back to keyword."""

    name = "null"

    def __init__(self, dimension: int = DEFAULT_DIMENSION) -> None:
        self.dimension = dimension

    def configured(self) -> bool:
        return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, dimension: int = DEFAULT_DIMENSION) -> None:
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30"))

    def configured(self) -> bool:
        return bool(self.api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.model, "input": texts}
        headers = {"authorization": f"Bearer {self.api_key}", "content-type": "application/json"}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/embeddings", headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"embedding request failed ({response.status_code}): {response.text[:300]}")
        data = response.json().get("data", [])
        return [item.get("embedding", []) for item in data]


_PROVIDER: EmbeddingProvider | None = None
_PROVIDER_KEY: tuple[str, str, int] | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _PROVIDER, _PROVIDER_KEY
    name = os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower()
    model = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    dimension = int(os.getenv("EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION)))
    key = (name, model, dimension)
    if _PROVIDER is not None and _PROVIDER_KEY == key:
        return _PROVIDER

    provider: EmbeddingProvider
    if name == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        provider = OpenAIEmbeddingProvider(api_key, model=model, dimension=dimension) if api_key else NullProvider(dimension)
    else:
        provider = NullProvider(dimension)
    _PROVIDER, _PROVIDER_KEY = provider, key
    return provider


def embed_texts(texts: list[str]) -> list[list[float]]:
    provider = get_embedding_provider()
    if not provider.configured():
        return [[] for _ in texts]
    return provider.embed(texts)


def embed_query(text: str) -> list[float]:
    vectors = embed_texts([text])
    return vectors[0] if vectors else []


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embedding_status() -> dict:
    provider = get_embedding_provider()
    return {
        "provider": provider.name,
        "configured": provider.configured(),
        "dimension": provider.dimension,
        "model": os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL) if provider.name != "null" else None,
    }
