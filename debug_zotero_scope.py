import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.zotero_reader import ZoteroReader


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect expanded Zotero collection scope.")
    parser.add_argument(
        "--roots",
        help="Comma-separated top-level Zotero collection names. Defaults to ZOTERO_INCLUDE_CATEGORIES.",
    )
    args = parser.parse_args()

    root_names = [part.strip() for part in args.roots.split(",")] if args.roots else None

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    reader = ZoteroReader()
    try:
        report = reader.get_scope_debug_report(root_names=root_names)
    finally:
        reader.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
