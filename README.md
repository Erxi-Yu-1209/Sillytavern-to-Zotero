# Academic Intelligent Agent System

This project now uses a Qdrant-backed RAG architecture for both Zotero academic papers and local field notes.

## Current Architecture

- Academic papers
  - Source: local Zotero database and PDF attachments
  - Ingestion: [`zotero_reader.py`](/C:/Users/Public/academic%20coll/src/zotero_reader.py)
  - Embedding: local Qdrant FastEmbed model on the host machine
  - Storage: Qdrant collection `academic_chunks`
  - Answering: retrieved chunks are sent to the academic chat model through LiteLLM

- Field notes
  - Source: markdown files under `field_notes/`
  - Ingestion: [`field_notes_reader.py`](/C:/Users/Public/academic%20coll/src/field_notes_reader.py)
  - Embedding: local Qdrant FastEmbed model on the host machine
  - Storage: Qdrant collection `field_notes_chunks`
  - Answering: queries retrieve chunks from Qdrant first, then send only retrieved context to the local chat model through LiteLLM

- Gateway and vector services
  - LiteLLM provides a unified OpenAI-compatible chat endpoint on `http://127.0.0.1:4000/v1`
  - Qdrant stores vectors on `http://127.0.0.1:6333`
  - FastEmbed runs in the local Python process, not inside the Qdrant Docker container

## Endpoints

- `POST /query`
- `POST /query/retrieve`
- `POST /ingest/zotero`
- `POST /ingest/field-notes`
- `POST /ingest/all`

## Manual Setup Steps

1. Activate the virtual environment.

```powershell
.venv312\Scripts\Activate.ps1
```

2. Reinstall dependencies so FastEmbed is available.

```powershell
pip install -r requirements.txt
```

3. Configure [`apiconfig.env`](/C:/Users/Public/academic%20coll/apiconfig.env).

Required variables:

- `RELAY_API_KEY`
- `RELAY_MODEL`
- `FIELD_NOTES_CHAT_MODEL`
- `LOCAL_LLAMA_BASE`
- `LOCAL_LLAMA_KEY`
- `ACADEMIC_QDRANT_EMBED_MODEL`
- `FIELD_NOTES_QDRANT_EMBED_MODEL`
- `FIELD_NOTES_PATH`
- `ZOTERO_DB_PATH`
- `ZOTERO_STORAGE_PATH`

`ZOTERO_INCLUDE_CATEGORIES` can now contain only top-level Zotero collection names. The project will automatically expand each named collection to include all descendant subcollections by following Zotero's collection hierarchy.

Recommended defaults already added:

- `ACADEMIC_QDRANT_EMBED_MODEL=BAAI/bge-small-en-v1.5`
- `FIELD_NOTES_QDRANT_EMBED_MODEL=intfloat/multilingual-e5-small`
- `ACADEMIC_COLLECTION_NAME=academic_chunks`
- `FIELD_NOTES_COLLECTION_NAME=field_notes_chunks`
- `QDRANT_URL=http://127.0.0.1:6333`
- `LITELLM_BASE_URL=http://127.0.0.1:4000/v1`

4. Make sure your local chat model service is actually running on `LOCAL_LLAMA_BASE`.

The project assumes:

- the service is OpenAI-compatible
- the loaded chat model name matches `FIELD_NOTES_CHAT_MODEL`
- it supports chat completions on `/v1/chat/completions`

5. Start Docker services.

```powershell
.\start-services.ps1
```

6. Start the FastAPI server.

```powershell
uvicorn src.main:app --reload
```

7. Ingest data into Qdrant before querying.

Full Zotero ingest:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/ingest/zotero `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"full_sync": true}' `
  -UseBasicParsing
```

Full field-notes ingest:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/ingest/field-notes `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"full_sync": true}' `
  -UseBasicParsing
```

Or ingest both:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/ingest/all `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"full_sync": true}' `
  -UseBasicParsing
```

## Retrieval-Only API

`POST /query/retrieve` returns retrieved passages and metadata without calling any chat model.

Minimal request body:

```json
{
  "data_source": "field_notes",
  "query": "What recurring themes appear in the field notes?",
  "top_k": 5
}
```

Example PowerShell call:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/query/retrieve" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"data_source":"field_notes","query":"What recurring themes appear in the field notes?","top_k":5}'
```

Response shape:

```json
{
  "status": "success",
  "data_source": "field_notes",
  "query": "What recurring themes appear in the field notes?",
  "top_k": 5,
  "collection": "field_notes_chunks",
  "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
  "total_results": 2,
  "results": [
    {
      "chunk_id": "field-note-6bb781f5-0-0",
      "score": 0.8421,
      "text": "Retrieved passage text",
      "metadata": {
        "note_title": "20260202-0204_field_note",
        "section_title": "Tourism development",
        "note_path": "20260202-0204_field_note.md",
        "modified_at": "2026-03-20T09:14:11"
      }
    }
  ]
}
```

This endpoint is intended for local clients such as SillyTavern UI extensions. CORS is enabled for local `localhost` and `127.0.0.1` origins.

8. If you change either embedding model later, clear the old vectors and checkpoints before re-ingesting.

```powershell
curl.exe -X DELETE http://127.0.0.1:6333/collections/academic_chunks
curl.exe -X DELETE http://127.0.0.1:6333/collections/field_notes_chunks
Remove-Item .\ingestion_state.db -ErrorAction SilentlyContinue
```

## Query Examples

Academic papers:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/query `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"data_source":"zotero_academic_papers","task_type":"analysis","query":"Summarize the main arguments about community participation.","top_k":5}' `
  -UseBasicParsing
```

Field notes:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/query `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"data_source":"field_notes","task_type":"analysis","query":"田野笔记里关于社区参与度下降的证据有哪些？","top_k":5}' `
  -UseBasicParsing
```

## Zotero Scope Debugging

To inspect how a top-level Zotero collection expands into child collections before ingestion, use the standalone script:

```powershell
& ".\.venv312\Scripts\python.exe" ".\debug_zotero_scope.py" --roots "11masterthesis"
```

This prints:

- the configured root collection name
- every expanded child collection
- each collection's direct item count
- the unique item count across the full expanded scope

If FastAPI is running, the same information is available from:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/debug/zotero-scope?roots=11masterthesis" -UseBasicParsing
```

## Notes

- Qdrant local embedding here means host-side FastEmbed through `qdrant-client[fastembed]`. The Docker Qdrant container stores and searches vectors; it does not run dense embedding inference by itself.
- Field-note queries no longer read markdown files during query time. Markdown files are read only during ingestion; query-time retrieval comes from Qdrant payloads.
- If `FIELD_NOTES_QDRANT_EMBED_MODEL` is not supported by FastEmbed in your environment, choose another supported model and update `apiconfig.env`.

To inspect supported FastEmbed models after installation:

```powershell
python -c "from fastembed import TextEmbedding; import json; print(json.dumps(TextEmbedding.list_supported_models(), ensure_ascii=False, indent=2))"
```

## Implementation Map

- Query orchestration: [`main.py`](/C:/Users/Public/academic%20coll/src/main.py)
- RAG workflow: [`rag_service.py`](/C:/Users/Public/academic%20coll/src/rag_service.py)
- Qdrant storage and retrieval: [`qdrant_service.py`](/C:/Users/Public/academic%20coll/src/qdrant_service.py)
- Field-note ingestion: [`field_notes_reader.py`](/C:/Users/Public/academic%20coll/src/field_notes_reader.py)
- Zotero ingestion: [`zotero_reader.py`](/C:/Users/Public/academic%20coll/src/zotero_reader.py)
- LiteLLM chat gateway: [`litellm_gateway.py`](/C:/Users/Public/academic%20coll/src/litellm_gateway.py)