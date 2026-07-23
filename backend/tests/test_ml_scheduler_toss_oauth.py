import requests

from backend.services import ml_scheduler


def test_request_toss_oauth_token_returns_none_on_connection_error(monkeypatch):
    def raise_connection_error(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError("dns failed")

    monkeypatch.setattr(ml_scheduler.requests, "post", raise_connection_error)

    assert ml_scheduler._request_toss_oauth_token("client-id", "client-secret") is None
