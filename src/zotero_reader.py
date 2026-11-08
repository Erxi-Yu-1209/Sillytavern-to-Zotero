import hashlib
import logging
import os
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .settings import BASE_DIR

logger = logging.getLogger(__name__)


class ZoteroReader:
    def __init__(self):
        self.db_path = Path(os.getenv("ZOTERO_DB_PATH"))
        self.storage_path = Path(os.getenv("ZOTERO_STORAGE_PATH"))

        if not self.db_path.exists():
            raise FileNotFoundError(f"Zotero database not found at {self.db_path}")

        db_uri = f"file:{self.db_path.as_posix()}?mode=ro"
        self.conn = sqlite3.connect(db_uri, uri=True)
        self.conn.row_factory = sqlite3.Row

        categories_str = os.getenv("ZOTERO_INCLUDE_CATEGORIES", "")
        self.target_categories = [c.strip() for c in categories_str.split(",") if c.strip()]

        logger.info("Zotero reader initialized. Target categories: %s", self.target_categories)

    def _resolve_root_names(self, root_names: List[str] | None = None) -> List[str]:
        effective_roots = root_names if root_names is not None else self.target_categories
        effective_roots = [name.strip() for name in effective_roots if name and name.strip()]
        if not effective_roots:
            logger.warning("No target categories configured")
            return []
        return effective_roots

    def get_collection_scope(self, root_names: List[str] | None = None) -> List[Dict[str, Any]]:
        effective_roots = self._resolve_root_names(root_names)
        if not effective_roots:
            return []

        placeholders = ",".join("?" * len(effective_roots))
        query = f"""
        WITH RECURSIVE subcollections AS (
            SELECT
                collectionID,
                collectionName,
                parentCollectionID,
                collectionName AS rootCollectionName,
                0 AS depth
            FROM collections
            WHERE collectionName IN ({placeholders})

            UNION ALL

            SELECT
                c.collectionID,
                c.collectionName,
                c.parentCollectionID,
                s.rootCollectionName,
                s.depth + 1
            FROM collections c
            JOIN subcollections s ON c.parentCollectionID = s.collectionID
        )
        SELECT DISTINCT
            collectionID,
            collectionName,
            parentCollectionID,
            rootCollectionName,
            depth
        FROM subcollections
        ORDER BY rootCollectionName, depth, collectionName
        """

        rows = self.conn.execute(query, effective_roots).fetchall()
        scope = [dict(row) for row in rows]

        logger.info(
            "Expanded Zotero collection scope from roots %s to %s collections",
            effective_roots,
            len(scope),
        )
        return scope

    def get_collection_ids(self, root_names: List[str] | None = None) -> Dict[str, List[int]]:
        scope = self.get_collection_scope(root_names=root_names)
        result: Dict[str, List[int]] = {}
        for row in scope:
            result.setdefault(row["rootCollectionName"], []).append(row["collectionID"])

        logger.info("Expanded collection IDs by root: %s", result)
        return result

    def get_scope_debug_report(self, root_names: List[str] | None = None) -> Dict[str, Any]:
        scope = self.get_collection_scope(root_names=root_names)
        if not scope:
            return {
                "configured_roots": self._resolve_root_names(root_names),
                "roots": [],
                "total_collections": 0,
            }

        collection_ids = [row["collectionID"] for row in scope]
        placeholders = ",".join("?" * len(collection_ids))

        direct_item_counts = {
            row["collectionID"]: row["direct_items"]
            for row in self.conn.execute(
                f"""
                SELECT collectionID, COUNT(*) AS direct_items
                FROM collectionItems
                WHERE collectionID IN ({placeholders})
                GROUP BY collectionID
                """,
                collection_ids,
            ).fetchall()
        }

        root_unique_items = {
            row["rootCollectionName"]: row["unique_items"]
            for row in self.conn.execute(
                f"""
                WITH scope AS (
                    SELECT rootCollectionName, collectionID
                    FROM (
                        WITH RECURSIVE subcollections AS (
                            SELECT
                                collectionID,
                                collectionName,
                                parentCollectionID,
                                collectionName AS rootCollectionName,
                                0 AS depth
                            FROM collections
                            WHERE collectionName IN ({",".join("?" * len(self._resolve_root_names(root_names)))})

                            UNION ALL

                            SELECT
                                c.collectionID,
                                c.collectionName,
                                c.parentCollectionID,
                                s.rootCollectionName,
                                s.depth + 1
                            FROM collections c
                            JOIN subcollections s ON c.parentCollectionID = s.collectionID
                        )
                        SELECT rootCollectionName, collectionID FROM subcollections
                    )
                )
                SELECT scope.rootCollectionName, COUNT(DISTINCT ci.itemID) AS unique_items
                FROM scope
                LEFT JOIN collectionItems ci ON ci.collectionID = scope.collectionID
                GROUP BY scope.rootCollectionName
                """,
                self._resolve_root_names(root_names),
            ).fetchall()
        }

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in scope:
            grouped[row["rootCollectionName"]].append(
                {
                    **row,
                    "direct_items": int(direct_item_counts.get(row["collectionID"], 0)),
                }
            )

        roots = []
        for root_name, collections in grouped.items():
            roots.append(
                {
                    "root_name": root_name,
                    "total_collections": len(collections),
                    "unique_items_in_scope": int(root_unique_items.get(root_name, 0)),
                    "collections": collections,
                }
            )

        roots.sort(key=lambda item: item["root_name"])
        return {
            "configured_roots": self._resolve_root_names(root_names),
            "roots": roots,
            "total_collections": len(scope),
        }

    def get_items_in_collections(self, collection_ids: List[int]) -> List[Dict[str, Any]]:
        if not collection_ids:
            logger.warning("No collections found")
            return []

        placeholders = ",".join("?" * len(collection_ids))
        query = f"""
        SELECT DISTINCT it.itemID, it.libraryID, idv.value as title, it.dateAdded
        FROM items it
        LEFT JOIN collectionItems ci ON it.itemID = ci.itemID
        LEFT JOIN itemData id ON it.itemID = id.itemID AND id.fieldID = 1
        LEFT JOIN itemDataValues idv ON id.valueID = idv.valueID
        WHERE ci.collectionID IN ({placeholders})
        ORDER BY it.dateAdded DESC
        """

        cur = self.conn.execute(query, collection_ids)
        items = []
        for row in cur:
            item_id, lib_id, title, date_added = row
            items.append(
                {
                    "itemID": item_id,
                    "libraryID": lib_id,
                    "title": title or "Untitled",
                    "dateAdded": date_added,
                }
            )

        logger.info("Found %s items in target collections", len(items))
        return items

    def get_all_items_in_scope(self) -> List[Dict[str, Any]]:
        collection_ids = list({cid for ids in self.get_collection_ids().values() for cid in ids})
        return self.get_items_in_collections(collection_ids)

    def extract_pdf_chunks(self, item_id: int, chunk_size: int = 500) -> List[Dict[str, Any]]:
        try:
            import PyPDF2
        except ImportError:
            logger.error("PyPDF2 not installed. Install with: pip install PyPDF2")
            return []

        cur = self.conn.execute(
            """
            SELECT path FROM itemAttachments
            WHERE parentItemID = ? AND contentType = 'application/pdf'
            """,
            (item_id,),
        )

        pdf_paths = []
        for row in cur:
            path = row[0]
            if path.startswith("storage:"):
                filename = path[8:]
                for hash_dir in self.storage_path.iterdir():
                    if hash_dir.is_dir():
                        potential_path = hash_dir / filename
                        if potential_path.exists():
                            pdf_paths.append(potential_path)
                            break

        if not pdf_paths:
            logger.debug("No PDF files found for item %s", item_id)
            return []

        chunks = []
        for pdf_path in pdf_paths:
            try:
                logger.info("Extracting text from %s", pdf_path)
                with open(pdf_path, "rb") as handle:
                    reader = PyPDF2.PdfReader(handle)
                    text = ""
                    for page_num, page in enumerate(reader.pages):
                        try:
                            text += page.extract_text()
                        except Exception as exc:
                            logger.warning("Error extracting page %s from %s: %s", page_num, pdf_path, exc)

                    if not text.strip():
                        logger.warning("No text extracted from %s", pdf_path)
                        continue

                    for i in range(0, len(text), chunk_size):
                        chunk = text[i:i + chunk_size].strip()
                        if chunk:
                            pdf_hash = hashlib.md5(pdf_path.name.encode()).hexdigest()[:8]
                            chunk_index = i // chunk_size
                            chunks.append(
                                {
                                    "id": f"zotero-{item_id}-{pdf_hash}-{chunk_index}",
                                    "text": chunk,
                                    "source": "zotero",
                                    "item_id": item_id,
                                    "pdf": pdf_path.name,
                                }
                            )
            except Exception as exc:
                logger.error("Error reading %s: %s", pdf_path, exc)

        logger.info("Extracted %s chunks from item %s", len(chunks), item_id)
        return chunks

    def get_new_items_since(self, last_sync_time: datetime) -> List[Dict[str, Any]]:
        collection_ids = list({cid for ids in self.get_collection_ids().values() for cid in ids})
        if not collection_ids:
            return []

        placeholders = ",".join("?" * len(collection_ids))
        query = f"""
        SELECT DISTINCT it.itemID, it.libraryID, idv.value as title, it.dateAdded, it.dateModified
        FROM items it
        LEFT JOIN collectionItems ci ON it.itemID = ci.itemID
        LEFT JOIN itemData id ON it.itemID = id.itemID AND id.fieldID = 1
        LEFT JOIN itemDataValues idv ON id.valueID = idv.valueID
        WHERE ci.collectionID IN ({placeholders})
        AND (it.dateAdded > ? OR it.dateModified > ?)
        ORDER BY it.dateModified DESC
        """

        timestamp = last_sync_time.isoformat()
        cur = self.conn.execute(query, collection_ids + [timestamp, timestamp])
        items = []
        for row in cur:
            item_id, lib_id, title, date_added, date_modified = row
            items.append(
                {
                    "itemID": item_id,
                    "libraryID": lib_id,
                    "title": title or "Untitled",
                    "dateAdded": date_added,
                    "dateModified": date_modified,
                }
            )

        logger.info("Found %s new/modified items since %s", len(items), timestamp)
        return items

    def close(self):
        self.conn.close()
