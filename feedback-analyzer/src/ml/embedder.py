"""Sentence embeddings shared by clustering (Tier 2) and the drift monitor.

Uses sentence-transformers (on MPS when available). If that can't load, falls back
to a fixed-dimension hashing vectoriser so every downstream step still works.
"""
from __future__ import annotations

import logging
from typing import List, Sequence

import numpy as np

from .config import Settings

log = logging.getLogger("feedback_analyzer")

HASH_DIM = 2048


class Embedder:
    def __init__(self, settings: Settings, device: str = "cpu", force_fallback: bool = False):
        self.s = settings
        self.device = device
        self.model = None
        self.name = f"hashing-{HASH_DIM}"
        self.notes: List[str] = []

        if not force_fallback:
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(settings.embedding_model, device=device)
                self.name = settings.embedding_model
            except Exception as exc:  # model missing/offline/not installed
                self.notes.append(
                    f"Sentence embeddings unavailable ({type(exc).__name__}); using hashed TF vectors."
                )
                log.warning(self.notes[-1])

        if self.model is None:
            from sklearn.feature_extraction.text import HashingVectorizer

            self._hasher = HashingVectorizer(
                n_features=HASH_DIM,
                alternate_sign=False,
                ngram_range=(1, 2),
                stop_words="english",
                norm="l2",
            )

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Return an (n, d) float32 matrix of L2-normalised embeddings."""
        texts = list(texts)
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        if self.model is not None:
            emb = self.model.encode(
                texts,
                batch_size=self.s.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return emb.astype(np.float32)
        return self._hasher.transform(texts).toarray().astype(np.float32)
