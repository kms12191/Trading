import json
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METRICS_PATH = (
    PROJECT_ROOT / "ml" / "models" / "lgbm_crypto_short_v11.metrics.json"
    if (PROJECT_ROOT / "ml" / "models" / "lgbm_crypto_short_v11.metrics.json").exists()
    else PROJECT_ROOT / "ml" / "models" / "lgbm_crypto_short_v1.metrics.json"
)
DEFAULT_BACKTEST_PATH = (
    PROJECT_ROOT / "ml" / "data" / "processed" / "crypto_backtest_short_v11.json"
    if (PROJECT_ROOT / "ml" / "data" / "processed" / "crypto_backtest_short_v11.json").exists()
    else PROJECT_ROOT / "ml" / "data" / "processed" / "crypto_backtest_short_v1.json"
)


class AiFundCryptoShortPerformanceService:
    """숏 모델의 연구용 성능 요약을 읽고 실거래 전 검토 상태를 만든다."""

    def __init__(self, metrics_path: Path = DEFAULT_METRICS_PATH, backtest_path: Path = DEFAULT_BACKTEST_PATH):
        self.metrics_path = metrics_path
        self.backtest_path = backtest_path

    @staticmethod
    def _read_json(path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @classmethod
    def _to_json_safe(cls, value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: cls._to_json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._to_json_safe(item) for item in value]
        return value

    def get_snapshot(self) -> dict:
        metrics = self._to_json_safe(self._read_json(self.metrics_path))
        backtest = self._to_json_safe(self._read_json(self.backtest_path))
        if not metrics:
            return {
                "status": "TRAINING_PENDING",
                "message": "숏 전용 모델이 아직 학습되지 않았습니다. 다음 코인 자동 학습 주기에 생성됩니다.",
                "model_version": "lgbm_crypto_short_v1",
                "metrics": {},
                "backtest": {},
            }
        if not backtest:
            return {
                "status": "BACKTEST_PENDING",
                "message": "숏 모델 학습은 완료됐지만 비용 반영 백테스트 결과가 아직 없습니다.",
                "model_version": "lgbm_crypto_short_v1",
                "metrics": metrics,
                "backtest": {},
            }

        net_return = float(backtest.get("top_avg_future_return_net") or 0.0)
        win_rate = float(backtest.get("selection_win_rate_net") or 0.0)
        selected_rows = int(backtest.get("selected_rows") or 0)
        ready_for_review = selected_rows > 0 and net_return > 0 and win_rate >= 0.5
        return {
            "status": "READY_FOR_REVIEW" if ready_for_review else "LIVE_TRADING_HOLD",
            "message": "성능 기준을 통과해 운영 검토가 가능합니다." if ready_for_review else "검증 기준을 충족하지 않아 실거래 연결을 보류합니다.",
            "model_version": str(backtest.get("model_version") or "lgbm_crypto_short_v1"),
            "metrics": metrics,
            "backtest": backtest,
        }
