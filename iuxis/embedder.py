"""
Local embedding client for Iuxis.

Primary:  nomic-embed-text via Ollama (768-dim, high quality for technical text)
Fallback: all-MiniLM-L6-v2 via sentence-transformers (384-dim)

Both run fully locally. No data leaves the machine.
"""

import numpy as np
import requests
import logging
from typing import List

logger = logging.getLogger("iuxis.embedder")

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
OLLAMA_EMBED_MODEL = "nomic-embed-text"


class Embedder:
    def __init__(self):
        self._st_model = None
        self._dim: int = None
        self._backend = self._detect_backend()
        logger.info(f"[Embedder] Using backend: {self._backend}, dim={self.dim}")

    def _detect_backend(self) -> str:
        try:
            r = requests.post(
                OLLAMA_EMBED_URL,
                json={"model": OLLAMA_EMBED_MODEL, "prompt": "warmup"},
                timeout=8
            )
            if r.status_code == 200:
                vec = r.json().get("embedding", [])
                if vec:
                    self._dim = len(vec)
                    return "ollama"
        except Exception as e:
            logger.warning(f"[Embedder] Ollama unavailable ({e}), using sentence-transformers fallback")
        return "sentence_transformers"

    @property
    def dim(self) -> int:
        if self._dim:
            return self._dim
        if self._backend == "sentence_transformers":
            return self._get_st_model().get_sentence_embedding_dimension()
        return 768

    def _get_st_model(self):
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer
            self._st_model = SentenceTransformer("all-MiniLM-L6-v2")
            self._dim = self._st_model.get_sentence_embedding_dimension()
        return self._st_model

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns normalized float32 vector."""
        text = (text or "").strip()
        if not text:
            return np.zeros(self.dim, dtype="float32")

        if self._backend == "ollama":
            try:
                r = requests.post(
                    OLLAMA_EMBED_URL,
                    json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
                    timeout=15
                )
                if r.status_code == 200:
                    vec = np.array(r.json()["embedding"], dtype="float32")
                    norm = np.linalg.norm(vec)
                    return vec / norm if norm > 0 else vec
            except Exception as e:
                logger.warning(f"[Embedder] Ollama embed failed ({e}), falling back")
                self._backend = "sentence_transformers"

        # Fallback: sentence-transformers
        model = self._get_st_model()
        vec = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return vec.astype("float32")

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Embed a list of texts. Returns (N, dim) float32 array."""
        if self._backend == "sentence_transformers":
            model = self._get_st_model()
            return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype("float32")
        # Ollama: embed one by one (no batch API in standard Ollama)
        return np.array([self.embed(t) for t in texts], dtype="float32")
