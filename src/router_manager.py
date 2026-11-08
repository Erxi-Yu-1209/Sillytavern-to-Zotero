from dataclasses import dataclass

from .settings import (
    ACADEMIC_COLLECTION_NAME,
    ACADEMIC_QDRANT_EMBED_MODEL,
    FIELD_NOTES_CHAT_MODEL,
    FIELD_NOTES_COLLECTION_NAME,
    FIELD_NOTES_QDRANT_EMBED_MODEL,
    RELAY_MODEL,
)


class SecurityException(Exception):
    pass


@dataclass(frozen=True)
class DataSourceConfig:
    data_source: str
    collection_name: str
    embedding_model: str
    chat_model: str
    system_prompt: str


class RouterManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_data_source_config(self, data_source: str, model: str | None = None) -> DataSourceConfig:
        if data_source == "field_notes":
            return DataSourceConfig(
                data_source=data_source,
                collection_name=FIELD_NOTES_COLLECTION_NAME,
                embedding_model=FIELD_NOTES_QDRANT_EMBED_MODEL,
                chat_model=model or FIELD_NOTES_CHAT_MODEL,
                system_prompt=(
                    "You answer only from retrieved field-note context. "
                    "If the context is insufficient, say so explicitly. "
                    "Do not invent observations that are not supported by the notes."
                ),
            )

        if data_source == "zotero_academic_papers":
            return DataSourceConfig(
                data_source=data_source,
                collection_name=ACADEMIC_COLLECTION_NAME,
                embedding_model=ACADEMIC_QDRANT_EMBED_MODEL,
                chat_model=model or RELAY_MODEL,
                system_prompt=(
                    "You are assisting with academic literature analysis. "
                    "Use only the retrieved passages as evidence, and state uncertainty when the evidence is incomplete."
                ),
            )

        raise SecurityException("Unknown data source. Request blocked.")
