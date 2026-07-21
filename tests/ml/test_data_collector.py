import os
import json
import pytest
from pathlib import Path
from backend.scripts.export_training_candles import load_symbols_from_file

def test_load_symbols_from_active_universe_json(tmp_path):
    # active_universe.json 모의 파일 생성
    temp_json = tmp_path / "active_universe.json"
    mock_data = {
        "kr_stock": ["005930", "000660"],
        "us_stock": ["AAPL"],
        "crypto": ["BTCUSDT"]
    }
    
    with open(temp_json, "w") as f:
        json.dump(mock_data, f)
        
    # load_symbols_from_file가 모든 키에 대해 티커 목록을 통합 병합하여 로드하는지 확인
    symbols = load_symbols_from_file(temp_json)
    
    assert "005930" in symbols
    assert "AAPL" in symbols
    assert "BTCUSDT" in symbols
    assert len(symbols) == 4
