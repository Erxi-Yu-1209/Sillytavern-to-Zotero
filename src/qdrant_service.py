import uuid
from typing import Any, Dict, Iterable, List

from qdrant_client import QdrantClient
from qdrant_client.http import models

from .settings import QDRANT_API_KEY, QDRANT_URL


class QdrantService:
    def __init__(self, url: str = QDRANT_URL, api_key: str | None = QDRANT_API_KEY):
        self.client = QdrantClient(url=url, api_key=api_key)

    def ensure_collection(self, collection_name: str, embedding_model: str) -> None:
        if self.client.collection_exists(collection_name):
            return

        try:
            vector_size = self.client.get_embedding_size(embedding_model)
        except ImportError as exc:
            raise RuntimeError(
                "FastEmbed is not installed. Re-run `pip install -r requirements.txt` to install qdrant-client[fastembed]."
            ) from exc
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )

    def upsert_chunks(
        self,
        collection_name: str,
        embedding_model: str,
        chunks: Iterable[Dict[str, Any]],
        batch_size: int = 64,
    ) -> int:
        chunk_list = list(chunks)
        if not chunk_list:
            return 0

        self.ensure_collection(collection_name, embedding_model)

        for index in range(0, len(chunk_list), batch_size):
            batch = chunk_list[index:index + batch_size]
            points = [
                models.PointStruct(
                    id=self._to_point_id(chunk["id"]),
                    vector=models.Document(text=chunk["text"], model=embedding_model),
                    payload=self._build_payload(chunk),
                )
                for chunk in batch
            ]
            self.client.upsert(collection_name=collection_name, points=points, wait=True)

        return len(chunk_list)

    def search(
        self,
        collection_name: str,
        embedding_model: str,
        query_text: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not self.client.collection_exists(collection_name):
            return []

        try:
            response = self.client.query_points(
                collection_name=collection_name,
                query=models.Document(text=query_text, model=embedding_model),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except ImportError as exc:
            raise RuntimeError(
                "FastEmbed is not installed. Re-run `pip install -r requirements.txt` to install qdrant-client[fastembed]."
            ) from exc

        hits: List[Dict[str, Any]] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                {
                    "id": str(point.id),
                    "score": float(point.score or 0.0),
                    "text": payload.get("text", ""),
                    "payload": payload,
                }
            )
        return hits

    @staticmethod
    def _to_point_id(chunk_id: Any) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, str(chunk_id)))

    @staticmethod
    def _build_payload(chunk: Dict[str, Any]) -> Dict[str, Any]:
        payload = {key: value for key, value in chunk.items()}
        payload["chunk_id"] = str(chunk["id"])
        return payload
