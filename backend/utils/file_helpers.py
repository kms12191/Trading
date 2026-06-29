import csv
import json
import re
from pathlib import Path

def read_json_file(path: Path) -> dict | None:
    """JSON 파일을 읽어서 딕셔너리로 반환합니다."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def read_csv_rows(path: Path, limit: int = 20) -> list[dict]:
    """CSV 파일의 행들을 딕셔너리 리스트로 읽어옵니다."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))[:limit]

def count_csv_rows(path: Path) -> int:
    """CSV 파일의 전체 데이터 행 개수(헤더 제외)를 반환합니다."""
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        return sum(1 for _ in reader)

def read_model_artifact(path: Path) -> dict:
    """모델 아티팩트 정보를 읽어 반환합니다."""
    return {
        "path": str(path),
        "data": read_json_file(path),
        "updated": path.exists(),
    }

def pick_existing_path(paths: list[Path]) -> Path:
    """주어진 경로 리스트 중 존재하는 첫 번째 경로를 반환합니다."""
    for path in paths:
        if path.exists():
            return path
    return paths[0]

def extract_version_number(path: Path) -> int:
    """파일명에서 버전 번호(_v숫자)를 추출합니다."""
    match = re.search(r"_v(\d+)(?:_|\.|$)", path.name)
    return int(match.group(1)) if match else 0

def sanitize_nan(data):
    """
    딕셔너리나 리스트 내부의 float 'NaN' 또는 'Infinity' 값을 
    JSON 표준 스펙에 맞춰 None(null)으로 재귀적으로 치환합니다.
    """
    import math
    if isinstance(data, dict):
        return {k: sanitize_nan(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_nan(v) for v in data]
    
    if not isinstance(data, str):
        try:
            val = float(data)
            if math.isnan(val) or math.isinf(val):
                return None
        except (ValueError, TypeError):
            pass
    return data
