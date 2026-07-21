import os
import json
import pytest
from ml.src.universe_screener import run_screener

def test_run_screener_filters_by_volume():
    # 간단한 가상 유니버스 리스트로 테스트
    mock_indices = {
        "kr_stock": ["005930"], # 삼성전자
        "us_stock": ["AAPL"],   # Apple
        "crypto": ["BTCUSDT"]   # BTC
    }
    
    # 60일 평균 거래대금이 극도로 낮은 임계값일 때 모두 통과해야 함
    test_path = "tests/ml/active_universe_test.json"
    result = run_screener(mock_indices, config_file=test_path, min_kr_vol=1, min_us_vol=1, min_crypto_vol=1)
    
    assert "kr_stock" in result
    assert "us_stock" in result
    assert "crypto" in result
    assert "005930" in result["kr_stock"]
    assert "AAPL" in result["us_stock"]
    assert "BTCUSDT" in result["crypto"]
    
    if os.path.exists(test_path):
        os.remove(test_path)
    
    # active_universe.json 파일 대신 격리된 테스트용 경로를 사용
    config_file = "tests/ml/active_universe_test.json"
    result = run_screener(mock_indices, config_file=config_file, min_kr_vol=1, min_us_vol=1, min_crypto_vol=1)
    
    assert os.path.exists(config_file)
    with open(config_file, "r") as f:
        saved_data = json.load(f)
        assert "005930" in saved_data["kr_stock"]
        
    # 테스트 파일 정리
    if os.path.exists(config_file):
        os.remove(config_file)
