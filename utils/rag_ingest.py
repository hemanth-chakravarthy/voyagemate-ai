import os
from typing import List

from utils.rag_store import RAGStore


def _read_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def ingest_directory(directory: str) -> int:
    texts: List[str] = []
    metadata = []
    for root, _, files in os.walk(directory):
        for name in files:
            if not name.lower().endswith(".txt"):
                continue
            path = os.path.join(root, name)
            texts.append(_read_txt(path))
            metadata.append({"source": path})
    if not texts:
        return 0
    store = RAGStore()
    return store.ingest_texts(texts, metadata)


if __name__ == "__main__":
    import sys

    target_dir = sys.argv[1] if len(sys.argv) > 1 else "./data/knowledge"
    count = ingest_directory(target_dir)
    print(f"Ingested {count} chunks from {target_dir}")
