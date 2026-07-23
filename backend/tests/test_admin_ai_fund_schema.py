import pytest
from backend.services.supabase_client import safe_query_supabase_as_service_role


def test_admin_ai_fund_configs_table_exists():
    """Verify admin_ai_fund_configs table query executes without crashing."""
    res = safe_query_supabase_as_service_role("admin_ai_fund_configs", params={"limit": "0"})
    assert res is not None or res == []


def test_admin_ai_trade_logs_table_exists():
    """Verify admin_ai_trade_logs table query executes without crashing."""
    res = safe_query_supabase_as_service_role("admin_ai_trade_logs", params={"limit": "0"})
    assert res is not None or res == []

