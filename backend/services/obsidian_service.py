import hashlib
import re
from typing import Any

import yaml


class ObsidianService:
    """Obsidian Markdown 노트를 앱 저장 포맷으로 정규화합니다."""

    def parse_markdown(self, file_path: str, content: str) -> dict[str, Any]:
        raw_content = str(content or "").replace("\r\n", "\n")
        frontmatter, body = self._extract_frontmatter(raw_content)
        normalized_path = str(file_path or "").strip()
        return {
            "file_path": normalized_path,
            "title": self._extract_title(body, normalized_path),
            "content": body.strip(),
            "content_hash": hashlib.sha256(raw_content.encode("utf-8")).hexdigest(),
            "frontmatter": frontmatter,
        }

    def _extract_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        if not content.startswith("---\n"):
            return {}, content

        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, flags=re.DOTALL)
        if not match:
            return {}, content

        loaded = yaml.safe_load(match.group(1)) or {}
        frontmatter = loaded if isinstance(loaded, dict) else {}
        return frontmatter, match.group(2)

    def _extract_title(self, body: str, file_path: str) -> str:
        for line in str(body or "").splitlines():
            if line.startswith("# "):
                return line[2:].strip() or self._fallback_title(file_path)
        return self._fallback_title(file_path)

    def _fallback_title(self, file_path: str) -> str:
        file_name = str(file_path or "Obsidian Note").rstrip("/").split("/")[-1]
        return re.sub(r"\.md$", "", file_name, flags=re.IGNORECASE) or "Obsidian Note"
