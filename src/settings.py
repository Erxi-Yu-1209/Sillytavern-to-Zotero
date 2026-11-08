import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - allows lightweight debug usage before full deps are installed
    def load_dotenv(*args, **kwargs):
        return False

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "apiconfig.env"


def _load_env_fallback(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


loaded = load_dotenv(CONFIG_PATH)
if not loaded:
    _load_env_fallback(CONFIG_PATH)


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
LITELLM_HEALTH_URL = os.getenv("LITELLM_HEALTH_URL", "http://127.0.0.1:4000/health")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "sk-1234")

RELAY_API_BASE = os.getenv("RELAY_API_BASE", "https://api.x.ai/v1")
RELAY_MODEL = os.getenv("RELAY_MODEL", "grok-4.20-0309-reasoning")

FIELD_NOTES_CHAT_MODEL = os.getenv(
    "FIELD_NOTES_CHAT_MODEL",
    os.getenv("LOCAL_LLAMA_MODEL", "llama-3-8b-local"),
)

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
ACADEMIC_COLLECTION_NAME = os.getenv("ACADEMIC_COLLECTION_NAME", "academic_chunks")
FIELD_NOTES_COLLECTION_NAME = os.getenv("FIELD_NOTES_COLLECTION_NAME", "field_notes_chunks")
ACADEMIC_QDRANT_EMBED_MODEL = os.getenv(
    "ACADEMIC_QDRANT_EMBED_MODEL",
    os.getenv("ACADEMIC_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
)
FIELD_NOTES_QDRANT_EMBED_MODEL = os.getenv(
    "FIELD_NOTES_QDRANT_EMBED_MODEL",
    "intfloat/multilingual-e5-small",
)
FIELD_NOTES_PATH = Path(os.getenv("FIELD_NOTES_PATH", str(BASE_DIR / "field_notes")))
RETRIEVAL_TOP_K = _get_int("RETRIEVAL_TOP_K", 5)
ZOTERO_AUTO_SYNC_ENABLED = os.getenv("ZOTERO_AUTO_SYNC_ENABLED", "false").lower() == "true"
ZOTERO_SYNC_INTERVAL_HOURS = _get_int("ZOTERO_SYNC_INTERVAL_HOURS", 24)
