import time
import json
import os
from typing import Any, Dict, Optional
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from langchain_huggingface import HuggingFaceEmbeddings

from utils.config_loader import load_config

class SemanticCache:
    def __init__(self) -> None:
        config = load_config()
        vs_cfg = config.get("vector_store", {})
        perf_cfg = config.get("performance", {})
        cache_cfg = perf_cfg.get("semantic_cache", {})

        self.enabled = cache_cfg.get("enabled", True)
        self.qdrant_url = vs_cfg.get("qdrant_url", "http://localhost:6333")
        self.collection_name = cache_cfg.get("collection_name", "voyagemate_semantic_cache")
        self.embeddings_model = vs_cfg.get("embeddings_model", "all-MiniLM-L6-v2")
        self.threshold = cache_cfg.get("threshold", 0.85)
        self.min_query_length = cache_cfg.get("min_query_length", 10)

        self.embeddings = HuggingFaceEmbeddings(model_name=self.embeddings_model)
        self.client = QdrantClient(url=self.qdrant_url)
        
        if self.enabled:
            self._ensure_collection()
            from langchain_qdrant import QdrantVectorStore
            self.vector_db = QdrantVectorStore(
                client=self.client,
                collection_name=self.collection_name,
                embedding=self.embeddings,
            )

    def _ensure_collection(self) -> None:
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            dim = len(self.embeddings.embed_query("test"))
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or len(query) < self.min_query_length:
            return None

        # Use similarity_search_with_score from LangChain
        try:
            search_results = self.vector_db.similarity_search_with_score(query, k=1)
            if search_results:
                doc, score = search_results[0]
                # LangChain Qdrant returns similarity score (higher is better)
                if score >= self.threshold:
                    print(f"DEBUG: Semantic cache hit with score {score}")
                    # Response is stored in metadata
                    return doc.metadata.get("response")
        except Exception as e:
            print(f"Warning: Semantic cache get failed: {e}")
        
        return None

    def set(self, query: str, response: Dict[str, Any]) -> None:
        if not self.enabled:
            return

        try:
            # Store response in metadata
            self.vector_db.add_texts(
                texts=[query],
                metadatas=[{"response": response, "timestamp": datetime.utcnow().isoformat()}]
            )
        except Exception as e:
            print(f"Warning: Semantic cache set failed: {e}")

