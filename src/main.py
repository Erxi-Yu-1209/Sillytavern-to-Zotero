import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .ingestion import ingest_from_field_notes, ingest_from_zotero
from .rag_service import RAGService
from .router_manager import SecurityException
from .settings import RETRIEVAL_TOP_K, ZOTERO_AUTO_SYNC_ENABLED, ZOTERO_SYNC_INTERVAL_HOURS
from .zotero_reader import ZoteroReader

logger = logging.getLogger(__name__)

app = FastAPI(title="Academic Intelligent Agent", description="Multimodal academic agent with Qdrant-backed RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_service = RAGService()


class QueryRequest(BaseModel):
    data_source: str
    task_type: str
    query: str
    model: str | None = None
    top_k: int = RETRIEVAL_TOP_K


class RetrieveQueryRequest(BaseModel):
    data_source: str
    query: str
    top_k: int = RETRIEVAL_TOP_K
    model: str | None = None


class SyncRequest(BaseModel):
    full_sync: bool = False


@app.get("/")
def read_root():
    return {"message": "Academic Agent API", "status": "running"}


@app.get("/debug/zotero-scope")
def debug_zotero_scope(roots: str | None = None):
    root_names = [part.strip() for part in roots.split(",")] if roots else None
    reader = ZoteroReader()
    try:
        return reader.get_scope_debug_report(root_names=root_names)
    finally:
        reader.close()


@app.post("/query")
def process_query(request: QueryRequest):
    try:
        return rag_service.answer_query(
            data_source=request.data_source,
            task_type=request.task_type,
            query=request.query,
            model=request.model,
            top_k=request.top_k,
        )
    except SecurityException as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.exception("Error during query: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.post("/query/retrieve")
def retrieve_query(request: RetrieveQueryRequest):
    try:
        return rag_service.retrieve_query(
            data_source=request.data_source,
            query=request.query,
            top_k=request.top_k,
            model=request.model,
        )
    except SecurityException as exc:
        return {
            "status": "error",
            "error": {
                "code": "INVALID_DATA_SOURCE",
                "message": str(exc),
            },
        }
    except Exception as exc:
        logger.exception("Error during retrieval query: %s", exc)
        return {
            "status": "error",
            "error": {
                "code": "RETRIEVAL_FAILED",
                "message": str(exc),
            },
        }


@app.post("/ingest/zotero")
async def trigger_zotero_ingest(request: SyncRequest | None = None):
    full_sync = request.full_sync if request else False
    return await ingest_from_zotero(full_sync=full_sync)


@app.post("/ingest/field-notes")
async def trigger_field_notes_ingest(request: SyncRequest | None = None):
    full_sync = request.full_sync if request else False
    return await ingest_from_field_notes(full_sync=full_sync)


@app.post("/ingest/all")
async def trigger_all_ingest(request: SyncRequest | None = None):
    full_sync = request.full_sync if request else False
    zotero_result = await ingest_from_zotero(full_sync=full_sync)
    field_notes_result = await ingest_from_field_notes(full_sync=full_sync)
    return {
        "status": "success",
        "zotero": zotero_result,
        "field_notes": field_notes_result,
    }


@app.on_event("startup")
async def startup_event():
    if ZOTERO_AUTO_SYNC_ENABLED:
        logger.info("Zotero auto-sync is enabled (interval=%sh)", ZOTERO_SYNC_INTERVAL_HOURS)


@app.on_event("shutdown")
async def shutdown_event():
    return None
