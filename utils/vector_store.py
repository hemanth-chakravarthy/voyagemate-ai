import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from langchain_qdrant import QdrantVectorStore
from langchain_huggingface import HuggingFaceEmbeddings

from utils.config_loader import load_config


load_dotenv()


class VectorStore:
    def __init__(self) -> None:
        config = load_config()
        vs_cfg = config.get("vector_store", {})

        self.qdrant_url = vs_cfg.get("qdrant_url", "http://localhost:6333")
        # Ensure we get the actual value if it's an env var or a placeholder
        raw_api_key = vs_cfg.get("qdrant_api_key", "")
        if raw_api_key and raw_api_key.startswith("${") and raw_api_key.endswith("}"):
            env_var = raw_api_key[2:-1]
            self.qdrant_api_key = os.environ.get(env_var)
        else:
            self.qdrant_api_key = os.environ.get("QDRANT_API_KEY") or raw_api_key
            
        self.collection_name = vs_cfg.get("collection_name", "voyagemate_memory")


        self.embeddings_model = vs_cfg.get("embeddings_model", "all-MiniLM-L6-v2")

        self.embeddings = HuggingFaceEmbeddings(model_name=self.embeddings_model)
        self.client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)

        self._ensure_collection()
        self.vector_db = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
        )

    def _ensure_collection(self) -> None:
        try:
            self.client.get_collection(self.collection_name)
            return
        except Exception:
            pass
        dim = len(self.embeddings.embed_query("test"))
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    def save_trip(self, plan_text: str, metadata: Dict[str, Any]) -> Optional[str]:
        if not plan_text:
            return None
        if "timestamp" not in metadata:
            metadata["timestamp"] = datetime.utcnow().strftime("%Y-%m-%d")
        ids = self.vector_db.add_texts(texts=[plan_text], metadatas=[metadata])
        if ids:
            return str(ids[0])
        return None

    def get_similar_trips(self, query: str, k: int = 3):
        if not query:
            return []
        return self.vector_db.similarity_search(query, k=k)

    def save_feedback(self, feedback_text: str, metadata: Dict[str, Any]) -> Optional[str]:
        if not feedback_text:
            return None
        if "timestamp" not in metadata:
            metadata["timestamp"] = datetime.utcnow().strftime("%Y-%m-%d")
        ids = self.vector_db.add_texts(texts=[feedback_text], metadatas=[metadata])
        if ids:
            return str(ids[0])
        return None
