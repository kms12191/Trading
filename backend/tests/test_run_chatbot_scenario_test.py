import pytest
from backend.scripts.run_chatbot_scenario_test import (
    make_test_interceptor,
    evaluate_scenario,
    calculate_metrics,
    generate_report,
    run_test_suite
)

def test_interceptor_captures_arguments():
    captured = []
    def dummy_tool(auth_header, message, **kwargs):
        return {"success": True}
    
    wrapped = make_test_interceptor(dummy_tool, captured)
    wrapped("Bearer test", "msg", exchange="COINONE", query="BTC")
    
    assert len(captured) == 1
    assert captured[0]["exchange"] == "COINONE"
    assert captured[0]["query"] == "BTC"

def test_evaluate_scenario_passes_on_exact_match():
    captured = {"tool_name": "get_asset_price", "arguments": {"query": "BTC", "exchange": "COINONE"}}
    expected = {"tool_name": "get_asset_price", "arguments": {"query": "BTC", "exchange": "COINONE"}}
    result = evaluate_scenario(captured, expected)
    assert result["status"] == "PASS"

def test_evaluate_scenario_fails_on_mismatch():
    captured = {"tool_name": "get_asset_price", "arguments": {"query": "XRP", "exchange": "COINONE"}}
    expected = {"tool_name": "get_asset_price", "arguments": {"query": "BTC", "exchange": "COINONE"}}
    result = evaluate_scenario(captured, expected)
    assert result["status"] == "FAIL"

def test_calculate_metrics_accuracy():
    results = [
        {"status": "PASS"},
        {"status": "PASS"},
        {"status": "FAIL"},
    ]
    metrics = calculate_metrics(results)
    assert metrics["total"] == 3
    assert metrics["passed"] == 2
    assert metrics["failed"] == 1
    assert metrics["success_rate"] == pytest.approx(66.67, 0.01)

def test_generate_report_creates_markdown_file(tmp_path):
    test_results = [{"scenario_id": 1, "input": "test input", "status": "PASS", "details": "Success"}]
    test_metrics = {"total": 1, "passed": 1, "failed": 0, "success_rate": 100.0}
    
    report_dir = tmp_path / "specs"
    report_dir.mkdir()
    report_path = report_dir / "2026-07-16-chatbot-scenario-test-result.md"
    
    generate_report(test_results, test_metrics, str(report_path))
    
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "**총 테스트 케이스**: 1개" in content
    assert "**통과**: 1개" in content
    assert "**실패**: 0개" in content
    assert "**최종 성공률**: 100.0%" in content

def test_run_test_suite_integration(tmp_path):
    report_path = tmp_path / "integration_report.md"
    result = run_test_suite(str(report_path))
    
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "**총 테스트 케이스**: 7개" in content
    assert "**통과**: 7개" in content
    assert "**실패**: 0개" in content
    assert "**최종 성공률**: 100.0%" in content
    assert result["metrics"]["total"] == 7
    assert result["metrics"]["passed"] == 7
    assert result["metrics"]["success_rate"] == 100.0


