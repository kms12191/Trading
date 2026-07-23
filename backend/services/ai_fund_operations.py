"""AI 위탁운용 워커 심박과 연속 장애 회로 차단기를 관리합니다."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.services.supabase_client import safe_query_supabase_as_service_role


class AiFundOperationsService:
    """설정별 운영 상태를 기록하고 반복 장애 시 신규 진입을 중단합니다."""

    def record_success(self, config: dict[str, Any]) -> None:
        config_id = str(config.get("id") or "")
        if not config_id:
            return
        now = datetime.now(timezone.utc).isoformat()
        self._update_config(
            config_id,
            {"consecutive_failure_count": 0, "last_heartbeat_at": now},
        )
        self._record_event(config_id, "HEARTBEAT", "AI 위탁운용 주기 정상 완료")

    def record_failure(self, config: dict[str, Any], message: str, threshold: int = 3) -> bool:
        config_id = str(config.get("id") or "")
        if not config_id:
            return False
        failure_count = int(config.get("consecutive_failure_count") or 0) + 1
        threshold = max(int(threshold), 1)
        now = datetime.now(timezone.utc).isoformat()
        halted = failure_count >= threshold
        payload: dict[str, Any] = {
            "consecutive_failure_count": failure_count,
            "last_failure_at": now,
        }
        if halted:
            payload["is_active"] = False
        self._update_config(config_id, payload)
        self._record_event(
            config_id,
            "HALTED" if halted else "FAILURE",
            message,
            {"consecutive_failure_count": failure_count, "threshold": threshold},
        )
        return halted

    def resume(self, config_id: str) -> None:
        """운영자의 명시적 조치로 중단된 설정을 재개합니다."""
        now = datetime.now(timezone.utc).isoformat()
        self._update_config(
            config_id,
            {
                "is_active": True,
                "consecutive_failure_count": 0,
                "last_heartbeat_at": now,
            },
        )
        self._record_event(config_id, "RESUMED", "운영자 요청으로 AI 위탁운용 재개")

    @staticmethod
    def _update_config(config_id: str, payload: dict[str, Any]) -> None:
        safe_query_supabase_as_service_role(
            f"admin_ai_fund_configs?id=eq.{config_id}",
            method="PATCH",
            json_data=payload,
        )

    @staticmethod
    def _record_event(
        config_id: str,
        event_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        safe_query_supabase_as_service_role(
            "ai_fund_operation_events",
            method="POST",
            json_data={
                "config_id": config_id,
                "event_type": event_type,
                "message": message,
                "metadata": metadata or {},
            },
        )
