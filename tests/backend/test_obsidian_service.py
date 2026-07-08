from backend.services.obsidian_service import ObsidianService


def test_parse_markdown_extracts_frontmatter_title_and_hash():
    service = ObsidianService()

    parsed = service.parse_markdown(
        "AI-Trading/삼성전자.md",
        "---\ntags: [ai-trading, stock]\nsymbol: '005930'\nmarket: KR\n---\n# 삼성전자\nHBM 체크",
    )

    assert parsed["file_path"] == "AI-Trading/삼성전자.md"
    assert parsed["title"] == "삼성전자"
    assert parsed["frontmatter"]["symbol"] == "005930"
    assert parsed["frontmatter"]["market"] == "KR"
    assert parsed["content"] == "# 삼성전자\nHBM 체크"
    assert len(parsed["content_hash"]) == 64


def test_parse_markdown_falls_back_to_file_name_title():
    service = ObsidianService()

    parsed = service.parse_markdown("AI-Trading/손실회고.md", "## 제목 아님\n내용")

    assert parsed["title"] == "손실회고"
    assert parsed["frontmatter"] == {}
