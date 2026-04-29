import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from langchain_qdrant import QdrantVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from utils.config_loader import load_config


os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
load_dotenv()


class RAGStore:
    def __init__(self) -> None:
        config = load_config()
        vs_cfg = config.get("vector_store", {})
        rag_cfg = config.get("rag", {})
        self.qdrant_url = vs_cfg.get("qdrant_url", "http://localhost:6333")
        self.qdrant_api_key = os.environ.get("QDRANT_API_KEY") or vs_cfg.get("qdrant_api_key")
        self.collection_name = rag_cfg.get("knowledge_collection", "voyagemate_knowledge")
        self.embeddings_model = vs_cfg.get("embeddings_model", "all-MiniLM-L6-v2")
        self.chunk_size = int(rag_cfg.get("chunk_size", 800))
        self.chunk_overlap = int(rag_cfg.get("chunk_overlap", 120))

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

    def ingest_texts(self, texts: List[str], metadata: Optional[List[Dict[str, Any]]] = None) -> int:
        if not texts:
            return 0
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        docs: List[Document] = []
        for idx, t in enumerate(texts):
            if not t:
                continue
            chunks = splitter.split_text(t)
            meta = metadata[idx] if metadata and idx < len(metadata) else {}
            for chunk in chunks:
                docs.append(Document(page_content=chunk, metadata=meta))
        if not docs:
            return 0
        self.vector_db.add_documents(docs)
        return len(docs)

    def search(self, query: str, k: int = 4):
        if not query:
            return []
        return self.vector_db.similarity_search(query, k=k)
