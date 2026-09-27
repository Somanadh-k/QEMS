"""Embedding generation with an offline fallback.

Production uses OpenAI `text-embedding-3-small`. When no usable API key is configured —
a fresh checkout, CI, or a developer working offline — this falls back to a local
lexical hashing embedder so that the retrieval pipeline (pgvector, HNSW, distance
thresholds, the recurrence scorer) can be exercised end to end without a network call or
a bill.

The fallback is NOT a semantic model and does not pretend to be. It is the hashing trick
over token bigrams: documents that share vocabulary land near each other, documents that
express the same idea in different words do not. That is enough to test the machinery and
seed a realistic corpus; it is not enough to ship. `embedding_model` is recorded on every
row precisely so a mixed corpus is never silently compared — see `is_offline_model`.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time

from openai import AsyncOpenAI, OpenAIError

from app.core.config import get_settings
from app.core.exceptions import AIServiceError

logger = logging.getLogger("qems.embedding")
settings = get_settings()

EMBEDDING_DIM = 1536
OFFLINE_MODEL_NAME = "offline-lexical-hash-v1"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def is_offline_model(model_name: str | None) -> bool:
    return model_name == OFFLINE_MODEL_NAME


def api_key_is_usable() -> bool:
    """A placeholder key is worse than no key: it fails at call time, not at startup."""
    key = (settings.openai_api_key or "").strip()
    if not key or not key.startswith("sk-"):
        return False
    return "your-key" not in key and len(key) > 24


def _tokens(text: str) -> list[str]:
    words = _TOKEN_RE.findall(text.lower())
    # Bigrams as well as unigrams so word order carries a little weight.
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


def local_embedding(text: str) -> list[float]:
    """Deterministic L2-normalised hashed term-frequency vector."""
    vector = [0.0] * EMBEDDING_DIM
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        # An empty or punctuation-only description still needs a valid vector.
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


class EmbeddingResult:
    def __init__(self, vector: list[float], model: str, tokens: int, latency_ms: int, offline: bool):
        self.vector = vector
        self.model = model
        self.tokens = tokens
        self.latency_ms = latency_ms
        self.offline = offline


async def generate_embedding(text: str) -> EmbeddingResult:
    started = time.monotonic()

    if not api_key_is_usable():
        logger.debug("No usable OpenAI key; using the offline lexical embedder")
        return EmbeddingResult(
            vector=local_embedding(text),
            model=OFFLINE_MODEL_NAME,
            tokens=0,
            latency_ms=int((time.monotonic() - started) * 1000),
            offline=True,
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.embeddings.create(
            model=settings.openai_embedding_model, input=text
        )
    except OpenAIError as exc:
        raise AIServiceError(f"OpenAI embeddings call failed: {exc}") from exc

    return EmbeddingResult(
        vector=response.data[0].embedding,
        model=settings.openai_embedding_model,
        tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
        latency_ms=int((time.monotonic() - started) * 1000),
        offline=False,
    )
