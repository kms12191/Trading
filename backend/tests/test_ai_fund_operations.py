from backend.services.ai_fund_operations import AiFundOperationsService


def test_record_failure_halts_config_after_consecutive_failure_threshold(monkeypatch):
    writes = []

    def fake_query(endpoint, method="GET", json_data=None, **_kwargs):
        writes.append((endpoint, method, json_data))
        return [json_data]

    monkeypatch.setattr(
        "backend.services.ai_fund_operations.safe_query_supabase_as_service_role",
        fake_query,
    )
    config = {"id": "config-1", "consecutive_failure_count": 2, "is_active": True}

    halted = AiFundOperationsService().record_failure(config, "대사 실패", threshold=3)

    assert halted is True
    assert writes[0][0] == "admin_ai_fund_configs?id=eq.config-1"
    assert writes[0][2]["consecutive_failure_count"] == 3
    assert writes[0][2]["is_active"] is False


def test_record_success_resets_failures_and_updates_heartbeat(monkeypatch):
    writes = []
    monkeypatch.setattr(
        "backend.services.ai_fund_operations.safe_query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, **_kwargs: writes.append((endpoint, method, json_data)) or [json_data],
    )

    AiFundOperationsService().record_success({"id": "config-1", "consecutive_failure_count": 2})

    assert writes[0][2]["consecutive_failure_count"] == 0
    assert "last_heartbeat_at" in writes[0][2]


def test_resume_reactivates_config_and_records_audit_event(monkeypatch):
    writes = []
    monkeypatch.setattr(
        "backend.services.ai_fund_operations.safe_query_supabase_as_service_role",
        lambda endpoint, method="GET", json_data=None, **_kwargs: writes.append((endpoint, method, json_data)) or [json_data],
    )

    AiFundOperationsService().resume("config-1")

    assert writes[0][2]["is_active"] is True
    assert writes[0][2]["consecutive_failure_count"] == 0
    assert writes[1][2]["event_type"] == "RESUMED"
