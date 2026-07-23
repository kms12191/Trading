from __future__ import annotations

from dataclasses import dataclass

import pytest
import requests

from backend.services.dart_repository import DartRepository


@dataclass(frozen=True)
class FakeResponse:
    payload: list[dict]
    headers: dict[str, str]

    def json(self) -> list[dict]:
        return self.payload

    def raise_for_status(self) -> None:
        return None


def test_disclosure_list_and_count_use_the_same_30_day_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setattr(DartRepository, "_retention_cutoff_date", classmethod(lambda cls: "2026-06-20"))
    calls: list[dict[str, str]] = []
    responses = [
        FakeResponse(payload=[{"rcept_no": "recent"}], headers={}),
        FakeResponse(payload=[], headers={"Content-Range": "0-0/1"}),
    ]

    def fake_get(url: str, *, headers: dict[str, str], params: dict[str, str], timeout: int) -> FakeResponse:
        calls.append(params)
        return responses.pop(0)

    monkeypatch.setattr(requests, "get", fake_get)
    repository = DartRepository()

    assert repository.list_disclosures(symbol="041830", limit=10) == [{"rcept_no": "recent"}]
    assert repository.count_disclosures(symbol="041830") == 1
    assert calls[0]["rcept_dt"] == "gte.2026-06-20"
    assert calls[1]["rcept_dt"] == "gte.2026-06-20"


def test_disclosure_list_separates_company_name_and_stock_code_in_alias_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    captured_params: list[dict[str, str]] = []

    def fake_get(url: str, *, headers: dict[str, str], params: dict[str, str], timeout: int) -> FakeResponse:
        captured_params.append(params)
        return FakeResponse(payload=[{"rcept_no": "recent"}], headers={})

    monkeypatch.setattr(requests, "get", fake_get)

    result = DartRepository().list_disclosures(query="이노스페이스 462350", limit=1)

    assert result == [{"rcept_no": "recent"}]
    assert captured_params[0]["stock_code"] == "eq.462350"
    assert "이노스페이스" in captured_params[0]["or"]
    assert "462350" not in captured_params[0]["or"]
