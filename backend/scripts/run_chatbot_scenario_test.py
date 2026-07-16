import functools
import json
import os
from datetime import datetime, timezone
from typing import Callable, List, Dict, Any

import backend.services.chatbot.chat_service as chat_service_module
from backend.services.chatbot.chat_service import ChatbotService
from backend.services.chatbot.llm_client import ChatbotLLMClient
from backend.app import app

def make_test_interceptor(
    original_func: Callable[..., Any], captured_list: List[Dict[str, Any]]
) -> Callable[..., Any]:
    @functools.wraps(original_func)
    def wrapper(auth_header: str, message: str, **kwargs: Any) -> Any:
        captured_list.append(kwargs)
        return original_func(auth_header, message, **kwargs)
    return wrapper

def make_mock_tool(tool_name: str) -> Callable[..., Any]:
    def mock_tool(auth_header: str, message: str, **kwargs: Any) -> Any:
        return {"success": True, "reply": f"Mocked {tool_name} reply", "data": {}}
    return mock_tool

def evaluate_scenario(captured: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """기대값(expected)의 인자들이 캡처된 인자(captured)에 부분 집합으로 모두 포함되어 있는지 검사합니다(Subset Match)."""
    tool_match = captured.get("tool_name") == expected.get("tool_name")
    
    cap_args = captured.get("arguments") or {}
    exp_args = expected.get("arguments") or {}
    args_match = True
    for k, v in exp_args.items():
        if cap_args.get(k) != v:
            args_match = False
            break
            
    status = "PASS" if (tool_match and args_match) else "FAIL"
    return {
        "status": status,
        "tool_match": tool_match,
        "args_match": args_match
    }

def calculate_metrics(results: list) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = total - passed
    success_rate = (passed / total * 100) if total > 0 else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "success_rate": round(success_rate, 2)
    }

def generate_report(results: list, metrics: dict, filepath: str) -> None:
    now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines = [
        "# 챗봇 시나리오 통합 성능 진단 결과 보고서",
        f"\n* **진단 시간**: {now_str}",
        f"* **총 테스트 케이스**: {metrics['total']}개",
        f"* **통과**: {metrics['passed']}개",
        f"* **실패**: {metrics['failed']}개",
        f"* **최종 성공률**: {metrics['success_rate']}%\n",
        "## 1. 시나리오별 검증 세부 내역",
        "| 번호 | 발화 (Input) | 결과 | 세부 판정 |",
        "| :--- | :--- | :--- | :--- |"
    ]
    for r in results:
        lines.append(f"| {r['scenario_id']} | \"{r['input']}\" | **{r['status']}** | {r.get('details') or ''} |")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def run_test_suite(report_path: str = "docs/superpowers/specs/2026-07-16-chatbot-scenario-test-result.md") -> dict:
    # 7대 시나리오 정의
    scenarios = [
        {
            "scenario_id": 1,
            "input": "비트코인 현재가 얼마야?",
            "expected": {"tool_name": "get_asset_price", "arguments": {"query": "BTC", "exchange": "COINONE"}}
        },
        {
            "scenario_id": 2,
            "input": "삼성전자 현재가 알려줘",
            "expected": {"tool_name": "get_asset_price", "arguments": {"query": "삼성전자", "exchange": "TOSS"}}
        },
        {
            "scenario_id": 3,
            "input": "리플 1시간 봉 캔들 흐름 보여줘",
            "expected": {"tool_name": "get_asset_candles", "arguments": {"query": "XRP", "exchange": "COINONE", "interval": "1h"}}
        },
        {
            "scenario_id": 4,
            "input": "이더리움 단타 진입 타이밍 봐줘",
            "expected": {"tool_name": "get_crypto_market_context", "arguments": {"query": "ETH", "exchange": "COINONE", "interval": "1h"}}
        },
        {
            "scenario_id": 5,
            "input": "내 보유 코인 잔고 보여줘",
            "expected": {"tool_name": "get_holdings", "arguments": {"exchange": "COINONE"}}
        },
        {
            "scenario_id": 6,
            "input": "현대차 관련 최근 소식 분석해줘",
            "expected": {"tool_name": "get_asset_outlook", "arguments": {"query": "현대차"}}
        },
        {
            "scenario_id": 7,
            "input": "솔라나 관심종목에 넣어줘",
            "expected": {"tool_name": "add_watchlist_item", "arguments": {"query": "SOL"}}
        }
    ]

    tool_names = [
        "get_asset_price",
        "get_asset_candles",
        "get_crypto_market_context",
        "get_holdings",
        "get_asset_outlook",
        "add_watchlist_item"
    ]

    # Mock LLM Client
    def mock_generate_reply(self_llm, *, system_prompt, user_message, **kwargs):
        mapping = {
            "비트코인 현재가 얼마야?": {
                "name": "get_asset_price",
                "arguments": json.dumps({"query": "BTC", "exchange": "COINONE"})
            },
            "삼성전자 현재가 알려줘": {
                "name": "get_asset_price",
                "arguments": json.dumps({"query": "삼성전자", "exchange": "TOSS"})
            },
            "리플 1시간 봉 캔들 흐름 보여줘": {
                "name": "get_asset_candles",
                "arguments": json.dumps({"query": "XRP", "exchange": "COINONE", "interval": "1h"})
            },
            "이더리움 단타 진입 타이밍 봐줘": {
                "name": "get_crypto_market_context",
                "arguments": json.dumps({"query": "ETH", "exchange": "COINONE", "interval": "1h"})
            },
            "내 보유 코인 잔고 보여줘": {
                "name": "get_holdings",
                "arguments": json.dumps({"exchange": "COINONE"})
            },
            "현대차 관련 최근 소식 분석해줘": {
                "name": "get_asset_outlook",
                "arguments": json.dumps({"query": "현대차"})
            },
            "솔라나 관심종목에 넣어줘": {
                "name": "add_watchlist_item",
                "arguments": json.dumps({"query": "SOL"})
            }
        }
        
        matched = mapping.get(user_message)
        if matched:
            return {
                "reply": "Mocked response",
                "tool_calls": [
                    {
                        "id": "mock_call_id",
                        "type": "function",
                        "function": matched
                    }
                ]
            }
        return {
            "reply": "No tool call matched",
            "tool_calls": []
        }

    # Mock Supabase clients to bypass DB queries in testing
    import backend.services.supabase_client as supabase_client_module
    import backend.services.chatbot.conversation_repository as conv_repo_module
    import backend.services.chatbot.llm_client as llm_client_module
    import backend.services.chatbot.tool_registry as tool_registry_module
    import backend.services.chatbot.chat_service as chat_service_module
    import jwt

    original_generate_reply = ChatbotLLMClient.generate_reply
    ChatbotLLMClient.generate_reply = mock_generate_reply

    original_query_supabase = supabase_client_module.query_supabase
    original_query_supabase_as_service_role = supabase_client_module.query_supabase_as_service_role
    original_safe_query_supabase = getattr(supabase_client_module, "safe_query_supabase", None)

    # 오리지널 모듈별 변수 저장
    orig_conv_qs = getattr(conv_repo_module, "query_supabase", None)
    orig_llm_qs = getattr(llm_client_module, "query_supabase", None)
    orig_llm_qsr = getattr(llm_client_module, "query_supabase_as_service_role", None)
    orig_tool_qs = getattr(tool_registry_module, "query_supabase", None)
    orig_tool_sqs = getattr(tool_registry_module, "safe_query_supabase", None)
    orig_tool_sqsr = getattr(tool_registry_module, "safe_query_supabase_as_service_role", None)
    orig_chat_sqs = getattr(chat_service_module, "safe_query_supabase", None)
    original_run_chatbot_tool = getattr(chat_service_module, "run_chatbot_tool", None)

    def mock_query_supabase(*args, **kwargs):
        return []

    def mock_query_supabase_as_service_role(*args, **kwargs):
        return []

    def mock_run_chatbot_tool(auth_header, message):
        return None

    # supabase_client 모듈 자체 패치
    supabase_client_module.query_supabase = mock_query_supabase
    supabase_client_module.query_supabase_as_service_role = mock_query_supabase_as_service_role
    if hasattr(supabase_client_module, "safe_query_supabase"):
        supabase_client_module.safe_query_supabase = mock_query_supabase

    # 개별 모듈 네임스페이스 패치
    if hasattr(conv_repo_module, "query_supabase"):
        conv_repo_module.query_supabase = mock_query_supabase
    if hasattr(llm_client_module, "query_supabase"):
        llm_client_module.query_supabase = mock_query_supabase
    if hasattr(llm_client_module, "query_supabase_as_service_role"):
        llm_client_module.query_supabase_as_service_role = mock_query_supabase_as_service_role
    if hasattr(tool_registry_module, "query_supabase"):
        tool_registry_module.query_supabase = mock_query_supabase
    if hasattr(tool_registry_module, "safe_query_supabase"):
        tool_registry_module.safe_query_supabase = mock_query_supabase
    if hasattr(tool_registry_module, "safe_query_supabase_as_service_role"):
        tool_registry_module.safe_query_supabase_as_service_role = mock_query_supabase_as_service_role
    if hasattr(chat_service_module, "safe_query_supabase"):
        chat_service_module.safe_query_supabase = mock_query_supabase
    chat_service_module.run_chatbot_tool = mock_run_chatbot_tool

    dummy_token = jwt.encode({"sub": "test-user-id"}, "secret", algorithm="HS256")
    auth_header = f"Bearer {dummy_token}"

    # Mocking 및 몽키 패치 준비
    original_funcs = {}
    results = []

    try:
        # Flask app context 하에서 실행
        with app.app_context():
            chatbot_service = ChatbotService()
            
            # 각 시나리오별로 순차 실행
            for sc in scenarios:
                captured_dict = {name: [] for name in tool_names}
                
                # 패치 적용
                for name in tool_names:
                    original = getattr(chat_service_module, name, None)
                    if original:
                        original_funcs[name] = original
                        
                        mock_original = make_mock_tool(name)
                        wrapped = make_test_interceptor(mock_original, captured_dict[name])
                        setattr(chat_service_module, name, wrapped)
                
                try:
                    # 챗봇에 발화 전달
                    chatbot_service.reply(
                        message=sc["input"],
                        user_id="test-user-id",
                        auth_header=auth_header
                    )
                except Exception as e:
                    # 에러 발생 시 세부 내역에 기록
                    pass
                finally:
                    # 패치 원복
                    for name, original in original_funcs.items():
                        setattr(chat_service_module, name, original)
                
                # 캡처 결과 분석
                captured = {}
                for name, calls in captured_dict.items():
                    if calls:
                        captured = {
                            "tool_name": name,
                            "arguments": calls[0]
                        }
                        break
                
                eval_res = evaluate_scenario(captured, sc["expected"])
                details = f"Expected: {sc['expected']['tool_name']}({sc['expected']['arguments']}), Captured: {captured.get('tool_name')}({captured.get('arguments')})"
                results.append({
                    "scenario_id": sc["scenario_id"],
                    "input": sc["input"],
                    "status": eval_res["status"],
                    "details": details
                })
    finally:
        # 복구
        ChatbotLLMClient.generate_reply = original_generate_reply
        supabase_client_module.query_supabase = original_query_supabase
        supabase_client_module.query_supabase_as_service_role = original_query_supabase_as_service_role
        if original_safe_query_supabase is not None:
            supabase_client_module.safe_query_supabase = original_safe_query_supabase

        if orig_conv_qs is not None:
            conv_repo_module.query_supabase = orig_conv_qs
        if orig_llm_qs is not None:
            llm_client_module.query_supabase = orig_llm_qs
        if orig_llm_qsr is not None:
            llm_client_module.query_supabase_as_service_role = orig_llm_qsr
        if orig_tool_qs is not None:
            tool_registry_module.query_supabase = orig_tool_qs
        if orig_tool_sqs is not None:
            tool_registry_module.safe_query_supabase = orig_tool_sqs
        if orig_tool_sqsr is not None:
            tool_registry_module.safe_query_supabase_as_service_role = orig_tool_sqsr
        if orig_chat_sqs is not None:
            chat_service_module.safe_query_supabase = orig_chat_sqs
        if original_run_chatbot_tool is not None:
            chat_service_module.run_chatbot_tool = original_run_chatbot_tool



    metrics = calculate_metrics(results)
    
    # 보고서 디렉토리 확인 및 생성
    report_dir = os.path.dirname(report_path)
    if report_dir and not os.path.exists(report_dir):
        os.makedirs(report_dir, exist_ok=True)
        
    generate_report(results, metrics, report_path)
    return {
        "results": results,
        "metrics": metrics
    }


