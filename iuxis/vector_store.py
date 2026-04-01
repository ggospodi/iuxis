"""
FAISS vector store for semantic retrieval over user_knowledge entries.

Storage:
  ~/.iuxis/vectors/knowledge.index   — FAISS binary index
  ~/.iuxis/vectors/knowledge_map.json — faiss_id -> knowledge entry id mapping

Index type: IndexFlatIP (inner product on normalized vectors = cosine similarity)
Thread safety: persist on every add (acceptable for write-infrequent workload)
"""

import os
import json
import logging
import numpy as np
import faiss
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger("iuxis.vector_store")

VECTOR_DIR = os.path.expanduser("~/.iuxis/vectors/")
INDEX_PATH = os.path.join(VECTOR_DIR, "knowledge.index")
MAP_PATH   = os.path.join(VECTOR_DIR, "knowledge_map.json")


class VectorStore:
    def __init__(self, embed_dim: int):
        self.embed_dim = embed_dim
        os.makedirs(VECTOR_DIR, exist_ok=True)
        self._load_or_init()
        logger.info(f"[VectorStore] Ready. {self.index.ntotal} entries indexed.")

    def _load_or_init(self):
        if os.path.exists(INDEX_PATH) and os.path.exists(MAP_PATH):
            try:
                self.index = faiss.read_index(INDEX_PATH)
                with open(MAP_PATH) as f:
                    raw = json.load(f)
                self.id_map: Dict[int, int] = {int(k): int(v) for k, v in raw.items()}
                self.next_id = (max(self.id_map.keys()) + 1) if self.id_map else 0
                return
            except Exception as e:
                logger.warning(f"[VectorStore] Failed to load existing index ({e}), reinitializing")

        self.index = faiss.IndexFlatIP(self.embed_dim)
        self.id_map = {}
        self.next_id = 0
        self._persist()

    def _persist(self):
        faiss.write_index(self.index, INDEX_PATH)
        with open(MAP_PATH, "w") as f:
            json.dump({str(k): v for k, v in self.id_map.items()}, f)

    def add(self, entry_id: int, vector: np.ndarray):
        """Add a single knowledge entry embedding."""
        vec = vector.astype("float32").reshape(1, -1)
        # Normalize (ensure cosine similarity via inner product)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        self.index.add(vec)
        self.id_map[self.next_id] = entry_id
        self.next_id += 1
        self._persist()

    def search(self, query_vector: np.ndarray, topk: int = 10) -> List[Tuple[int, float]]:
        """
        Semantic search. Returns list of (entry_id, cosine_score) sorted descending.
        """
        if self.index.ntotal == 0:
            return []
        qv = query_vector.astype("float32").reshape(1, -1)
        norm = np.linalg.norm(qv)
        if norm > 0:
            qv = qv / norm
        k = min(topk + 4, self.index.ntotal)
        scores, ids = self.index.search(qv, k)
        results = []
        for fid, score in zip(ids[0].tolist(), scores[0].tolist()):
            if fid == -1:
                continue
            entry_id = self.id_map.get(int(fid))
            if entry_id is not None:
                results.append((entry_id, float(score)))
        return results[:topk]

    def rebuild(self, entries: List[Dict], embed_fn):
        """
        Full index rebuild from a list of {'id': int, 'content': str} dicts.
        Called on first startup when index is empty but DB has entries.
        """
        logger.info(f"[VectorStore] Rebuilding index for {len(entries)} entries...")
        self.index = faiss.IndexFlatIP(self.embed_dim)
        self.id_map = {}
        self.next_id = 0

        for i, entry in enumerate(entries):
            try:
                vec = embed_fn(entry["content"])
                self.add(entry["id"], vec)
            except Exception as e:
                logger.warning(f"[VectorStore] Failed to embed entry {entry['id']}: {e}")

            if (i + 1) % 20 == 0:
                logger.info(f"[VectorStore] Indexed {i + 1}/{len(entries)}...")

        logger.info(f"[VectorStore] Rebuild complete. {self.index.ntotal} entries in index.")

    @property
    def total(self) -> int:
        return self.index.ntotal
