from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(name: str) -> str:
    """프롬프트 파일을 읽어 문자열로 반환합니다."""
    path = PROMPT_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def build_system_prompt() -> str:
    """챗봇 기본 시스템 지시문을 조합합니다."""
    return "\n\n".join(
        item for item in [
            load_prompt("system_role.md"),
            load_prompt("trading_rules.md"),
        ] if item
    )
