"""Deterministic local embeddings for offline retrieval tests and baselines."""
from __future__ import annotations

import hashlib
import math


class DeterministicHashEmbedding:
    """Hash character unigrams and bigrams into a normalized fixed vector."""

    def __init__(self, dimensions: int = 256):
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self.dimensions = dimensions

    @staticmethod
    def _tokens(text: str) -> list[str]:
        normalized = "".join(text.lower().split())
        if not normalized:
            return []
        unigrams = list(normalized)
        bigrams = [
            normalized[index:index + 2]
            for index in range(len(normalized) - 1)
        ]
        return unigrams + bigrams

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.blake2b(
                token.encode("utf-8"),
                digest_size=8,
            ).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]
