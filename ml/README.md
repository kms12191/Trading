# ML 파이프라인 문서

이 디렉토리는 트레이딩 보조용 LightGBM 모델을 학습하고 예측 결과를 생성하는 오프라인 ML 파이프라인입니다.
현재 코드 기준으로 주식 모델은 `v11`까지, 코인 모델은 `v9`까지 존재합니다.

## 1. 현재 버전 범위

### 주식

- 신호 모델: `lgbm_stock_v1.yaml` ~ `lgbm_stock_v11.yaml`
- 위험 모델: `lgbm_stock_risk_v1.yaml` ~ `lgbm_stock_risk_v11.yaml`
- 추가 실험 설정:
  - `lgbm_stock_risk_v11_pruned.yaml`
  - `lgbm_stock_risk_v11_lowimp_pruned.yaml`
  - `lgbm_stock_risk_v11_residual.yaml`

### 코인

- 신호 모델: `lgbm_crypto_v1.yaml` ~ `lgbm_crypto_v9.yaml`
- 위험 모델: `lgbm_crypto_risk_v1.yaml` ~ `lgbm_crypto_risk_v9.yaml`

## 2. 핵심 스크립트

```text
ml/src/build_features.py
ml/src/train_model.py
ml/src/evaluate.py
ml/src/predict.py
ml/src/backtest_signals.py
ml/src/run_pipeline_bundle.py
ml/src/tune_hyperparameters.py
ml/src/tune_stock_policy.py
ml/src/export_serving_package.py
ml/src/compare_experiments.py
ml/src/compare_model_versions.py
ml/src/write_experiment_report.py
```

### 역할 요약

- `build_features.py`
  - 캔들 + 외부 피처를 학습용 feature set으로 변환
- `train_model.py`
  - LightGBM 학습 및 모델 저장
- `predict.py`
  - 최신 데이터에 대한 확률/점수 예측 CSV 생성
- `backtest_signals.py`
  - `up_only`, `composite` 전략 백테스트
- `run_pipeline_bundle.py`
  - 피처 생성, 학습, 예측, 백테스트, 요약 출력까지 일괄 실행
- `tune_hyperparameters.py`
  - Optuna 기반 하이퍼파라미터 탐색
- `tune_stock_policy.py`
  - 주식 정책 임계값과 선택 규칙 비교
- `export_serving_package.py`
  - EC2 배포용 서빙 패키지와 `manifest.json` 생성

## 3. 데이터 구조

```text
ml/data/
├── raw/
│   ├── stock_candles.csv
│   ├── crypto_candles.csv
│   ├── crypto_candles_30m.csv
│   ├── macro_indices.csv
│   ├── news_features.csv
│   ├── stock_event_features.csv
│   └── *.template.csv
├── processed/
│   ├── *_features_lgbm_v*.csv
│   ├── *_predictions_lgbm_v*.csv
│   ├── *_backtest_*.json
│   ├── *_summary.json
│   └── 비교/실험 메모 문서
└── ops/
    ├── job_history.json
    └── model_registry.json
```

## 4. 현재 기준 실행 예시

### 주식 v11

```bash
cd ml
source .venv/bin/activate
python src/run_pipeline_bundle.py \
  --config configs/lgbm_stock_v11.yaml \
  --risk-config configs/lgbm_stock_risk_v11.yaml \
  --summary-output data/processed/stock_v11_summary.json
```

### 코인 v9

```bash
cd ml
source .venv/bin/activate
python src/run_pipeline_bundle.py \
  --config configs/lgbm_crypto_v9.yaml \
  --risk-config configs/lgbm_crypto_risk_v9.yaml \
  --summary-output data/processed/crypto_v9_summary.json
```

### 정책 비교

```bash
cd ml
source .venv/bin/activate
python src/compare_model_versions.py \
  --asset-type STOCK \
  --baseline v8 \
  --candidate v11
```

### Optuna

```bash
cd ml
source .venv/bin/activate
python src/tune_hyperparameters.py \
  --config configs/lgbm_stock_v11.yaml \
  --trials 20
```

## 5. 현재 자동화와의 관계

자동화 preset 정의는 `backend/services/ml_automation_service.py`를 기준으로 합니다.

현재 preset:

- `stock-v7-full`
- `crypto-v7-full`
- `stock-v8-full`
- `crypto-v8-full`
- `stock-v11-full`
- `crypto-v9-full`
- `kr-stock-v1-full`
- `us-stock-v1-full`

중요한 사실:

- 현재 운영 점검 기준은 `stock-v11-full`, `crypto-v9-full`, `kr-stock-v1-full`, `us-stock-v1-full`입니다.
- v7/v8 preset은 과거 실험 및 비교를 위해 코드에 남아 있습니다.
- 따라서 문서에서 "존재하는 preset"과 "운영 점검 기준 preset"을 구분해야 합니다.

## 6. 운영 산출물

### 모델 파일

```text
ml/models/lgbm_stock_signal_v11.joblib
ml/models/lgbm_stock_risk_v11.joblib
ml/models/lgbm_kr_stock_signal_v1.joblib
ml/models/lgbm_kr_stock_risk_v1.joblib
ml/models/lgbm_us_stock_signal_v1.joblib
ml/models/lgbm_us_stock_risk_v1.joblib
ml/models/lgbm_crypto_signal_v9.joblib
ml/models/lgbm_crypto_risk_v9.joblib
```

### 지표 파일

```text
ml/models/*.metrics.json
```

### 예측 파일

```text
ml/data/processed/*_predictions_lgbm_v*.csv
```

### 백테스트 파일

```text
ml/data/processed/*_backtest_up_only_v*.json
ml/data/processed/*_backtest_composite_v*.json
```

### 리포트

```text
ml/reports/latest_experiment_report.md
ml/reports/stock_v8_v11_comparison_20260630.md
```

### EC2 서빙 패키지

EC2에는 학습 데이터 전체를 올리지 않고 서빙 패키지만 업로드합니다.

```bash
python3 -m ml.src.export_serving_package \
  --asset-key kr_stock \
  --output-root ml/serving_packages \
  --no-predictions \
  --archive
```

패키지는 `manifest.json`, 상승 모델, risk 모델, config, metrics, summary를 포함합니다. raw 학습 데이터는 포함하지 않습니다.

## 7. API와 연결되는 필드

`GET /api/ml/predictions/active`는 예측 CSV를 바로 노출하지 않고, 운영 UI용 필드를 보강해 반환합니다.

대표 필드:

- `signal_grade`
- `reason_summary`
- `predicted_at`
- `staleness_minutes`
- `model_version`
- `recommendation_tier`
- `policy_block_reason`
- `policy_block_reason_labels`
- `market_breadth_5`
- `sector_strength_score`
- `volume_ratio_5`
- `adjusted_composite_spread`
- `long_entry_distance`

즉, 상세 페이지와 관리자 페이지는 단순 확률만이 아니라 정책 사유와 성능 스냅샷까지 함께 보여줄 수 있습니다.

## 8. 현재 문서에서 주의할 점

- 과거 문서처럼 "주식은 v7, 코인은 v7이 최신"이라고 적으면 현재 코드와 다릅니다.
- EC2 배포 문서에서 전체 `ml/` 디렉토리나 raw 학습 데이터를 업로드 대상으로 적으면 현재 운영 방식과 다릅니다.
- 작업 이력과 모델 레지스트리의 1차 저장소는 여전히 파일입니다.
  - `ml/data/ops/job_history.json`
  - `ml/data/ops/model_registry.json`
- Supabase의 `ml_dataset_jobs`, `ml_training_runs`, `ml_model_registry`는 동기화 대상입니다.

## 3분리 모델 자동화

주식 통합 모델은 안전망으로 유지하며, 신규 shadow 모델은 국내주식, 해외주식, 코인으로 분리해 자동 수집+학습한다.

| 모델 | 유니버스 | raw 파일 | config | 공시 피처 |
| --- | --- | --- | --- | --- |
| 국내주식 | `stock_kr_core_45` | `ml/data/raw/kr_stock_candles.csv` | `ml/configs/lgbm_kr_stock_v1.yaml` | DART 사용 |
| 해외주식 | `stock_us_core_45` | `ml/data/raw/us_stock_candles.csv` | `ml/configs/lgbm_us_stock_v1.yaml` | DART 미사용 |
| 코인 | `crypto_core_30` | `ml/data/raw/crypto_candles_30m.csv` | `ml/configs/lgbm_crypto_v9.yaml` | 미사용 |

교체 판단은 자동 serving 교체가 아니라 `promotion_candidate` 판정으로 남긴다. 관리자는 composite 순초과수익, 최대낙폭, risk AUC, risk 상위 10% precision을 확인한 뒤 serving 교체 여부를 결정한다.
