"""Local embedding adapters.

HashLexicalEmbedder is a deterministic lexical encoder (signed feature
hashing, L2-normalized). It is clearly labeled simulated — cosine similarity
approximates token overlap, which is enough to group recurring phrasing and
keeps clustering runnable without heavyweight model downloads.

SentenceTransformerEmbedder is the optional local neural adapter; it requires
the `openclass-server[embeddings]` extra and never fabricates vectors when the
model is unavailable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from hashlib import md5

from openclass_core.providers import ProviderError


class HashLexicalEmbedder:
    model_version = "hash-lexical-v1"
    dimensions = 256

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vectors.append(self._vector(text))
        return vectors

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * HashLexicalEmbedder.dimensions
        for token in text.lower().split():
            cleaned = token.strip(".,!?;:'\"()[]")
            if not cleaned:
                continue
            digest = md5(cleaned.encode()).digest()
            slot = int.from_bytes(digest[:4], "big") % HashLexicalEmbedder.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[slot] += sign
        norm = sum(value * value for value in vector) ** 0.5
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class SentenceTransformerEmbedder:
    """Optional neural adapter (requires the embeddings extra)."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as error:  # pragma: no cover - depends on optional extra
            raise ProviderError(
                "sentence-transformers is not installed; install openclass-server[embeddings]",
                kind="unsupported",
            ) from error
        self._model = SentenceTransformer(model_name)
        self.model_version = model_name
        self.dimensions = int(self._model.get_sentence_embedding_dimension())

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        embeddings = await asyncio.to_thread(self._model.encode, list(texts))
        return [vector.tolist() for vector in embeddings]
