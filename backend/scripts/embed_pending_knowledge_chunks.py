from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from backend.services.embedding_service import EmbeddingService  # noqa: E402


def main() -> int:
    batch_size = int(os.getenv("KNOWLEDGE_EMBEDDING_BATCH_SIZE", "100"))
    source_type = os.getenv("KNOWLEDGE_EMBEDDING_SOURCE_TYPE", "DISCLOSURE").strip() or None
    service = EmbeddingService()
    total = 0

    while True:
        saved = service.embed_pending_chunks(limit=batch_size, source_type=source_type)
        if saved == 0:
            break
        total += saved
        print(f"[embedded] batch={saved}, total={total}")

    print(f"[done] embedded={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
