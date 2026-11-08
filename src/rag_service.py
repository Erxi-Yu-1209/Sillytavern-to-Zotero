from typing import Any, Dict, List

from .litellm_gateway import LiteLLMGateway
from .qdrant_service import QdrantService
from .router_manager import RouterManager
from .settings import RETRIEVAL_TOP_K


class RAGService:
    def __init__(self):
        self.router_manager = RouterManager()
        self.vector_store = QdrantService()
        self.chat_gateway = LiteLLMGateway()

    def answer_query(
        self,
        data_source: str,
        task_type: str,
        query: str,
        model: str | None = None,
        top_k: int | None = None,
    ) -> Dict[str, Any]:
        config = self.router_manager.get_data_source_config(data_source, model=model)
        effective_top_k = top_k or RETRIEVAL_TOP_K

        hits = self.vector_store.search(
            collection_name=config.collection_name,
            embedding_model=config.embedding_model,
            query_text=query,
            limit=effective_top_k,
        )

        if not hits:
            return {
                "status": "no_results",
                "data_source": data_source,
                "collection": config.collection_name,
                "model": config.chat_model,
                "answer": "No relevant context was found in Qdrant for this query.",
                "retrieved_chunks": [],
            }

        messages = self._build_messages(
            system_prompt=config.system_prompt,
            task_type=task_type,
            query=query,
            hits=hits,
        )
        answer = self.chat_gateway.complete(model=config.chat_model, messages=messages)

        return {
            "status": "success",
            "data_source": data_source,
            "task_type": task_type,
            "collection": config.collection_name,
            "model": config.chat_model,
            "embedding_model": config.embedding_model,
            "answer": answer,
            "retrieved_chunks": hits,
        }

    def retrieve_query(
        self,
        data_source: str,
        query: str,
        top_k: int | None = None,
        model: str | None = None,
    ) -> Dict[str, Any]:
        config = self.router_manager.get_data_source_config(data_source, model=model)
        effective_top_k = top_k or RETRIEVAL_TOP_K

        hits = self.vector_store.search(
            collection_name=config.collection_name,
            embedding_model=config.embedding_model,
            query_text=query,
            limit=effective_top_k,
        )

        return {
            "status": "success",
            "data_source": data_source,
            "query": query,
            "top_k": effective_top_k,
            "collection": config.collection_name,
            "embedding_model": config.embedding_model,
            "total_results": len(hits),
            "results": [self._format_retrieve_hit(hit) for hit in hits],
        }

    @staticmethod
    def _build_messages(system_prompt: str, task_type: str, query: str, hits: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        context_blocks = []
        for index, hit in enumerate(hits, start=1):
            payload = hit["payload"]
            label = payload.get("title") or payload.get("note_title") or payload.get("note_path") or payload.get("pdf") or "unknown"
            context_blocks.append(
                "\n".join(
                    [
                        f"[Chunk {index}]",
                        f"label: {label}",
                        f"score: {hit['score']:.4f}",
                        f"text: {hit['text']}",
                    ]
                )
            )

        user_prompt = "\n\n".join(
            [
                f"Task type: {task_type}",
                f"User query: {query}",
                "Retrieved context:",
                "\n\n".join(context_blocks),
                "Answer the query using only the retrieved context. Cite chunk numbers inline when useful.",
            ]
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _format_retrieve_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
        payload = hit.get("payload", {}) or {}
        metadata = {
            key: value
            for key, value in payload.items()
            if key not in {"id", "chunk_id", "text", "source"}
        }

        return {
            "chunk_id": str(payload.get("chunk_id") or hit.get("id") or ""),
            "score": float(hit.get("score") or 0.0),
            "text": payload.get("text", "") or hit.get("text", ""),
            "metadata": metadata,
        }
