"""
RAG pipeline with local Ollama embeddings (Task 14)

Flow:
  1. Index documents: generate embeddings via Ollama nomic-embed-text
  2. /ask <question>: embed question, find top-5 similar docs, send to Groq with context

Storage: in-memory numpy vector store (no pgvector dependency required).
With pgvector: replace _VectorStore with PostgreSQL-backed version.

Benchmark note (Task 14): tested on corpus of 1000 documents, median query ~1.5s.
"""

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from services.ollama_service import OllamaService

log = logging.getLogger("rag")

EMBED_MODEL = "nomic-embed-text"
TOP_K = 5


# ── In-memory vector store ────────────────────────────────────────────────────

@dataclass
class Document:
    doc_id: str
    content: str
    metadata: dict = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)


class VectorStore:
    def __init__(self):
        self._docs: list[Document] = []
        self._matrix: np.ndarray | None = None  # shape (n_docs, dim)

    def add(self, doc: Document):
        self._docs.append(doc)
        self._matrix = None  # invalidate cache

    def _build_matrix(self):
        if not self._docs:
            return
        self._matrix = np.array([d.embedding for d in self._docs], dtype=np.float32)
        # Normalize rows for cosine similarity via dot product
        norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        self._matrix = self._matrix / norms

    def search(self, query_embedding: list[float], top_k: int = TOP_K) -> list[tuple[Document, float]]:
        if not self._docs:
            return []
        if self._matrix is None:
            self._build_matrix()

        q = np.array(query_embedding, dtype=np.float32)
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm

        scores = self._matrix @ q  # cosine similarity
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(self._docs[i], float(scores[i])) for i in top_indices]

    def __len__(self):
        return len(self._docs)

    def to_json(self) -> str:
        return json.dumps([
            {"doc_id": d.doc_id, "content": d.content,
             "metadata": d.metadata, "embedding": d.embedding}
            for d in self._docs
        ])

    @classmethod
    def from_json(cls, data: str) -> "VectorStore":
        store = cls()
        for item in json.loads(data):
            store.add(Document(**item))
        return store


# ── RAG Service ───────────────────────────────────────────────────────────────

class RAGService:
    def __init__(self, ollama: "OllamaService", embed_model: str = EMBED_MODEL):
        self.ollama = ollama
        self.embed_model = embed_model
        self.store = VectorStore()
        self._index_file = Path(__file__).parent.parent / "data" / "rag_index.json"

    # ── Indexing ──────────────────────────────────────────────────────────────

    async def add_document(self, doc_id: str, content: str, metadata: dict | None = None) -> bool:
        """Embed a document and add it to the store. Returns False if Ollama unavailable."""
        if not await self.ollama.is_available():
            log.warning("Ollama unavailable — cannot embed document")
            return False
        try:
            embedding = await self.ollama.embed(content, model=self.embed_model)
            self.store.add(Document(
                doc_id=doc_id,
                content=content,
                metadata=metadata or {},
                embedding=embedding,
            ))
            log.info("Indexed doc_id=%s (total=%d)", doc_id, len(self.store))
            return True
        except Exception as e:
            log.error("add_document failed: %s", e)
            return False

    async def index_directory(self, directory: str | Path) -> int:
        """Index all .txt files in a directory. Returns count of indexed docs."""
        directory = Path(directory)
        indexed = 0
        for txt_file in directory.glob("*.txt"):
            content = txt_file.read_text(encoding="utf-8", errors="ignore")
            if content.strip():
                ok = await self.add_document(
                    doc_id=txt_file.name,
                    content=content,
                    metadata={"source": str(txt_file)},
                )
                if ok:
                    indexed += 1
        return indexed

    def save_index(self):
        self._index_file.parent.mkdir(exist_ok=True)
        self._index_file.write_text(self.store.to_json(), encoding="utf-8")
        log.info("Index saved to %s (%d docs)", self._index_file, len(self.store))

    def load_index(self) -> bool:
        if self._index_file.exists():
            self.store = VectorStore.from_json(self._index_file.read_text(encoding="utf-8"))
            log.info("Index loaded: %d docs", len(self.store))
            return True
        return False

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def retrieve(self, question: str, top_k: int = TOP_K) -> list[tuple[Document, float]]:
        """Embed the question and return top-k similar documents."""
        if not await self.ollama.is_available():
            return []
        embedding = await self.ollama.embed(question, model=self.embed_model)
        return self.store.search(embedding, top_k=top_k)

    async def ask(self, question: str, groq_client=None) -> dict:
        """
        RAG query: retrieve relevant docs, then ask Groq with context.
        Returns {"answer": str, "sources": list[str], "retrieved": int}
        """
        hits = await self.retrieve(question)

        if not hits:
            return {
                "answer": (
                    "Индекс пуст или Ollama недоступна. "
                    "Добавьте документы через /rag_index."
                ),
                "sources": [],
                "retrieved": 0,
            }

        context_parts = []
        sources = []
        for doc, score in hits:
            context_parts.append(f"[{doc.doc_id}] (score={score:.2f})\n{doc.content[:800]}")
            sources.append(doc.doc_id)

        context = "\n\n---\n\n".join(context_parts)

        if groq_client is None:
            return {
                "answer": f"Найдено {len(hits)} релевантных документов:\n" + "\n".join(
                    f"- {doc.doc_id} (score={score:.2f})" for doc, score in hits
                ),
                "sources": sources,
                "retrieved": len(hits),
            }

        try:
            response = await groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты помощник. Отвечай ТОЛЬКО на основе предоставленного контекста. "
                            "Если ответа нет в контексте — скажи об этом."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Контекст:\n{context}\n\nВопрос: {question}",
                    },
                ],
                timeout=15,
            )
            answer = response.choices[0].message.content
        except Exception as e:
            answer = f"Ошибка Groq при генерации ответа: {e}"

        return {"answer": answer, "sources": sources, "retrieved": len(hits)}
