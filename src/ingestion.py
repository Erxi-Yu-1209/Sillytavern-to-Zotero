import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .field_notes_reader import FieldNotesReader
from .qdrant_service import QdrantService
from .settings import (
    ACADEMIC_COLLECTION_NAME,
    ACADEMIC_QDRANT_EMBED_MODEL,
    FIELD_NOTES_COLLECTION_NAME,
    FIELD_NOTES_QDRANT_EMBED_MODEL,
)
from .zotero_reader import ZoteroReader

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DB_PATH = Path("ingestion_state.db")


class SQLiteCheckpoint:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS processed_chunks (chunk_id TEXT PRIMARY KEY, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sync_state (sync_type TEXT PRIMARY KEY, last_sync_time DATETIME)"
        )
        self._conn.commit()

    def is_processed(self, chunk_id: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM processed_chunks WHERE chunk_id=?", (chunk_id,))
        return bool(cur.fetchone())

    def mark_as_processed(self, chunk_id: str):
        self._conn.execute("INSERT OR IGNORE INTO processed_chunks (chunk_id) VALUES (?)", (chunk_id,))
        self._conn.commit()

    def get_last_sync_time(self, sync_type: str) -> datetime:
        cur = self._conn.execute("SELECT last_sync_time FROM sync_state WHERE sync_type=?", (sync_type,))
        row = cur.fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0])
        return datetime.min

    def set_last_sync_time(self, sync_type: str, sync_time: datetime | None = None):
        effective_time = sync_time or datetime.now()
        self._conn.execute(
            "INSERT OR REPLACE INTO sync_state (sync_type, last_sync_time) VALUES (?, ?)",
            (sync_type, effective_time.isoformat()),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()


async def _upsert_chunks(
    collection_name: str,
    embedding_model: str,
    chunks: Iterable[Dict[str, Any]],
    checkpoint: SQLiteCheckpoint,
) -> Dict[str, int]:
    chunk_list = list(chunks)
    pending = [chunk for chunk in chunk_list if not checkpoint.is_processed(chunk["id"])]
    if not pending:
        return {"processed": 0, "skipped": len(chunk_list)}

    qdrant = QdrantService()
    inserted = await asyncio.to_thread(
        qdrant.upsert_chunks,
        collection_name,
        embedding_model,
        pending,
    )

    for chunk in pending:
        checkpoint.mark_as_processed(chunk["id"])

    return {"processed": inserted, "skipped": len(chunk_list) - inserted}


async def ingest_from_zotero(full_sync: bool = False):
    zotero = None
    checkpoint = SQLiteCheckpoint()
    try:
        zotero = ZoteroReader()
        last_sync = checkpoint.get_last_sync_time("zotero")
        items = zotero.get_all_items_in_scope() if full_sync else zotero.get_new_items_since(last_sync)

        all_chunks: List[Dict[str, Any]] = []
        for item in items:
            item_chunks = zotero.extract_pdf_chunks(item["itemID"])
            for chunk in item_chunks:
                chunk["title"] = item["title"]
                chunk["dateAdded"] = item.get("dateAdded")
                chunk["dateModified"] = item.get("dateModified")
            all_chunks.extend(item_chunks)

        result = await _upsert_chunks(
            collection_name=ACADEMIC_COLLECTION_NAME,
            embedding_model=ACADEMIC_QDRANT_EMBED_MODEL,
            chunks=all_chunks,
            checkpoint=checkpoint,
        )
        checkpoint.set_last_sync_time("zotero")

        return {
            "status": "success",
            "data_source": "zotero_academic_papers",
            "items": len(items),
            "chunks": len(all_chunks),
            **result,
        }
    except Exception as exc:
        logger.exception("Error during Zotero ingestion: %s", exc)
        return {"status": "error", "message": str(exc)}
    finally:
        if zotero:
            zotero.close()
        checkpoint.close()


async def ingest_from_field_notes(full_sync: bool = False):
    checkpoint = SQLiteCheckpoint()
    try:
        reader = FieldNotesReader()
        last_sync = checkpoint.get_last_sync_time("field_notes")
        note_paths = reader.get_all_notes() if full_sync else reader.get_new_notes_since(last_sync)

        all_chunks: List[Dict[str, Any]] = []
        for note_path in note_paths:
            all_chunks.extend(reader.extract_note_chunks(note_path))

        result = await _upsert_chunks(
            collection_name=FIELD_NOTES_COLLECTION_NAME,
            embedding_model=FIELD_NOTES_QDRANT_EMBED_MODEL,
            chunks=all_chunks,
            checkpoint=checkpoint,
        )
        checkpoint.set_last_sync_time("field_notes")

        return {
            "status": "success",
            "data_source": "field_notes",
            "notes": len(note_paths),
            "chunks": len(all_chunks),
            **result,
        }
    except Exception as exc:
        logger.exception("Error during field-note ingestion: %s", exc)
        return {"status": "error", "message": str(exc)}
    finally:
        checkpoint.close()
