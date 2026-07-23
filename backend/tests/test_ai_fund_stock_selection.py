from backend.services.ai_fund_stock_selection import AiFundStockSelectionService


class _UnavailableReleaseService:
    def is_asset_fresh(self, _asset_key):
        return False, "RELEASE_UNAVAILABLE"


def test_stock_candidates_are_withheld_when_current_release_is_required():
    service = AiFundStockSelectionService(
        release_service=_UnavailableReleaseService(),
        require_release=True,
    )

    result = service.select_candidates(
        {"asset_scope": "ALL", "max_open_positions": 3, "min_signal_confidence": 0.3},
        held_symbols=set(),
    )
    availability = service.get_availability({"asset_scope": "ALL"})

    assert result == []
    assert availability["KR"]["status"] == "RELEASE_UNAVAILABLE"
    assert availability["US"]["status"] == "RELEASE_UNAVAILABLE"


def test_select_candidates_uses_market_scope_and_excludes_held_symbols(monkeypatch):
    service = AiFundStockSelectionService()
    monkeypatch.setattr(
        service,
        "_load_active_predictions",
        lambda market, *_args: [
            {"symbol": "005930", "position": "LONG", "signal_score": 91.0, "policy_blocked": False}
        ]
        if market == "KR"
        else [{"symbol": "AAPL", "position": "LONG", "signal_score": 94.0, "policy_blocked": False}],
    )

    result = service.select_candidates(
        {"asset_scope": "ALL", "max_open_positions": 3, "min_signal_confidence": 0.75},
        held_symbols={"005930"},
    )

    assert [item["symbol"] for item in result] == ["AAPL"]
    assert result[0]["market"] == "US"
    assert result[0]["confidence_score"] == 0.94


def test_select_candidates_respects_market_allocation_before_filling_remaining_slots(monkeypatch):
    service = AiFundStockSelectionService()
    rows = {
        "KR": [
            {"symbol": "005930", "position": "LONG", "signal_score": 90.0, "policy_blocked": False},
            {"symbol": "000660", "position": "LONG", "signal_score": 88.0, "policy_blocked": False},
        ],
        "US": [
            {"symbol": "AAPL", "position": "LONG", "signal_score": 95.0, "policy_blocked": False},
            {"symbol": "MSFT", "position": "LONG", "signal_score": 93.0, "policy_blocked": False},
        ],
    }
    monkeypatch.setattr(service, "_load_active_predictions", lambda market, *_args: rows[market])

    result = service.select_candidates(
        {
            "asset_scope": "ALL",
            "max_open_positions": 2,
            "min_signal_confidence": 0.75,
            "kr_allocation_pct": 50,
            "us_allocation_pct": 50,
        },
        held_symbols=set(),
    )

    assert [(item["market"], item["symbol"]) for item in result] == [("US", "AAPL"), ("KR", "005930")]
    assert {item["market_allocation_pct"] for item in result} == {50.0}


def test_select_candidates_rejects_blocked_and_below_confidence_rows(monkeypatch):
    service = AiFundStockSelectionService()
    monkeypatch.setattr(
        service,
        "_load_active_predictions",
        lambda *_args: [
            {"symbol": "005930", "position": "LONG", "signal_score": 90.0, "policy_blocked": True},
            {"symbol": "000660", "position": "LONG", "signal_score": 74.0, "policy_blocked": False},
        ],
    )

    result = service.select_candidates(
        {"asset_scope": "KR", "max_open_positions": 3, "min_signal_confidence": 0.75},
        held_symbols=set(),
    )

    assert result == []


def test_availability_explains_when_market_policy_blocks_every_candidate(monkeypatch):
    service = AiFundStockSelectionService()
    monkeypatch.setattr(
        service,
        "_load_market_predictions",
        lambda market, *_args: [
            {
                "symbol": "005930" if market == "KR" else "AAPL",
                "position": "HOLD",
                "signal_score": 0.0,
                "policy_blocked": True,
                "market_regime_state": "risk_off",
                "policy_block_reason": "market_regime",
            }
        ],
    )

    availability = service.get_availability({"asset_scope": "ALL"})

    assert availability["KR"]["status"] == "POLICY_BLOCKED"
    assert availability["US"]["blocked_count"] == 1
    assert availability["KR"]["message"] == "시장 위험 정책이 모든 후보를 보류했습니다."
