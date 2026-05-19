import logging
from functools import cached_property

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import Settings


logger = logging.getLogger("brainclaw.embeddings")


class EmbeddingProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def model(self) -> SentenceTransformer:
        logger.info("loading_embedding_model", extra={"model_name": self.settings.embedding_model_name})
        return SentenceTransformer(self.settings.embedding_model_name)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.settings.embedding_dimension), dtype=np.float32)
        vectors = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = np.asarray(vectors, dtype=np.float32)
        if len(vectors.shape) == 1:
            vectors = vectors.reshape(1, -1)
        return vectors

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_texts([query])

