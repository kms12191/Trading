from backend.services.disclosure_knowledge_index_service import (
    DisclosureSummaryDocument,
    build_disclosure_chunk_metadata,
    build_disclosure_summary_text,
)


def test_build_disclosure_summary_text_excludes_raw_original_text():
    document = DisclosureSummaryDocument(
        rcept_no="20260709000001",
        stock_code="000660",
        corp_name="SK하이닉스",
        report_name="주요사항보고서",
        rcept_dt="20260709",
        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260709000001",
        category="수주·공급계약",
        sentiment_label="호재",
        sentiment_message="수주 공시로 긍정적으로 해석될 수 있습니다.",
        headline="대규모 공급계약 체결 공시입니다.",
        plain_summary="계약 규모와 기간을 함께 확인해야 합니다.",
        key_points=["계약상대: ABC", "계약기간: 2026-07-09"],
        risk_points=["실제 매출 반영 시점 확인"],
        check_items=["계약 해지 조건 확인"],
        metrics=["계약금액: 1,000억원"],
    )

    text = build_disclosure_summary_text(document)

    assert "대규모 공급계약 체결 공시입니다." in text
    assert "계약금액: 1,000억원" in text
    assert "원문" not in text
    assert "raw_payload" not in text


def test_build_disclosure_chunk_metadata_keeps_source_fields():
    document = DisclosureSummaryDocument(
        rcept_no="20260709000001",
        stock_code="000660",
        corp_name="SK하이닉스",
        report_name="주요사항보고서",
        rcept_dt="20260709",
        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260709000001",
        category="수주·공급계약",
        sentiment_label="호재",
        sentiment_message="수주 공시입니다.",
        headline="공급계약 체결",
        plain_summary="요약",
        key_points=[],
        risk_points=[],
        check_items=[],
        metrics=[],
    )

    metadata = build_disclosure_chunk_metadata(document)

    assert metadata["source_type"] == "DISCLOSURE"
    assert metadata["rcept_no"] == "20260709000001"
    assert metadata["symbol"] == "000660"
    assert metadata["sentiment"] == "호재"
