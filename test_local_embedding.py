#!/usr/bin/env python
import asyncio
import os
import sys

os.environ['ZOTERO_DB_PATH'] = 'C:/Users/cefts/Zotero/zotero.sqlite'
os.environ['ZOTERO_STORAGE_PATH'] = 'C:/Users/cefts/Zotero/storage'
os.environ['ZOTERO_INCLUDE_CATEGORIES'] = '11masterthesis,12kulanthropology'

print("Starting Zotero sync test with local embeddings...", file=sys.stderr)

from src.ingestion import ingest_from_zotero

async def test():
    result = await ingest_from_zotero(full_sync=True)
    return result

try:
    result = asyncio.run(test())
    print(result)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
