# ML 데이터셋 운영 런북

이 문서는 주식/코인 학습 데이터셋을 실제로 어떻게 만들고, 어떤 순서로 학습을 돌리고, 무엇을 확인해야 하는지 팀 공용 기준으로 정리한 운영 문서입니다.

실제 버튼 클릭 순서와 serving 전환 절차는 `ml/live_run_checklist.md`를 함께 참고합니다.

---

## 1. 기본 원칙

- **주식 데이터**는 Toss Open API를 메인으로 사용합니다.
- **코인 데이터**는 Binance 공개 캔들 API를 메인으로 사용합니다.
- 사용자 API Key는 프론트엔드로 절대 전달하지 않고, **Supabase `user_api_keys` 테이블에 암호화 저장된 값을 백엔드에서만 복호화**해서 사용합니다.
- 개인 계좌 잔고, 주문 이력, API Key 자체는 학습 데이터에 포함하지 않습니다.

---

## 2. 현재 데이터셋 생성 방식

### 2.1 주식

- 소스: Toss Open API
- 인증: 로그인 사용자의 Supabase access token
- 내부 동작:
  1. 프론트엔드 또는 스크립트가 access token 전달
  2. 백엔드가 `user_api_keys`에서 해당 사용자 `TOSS` 키 조회
  3. `crypto_helper.py`로 `encrypted_access_key`, `encrypted_secret_key` 복호화
  4. Toss OAuth 토큰 발급 후 캔들 수집
  5. `ml/data/raw/stock_candles.csv`에 저장

### 2.2 코인

- 소스: Binance 공개 API
- 인증: 불필요
- 저장 위치: `ml/data/raw/crypto_candles.csv`

### 2.3 공통 보조 데이터

- 매크로 지표: `ml/data/raw/macro_indices.csv`
- 뉴스 피처: `ml/data/raw/news_features.csv`
- 코인 외부 피처: `ml/data/raw/crypto_market_features.csv`
- 주식 이벤트 피처: `ml/data/raw/stock_event_features.csv`
- 유니버스 프리셋: `ml/data/reference/training_universes.json`

선택 보조 데이터가 없는 경우 v6 파이프라인은 0값으로 대체하여 동작합니다.
v7 파이프라인은 동일한 구조를 유지하면서, 외부 피처가 실제로 채워지면 자동 반영하고 없으면 0값으로 대체합니다.

---

## 3. 추천 수집 기준

### 3.1 주식 1차 권장

- 유니버스: `stock_core_90`
- 봉: `1d`
- 개수: 최소 `500`, 가능하면 `700~1000`
- 수집 방식: `10종목 단위 chunk`
- 권장: `include_macro`를 켜서 KOSPI/KOSDAQ/NASDAQ/USDKRW를 함께 갱신

예시:

```bash
source ml/.venv/bin/activate

python backend/scripts/export_training_candles.py \
  --asset-type STOCK \
  --exchange TOSS \
  --preset stock_core_90 \
  --interval 1d \
  --count 700 \
  --auth-token "$SUPABASE_ACCESS_TOKEN" \
  --sleep-seconds 2 \
  --retry 3 \
  --retry-wait-seconds 60 \
  --chunk-size 10 \
  --chunk-index 1 \
  --append \
  --failure-output ml/data/raw/stock_failures_chunk1.json
```

### 3.2 코인 1차 권장

- 유니버스: `crypto_core_30`
- 봉: `1h`
- 개수: 최소 `1500`, 가능하면 `2500~4000`
- 수집 방식: `10종목 단위 chunk`

예시:

```bash
source ml/.venv/bin/activate

python backend/scripts/export_training_candles.py \
  --asset-type CRYPTO \
  --exchange BINANCE \
  --preset crypto_core_30 \
  --interval 1h \
  --count 2500 \
  --chunk-size 10 \
  --chunk-index 1 \
  --append \
  --failure-output ml/data/raw/crypto_failures_chunk1.json
```

---

## 4. 학습 순서

### 4.1 주식 v6

```bash
source ml/.venv/bin/activate

python ml/src/build_features.py --config ml/configs/lgbm_stock_v6.yaml
python ml/src/run_pipeline_bundle.py \
  --config ml/configs/lgbm_stock_v6.yaml \
  --risk-config ml/configs/lgbm_stock_risk_v6.yaml \
  --skip-build-features \
  --summary-output ml/data/processed/stock_v6_summary.json
```

### 4.2 코인 v6

```bash
source ml/.venv/bin/activate

python ml/src/build_features.py --config ml/configs/lgbm_crypto_v6.yaml
python ml/src/run_pipeline_bundle.py \
  --config ml/configs/lgbm_crypto_v6.yaml \
  --risk-config ml/configs/lgbm_crypto_risk_v6.yaml \
  --skip-build-features \
  --summary-output ml/data/processed/crypto_v6_summary.json
```

### 4.3 관리자 페이지 직접 실행

관리자 페이지 `/admin/ml-data`에서는 아래 두 작업을 직접 실행할 수 있습니다.

1. 학습용 캔들 CSV 생성
2. `v6`, `v7` 학습 파이프라인 실행
3. `stock-v7-full`, `crypto-v7-full` 자동 수집+학습 실행

작업 이력은 아래 파일에 자동 누적됩니다.

```text
ml/data/ops/job_history.json
ml/data/ops/model_registry.json
```

---

## 5. 반드시 확인할 평가 항목

### 5.1 분류 지표

- `roc_auc`
- `average_precision`
- `accuracy`
- `precision`
- `recall`
- `precision_at_top_10pct`

### 5.2 백테스트 지표

- `excess_return_net`
- `selection_win_rate_net`
- `max_drawdown_net`
- `symbol_breakdown`
- `market_breakdown`
- `sector_breakdown`

### 5.3 시계열 안정성

- `time_series_cv_average.roc_auc`
- `time_series_cv_average.precision_at_top_10pct`

---

## 6. 현재 운영 해석 기준

- **주식**
  - 분류 지표와 백테스트를 함께 보고 추천 버전 선정
  - `excess_return_net`가 플러스여도 `max_drawdown_net`가 너무 크면 보수적으로 해석

- **코인**
  - 분류 지표만 좋고 비용 반영 백테스트가 음수일 수 있음
  - 이 경우 바로 운영 반영하지 않고, 외부 피처 실측값 채운 뒤 재검증

---

## 7. 실패 대응 기준

### 7.1 Toss 429

- 한 번에 너무 많은 심볼을 넣지 않음
- `chunk-size 5~10` 유지
- `sleep-seconds 2~3`
- `retry-wait-seconds 60 이상`

### 7.2 빈 데이터

- 장외 시간 또는 Toss 제공 범위 제한 가능성 확인
- 실패 파일(`failure-output`)에 심볼별 사유 기록

### 7.3 피처가 전부 0으로 들어가는 경우

- `news_features.csv`
- `crypto_market_features.csv`
- `stock_event_features.csv`

위 파일이 없는 상태인지 먼저 확인

---

## 8. 관리자 페이지 해석 기준

관리자 페이지 `/admin/ml-data`에서는 아래를 우선 확인합니다.

1. 버전별 `CV 구분력`
2. 버전별 `상위 10% 적중`
3. 버전별 `복합 초과수익(순)`
4. 버전별 `복합 승률`
5. 버전별 `최대낙폭`
6. 레지스트리의 `LATEST / PICK / SERVING` 상태
7. 운영 준비 상태 패널의 `Toss 키 / 원천 CSV / 매크로 / 외부 피처 / SERVING` 체크
8. 선택 버전이 `SERVING / PICK / LATEST` 대비 얼마나 개선됐는지 버전 차이 요약 패널에서 확인

추천 버전은 단순 최신 버전이 아니라, **비용 반영 복합 백테스트 + 시계열 CV 안정성**이 더 좋은 쪽을 우선합니다.

서비스 반영은 아래 순서로 진행합니다.

1. 성능 비교 표에서 후보 버전 확인
2. 레지스트리 패널에서 `PICK` 또는 검토 완료 버전 확인
3. `서비스 반영` 버튼으로 `SERVING` 전환
4. 이후 예측 API serving 연동 전까지는 운영 기준 기록용으로 활용

백엔드 모델 선택 기준은 다음 우선순위를 따릅니다.

1. `SERVING`
2. `PICK`
3. `LATEST`

현재 선택 결과는 `GET /api/ml/active-model`로 확인할 수 있습니다.

생성된 실험 리포트 목록은 관리자 페이지 또는 `GET /api/ml/reports`로 다시 확인할 수 있습니다.
학습 또는 `full-run`이 성공하면 최신 summary JSON 기준으로 Markdown 실험 리포트가 자동 생성되며, 운영자는 결과 확인 시 최근 리포트가 함께 갱신됐는지도 체크해야 합니다.
주식 데이터셋 수집에 필요한 Toss 키는 관리자 페이지 준비 상태 패널에서 `supabase.user_api_keys -> encrypted_access_key/encrypted_secret_key -> crypto.decrypt` 경로로 확인하며, 민감정보 원문은 화면에 노출하지 않습니다.
