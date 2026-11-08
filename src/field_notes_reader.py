import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .settings import FIELD_NOTES_PATH

logger = logging.getLogger(__name__)


class FieldNotesReader:
    def __init__(self, notes_path: Path | None = None):
        self.notes_path = Path(notes_path or FIELD_NOTES_PATH)
        if not self.notes_path.exists():
            raise FileNotFoundError(f"Field notes directory not found: {self.notes_path}")

    def get_all_notes(self) -> List[Path]:
        return sorted(self.notes_path.rglob("*.md"))

    def get_new_notes_since(self, last_sync_time: datetime) -> List[Path]:
        notes = []
        for path in self.get_all_notes():
            modified_at = datetime.fromtimestamp(path.stat().st_mtime)
            if modified_at > last_sync_time:
                notes.append(path)
        return notes

    def extract_note_chunks(self, note_path: Path, chunk_size: int = 800, overlap: int = 120) -> List[Dict[str, Any]]:
        raw_text = note_path.read_text(encoding="utf-8")
        note_title = self._extract_title(raw_text, note_path.stem)
        relative_path = str(note_path.relative_to(self.notes_path))
        modified_at = datetime.fromtimestamp(note_path.stat().st_mtime).isoformat()

        sections = self._split_sections(raw_text, note_title)
        chunks: List[Dict[str, Any]] = []

        file_hash = hashlib.md5(relative_path.encode("utf-8")).hexdigest()[:8]
        for section_index, section in enumerate(sections):
            section_chunks = self._chunk_text(section["content"], chunk_size=chunk_size, overlap=overlap)
            for chunk_index, chunk_text in enumerate(section_chunks):
                chunks.append(
                    {
                        "id": f"field-note-{file_hash}-{section_index}-{chunk_index}",
                        "text": chunk_text,
                        "source": "field_notes",
                        "note_title": note_title,
                        "section_title": section["heading"],
                        "note_path": relative_path,
                        "modified_at": modified_at,
                    }
                )

        logger.info("Extracted %s chunks from %s", len(chunks), relative_path)
        return chunks

    @staticmethod
    def _extract_title(text: str, fallback: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return fallback

    @staticmethod
    def _split_sections(text: str, default_title: str) -> List[Dict[str, str]]:
        sections: List[Dict[str, str]] = []
        current_heading = default_title
        current_lines: List[str] = []

        for line in text.splitlines():
            if re.match(r"^#{1,6}\s+", line.strip()):
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        sections.append({"heading": current_heading, "content": content})
                current_heading = line.strip().lstrip("#").strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append({"heading": current_heading, "content": content})

        if not sections:
            stripped = text.strip()
            if stripped:
                sections.append({"heading": default_title, "content": stripped})

        return sections

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
        normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not normalized:
            return []

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
        chunks: List[str] = []
        current = ""

        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= chunk_size:
                current = candidate
                continue

            if current:
                chunks.append(current)

            if len(paragraph) <= chunk_size:
                current = paragraph
                continue

            start = 0
            step = max(chunk_size - overlap, 1)
            while start < len(paragraph):
                chunks.append(paragraph[start:start + chunk_size].strip())
                start += step
            current = ""

        if current:
            chunks.append(current)

        return chunks
