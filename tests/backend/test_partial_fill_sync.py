import pytest
from unittest.mock import MagicMock, patch
from backend.services.open_order_status_sync_service import OpenOrderStatusSyncService


def test_handle_partial_filled_exit_order_recovers_rule():
    # 1. 모의 데이터 설정
    proposal = {
        "id": "mock-proposal-id",
        "volume": "3.0"
    }
    current_order = {
        "executed_qty": "2.0",
        "status": "CANCELED"
    }
    
    mock_rule = {
        "id": "mock-rule-id",
        "entry_price": 10000.0,
        "quantity": 3.0,
        "auto_restart_on_partial_fill": True,
        "investment_amount": 30000.0
    }

    # 2. Supabase 쿼리 함수 모킹
    mock_query = MagicMock(return_value=[mock_rule])
    
    service = OpenOrderStatusSyncService()
    
    with patch("backend.services.open_order_status_sync_service.query_supabase_as_service_role", mock_query):
        service._handle_partial_filled_exit_order(proposal, current_order, "CANCELED")
        
        # 3. DB 조회가 올바르게 일어났는지 확인
        mock_query.assert_any_call(
            "auto_trading_rules",
            "GET",
            params={
                "exit_order_proposal_id": "eq.mock-proposal-id",
                "limit": "1"
            }
        )
        
        # 4. DB 업데이트가 RUNNING 상태와 남은 수량(1.0)으로 올바르게 들어갔는지 확인
        # 마지막 patch 호출 인자 체크
        patch_calls = [
            call for call in mock_query.call_args_list 
            if call[0][0].startswith("auto_trading_rules?id=eq.mock-rule-id") and call[0][1] == "PATCH"
        ]
        assert len(patch_calls) == 1
        patch_data = patch_calls[0][1]["json_data"]
        
        assert patch_data["status"] == "RUNNING"
        assert patch_data["quantity"] == 1.0
        assert patch_data["investment_amount"] == 10000.0
        assert patch_data["exit_order_proposal_id"] is None
        assert "부분 체결 완료 감지" in patch_data["last_error"]


def test_handle_partial_filled_exit_order_does_not_recover_if_disabled():
    proposal = {
        "id": "mock-proposal-id",
        "volume": "3.0"
    }
    current_order = {
        "executed_qty": "2.0",
        "status": "CANCELED"
    }
    
    mock_rule = {
        "id": "mock-rule-id",
        "entry_price": 10000.0,
        "quantity": 3.0,
        "auto_restart_on_partial_fill": False, # 자동 재감시 비활성화
        "investment_amount": 30000.0
    }

    mock_query = MagicMock(return_value=[mock_rule])
    service = OpenOrderStatusSyncService()
    
    with patch("backend.services.open_order_status_sync_service.query_supabase_as_service_role", mock_query):
        service._handle_partial_filled_exit_order(proposal, current_order, "CANCELED")
        
        # PATCH 업데이트가 일어나지 않아야 함
        patch_calls = [
            call for call in mock_query.call_args_list 
            if call[0][0].startswith("auto_trading_rules") and call[0][1] == "PATCH"
        ]
        assert len(patch_calls) == 0
