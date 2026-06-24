# ML 자동화 시스템 구현 계획

이 문서는 현재 수동 실험 파이프라인을, 추후 **백엔드에서 데이터 수집 -> 피처 생성 -> 학습 -> 평가 -> 추천 버전 반영**까지 자동화하는 설계 초안을 정리한 문서입니다.

---

## 1. 목표

최종 목표는 다음 4단계를 자동화하는 것입니다.

1. **데이터셋 자동 수집**
2. **모델 자동 학습 및 평가**
3. **버전별 성능 비교 및 추천 버전 선정**
4. **백엔드 예측 API가 추천 버전을 자동 사용**

---

## 2. 현재 상태

현재 구현된 범위:

- Toss/Binance 기반 캔들 수집 스크립트
- v1~v6 설정 파일 기반 학습 파이프라인
- metrics / predictions / backtest 결과 파일 생성
- 관리자 페이지에서 버전별 결과 비교
- 백엔드가 버전별 결과를 읽고 추천 버전 계산
- 관리자 페이지에서 백엔드 학습 작업 직접 실행
- 파일 기반 작업 이력 저장: `ml/data/ops/job_history.json`
- 유니버스 프리셋 기반 대량 수집 준비: `ml/data/reference/training_universes.json`
- v7 설정 파일 추가 완료

현재 미구현 범위:

- 주기적 자동 수집 스케줄러
- 자동 학습 트리거
- 실험 이력 DB 저장
- 추천 버전 승인 워크플로우
- 작업 이력의 Supabase 영속화

---

## 3. 권장 자동화 구조

```text
Scheduler / Worker
  -> dataset job 생성
  -> 캔들 수집
  -> 외부 피처 수집
  -> feature build
  -> model train
  -> evaluate / backtest
  -> 결과 DB 저장
  -> 추천 버전 계산
  -> 관리자 승인 후 서비스 반영
```

---

## 4. Supabase 연동 역할

### 4.1 계속 Supabase를 써야 하는 부분

- `user_api_keys`
  - 로그인 사용자별 Toss API Key 보관
  - 백엔드 내부에서만 복호화

- 실험 관리용 신규 테이블(추가 예정)
  - `ml_dataset_jobs`
  - `ml_training_runs`
  - `ml_model_registry`
  - `ml_feature_sources`

### 4.2 왜 DB 기록이 필요한가

지금은 파일이 결과의 진실 원천이지만, 자동화 단계에선 아래가 필요합니다.

- 어떤 데이터셋으로 학습했는지
- 실패한 심볼이 무엇이었는지
- 어떤 버전이 추천되었는지
- 누가 운영 반영 승인했는지

---

## 5. 구현 단계 제안

### Phase A. 자동 수집 작업 테이블 추가

신규 테이블 예시:

```text
ml_dataset_jobs
- id
- asset_type
- exchange
- preset_name
- interval
- count
- chunk_size
- chunk_index
- status
- started_at
- finished_at
- failure_count
- output_path
- failure_output_path
```

목적:

- 단순 스크립트 실행이 아니라 작업 단위 추적
- 실패/성공 이력 저장

### Phase B. 자동 학습 작업 테이블 추가

```text
ml_training_runs
- id
- asset_type
- config_name
- model_version
- dataset_job_id
- status
- metrics_json
- backtest_json
- started_at
- finished_at
```

목적:

- 수동 실험과 자동 실험을 같은 형식으로 누적
- 관리자 페이지에서 파일이 아니라 DB 기준 이력 비교 가능

### Phase C. 모델 레지스트리

```text
ml_model_registry
- id
- asset_type
- model_version
- model_path
- metrics_path
- summary_path
- is_latest
- is_recommended
- is_serving
- approved_by
- approved_at
```

목적:

- 최신 버전, 추천 버전, 실제 서비스 버전 분리
- 사람이 승인한 버전만 서비스 사용

### Phase D. 워커 자동화

권장 방식:

- Flask 웹 서버와 분리된 백그라운드 워커 프로세스
- cron 또는 별도 스케줄러로 호출
- 예시 주기:
  - 주식 일봉: 평일 장 마감 후 1회
  - 코인 1시간봉: 하루 1~2회

---

## 6. 백엔드 자동화 API 초안

### 6.1 데이터셋 작업 생성

`POST /api/ml/jobs/dataset`

역할:

- preset, interval, count, chunk 기준 수집 작업 생성
- 작업 상태를 DB에 기록

현재 상태:

- 아직 별도 `/api/ml/jobs/dataset` 엔드포인트는 없고
- `POST /api/ml/export-candles` 호출 시 파일 기반 job history에 `dataset_export`로 기록합니다.
- 현재는 `preset`, `chunk_size`, `chunk_index`, `include_macro` 값을 함께 받아 대량 수집 실험을 준비할 수 있습니다.
- `POST /api/ml/jobs/full-run` 엔드포인트를 통해 preset 기준 데이터셋 수집과 학습을 순차 실행할 수 있습니다.

### 6.2 학습 작업 생성

`POST /api/ml/jobs/train`

역할:

- 특정 config 기준으로 feature build -> train -> backtest 실행
- 결과를 DB와 파일 양쪽에 저장

현재 상태:

- 구현 완료
- 백엔드가 `ml/.venv/bin/python`으로 `run_pipeline_bundle.py`를 실행합니다.
- 작업 결과는 `ml/data/ops/job_history.json`에 저장됩니다.
- Supabase `ml_training_runs` 테이블이 있으면 best-effort 방식으로 동기화합니다.
- 학습 성공 시 Supabase `ml_model_registry` 테이블도 best-effort 방식으로 최신/추천 플래그를 갱신합니다.
- 동시에 파일 기반 레지스트리 `ml/data/ops/model_registry.json`도 함께 갱신합니다.
- 학습 성공 시 최신 summary JSON을 기준으로 Markdown 실험 리포트를 자동 생성하고, `ml/reports/`와 `latest_experiment_report.md`를 함께 갱신합니다.

### 6.3 모델 레지스트리 조회

`GET /api/ml/registry`

역할:

- 관리자 페이지에서 실험 이력과 서비스 반영 상태 조회

현재 상태:

- 구현 완료
- Supabase `ml_model_registry` 테이블이 있으면 우선 조회하고, 없으면 파일 기반 결과와 `ml/data/ops/model_registry.json`을 fallback으로 사용합니다.
- 관리자 페이지에서 주식/코인 레지스트리 상태를 별도 패널로 확인할 수 있습니다.
- `GET /api/ml/model-results`도 레지스트리의 `serving/recommended/latest` 상태를 함께 반영해 관리자 화면의 기본 선택 버전에 사용합니다.
- `GET /api/ml/readiness`로 키 저장 여부, 원천 CSV, 외부 피처, serving 상태를 운영 준비 체크 용도로 조회할 수 있습니다.
- `GET /api/ml/active-model?asset_type=STOCK|CRYPTO`로 실제 백엔드가 우선 사용할 활성 모델 선택 결과를 조회할 수 있습니다.
- `POST /api/ml/report`로 현재 summary JSON과 serving 상태를 기준으로 Markdown 실험 리포트를 생성할 수 있습니다.
- `GET /api/ml/reports`로 최근 생성된 Markdown 실험 리포트 목록을 조회할 수 있습니다.

### 6.4 추천 버전 승인

`POST /api/ml/registry/activate`

역할:

- 추천 버전 중 하나를 서비스 버전으로 승격
- 즉시 예측 API가 해당 버전을 사용

현재 상태:

- 구현 완료
- 관리자 페이지 레지스트리 패널에서 `서비스 반영` 버튼으로 호출 가능합니다.
- Supabase 테이블이 없더라도 파일 기반 레지스트리에서 `is_serving` 상태를 유지합니다.
- 현재는 `is_serving` 플래그를 기록하는 단계이며, 추후 예측 API가 이 플래그를 우선 사용하도록 연결하면 완전한 serving registry가 됩니다.

### 6.5 풀 파이프라인 자동 실행

`POST /api/ml/jobs/full-run`

역할:

- 사전 정의된 automation preset을 읽음
- 데이터셋 수집 수행
- 학습/백테스트 수행
- 작업 이력과 모델 레지스트리 동기화

현재 상태:

- `stock-v7-full`, `crypto-v7-full` 프리셋 구현 완료
- 관리자 페이지에서 버튼으로 호출 가능
- full-run 성공 시에도 학습 단계와 동일하게 최신 Markdown 실험 리포트를 자동 생성합니다.

---

## 7. 추천 버전 선정 로직

현재 추천 기준은 파일 기반이며 아래 순서입니다.

1. `composite excess_return_net`
2. `up_only excess_return_net`
3. `time_series_cv_average.roc_auc`
4. `risk time_series_cv_average.roc_auc`
5. 버전 번호

자동화 이후에도 기본 방향은 유지하되, 아래 보완이 필요합니다.

- 최소 샘플 수 미달 버전 제외
- `max_drawdown_net` 너무 큰 버전 제외
- 최근 2~3회 반복 실행에서 일관되게 좋은 버전 우선

---

## 8. 운영 안전 장치

- 자동화는 **데이터셋 생성과 학습까지만 자동**
- **서비스 반영은 관리자 승인 후 활성화**
- 추천 버전과 실제 서비스 버전은 반드시 분리
- 학습 실패 시 기존 서비스 버전 유지
- 사용자 API Key는 작업 로그에 남기지 않음

---

## 9. 다음 구현 우선순위

1. `ml_dataset_jobs`, `ml_training_runs`, `ml_model_registry` 스키마 설계
2. 백엔드 dataset job / train job API 추가
3. 워커 프로세스 분리
4. 관리자 페이지에 작업 이력 탭 추가
5. 추천 버전 승인 버튼 추가
6. 비교 리포트 JSON/API 추가 (`compare_experiments.py` 기반)

---

## 10. 현실적인 결론

지금 단계에서 가장 중요한 것은 “완전 자동화”보다 아래 3가지를 먼저 안정화하는 것입니다.

1. 데이터셋 수집 실패를 추적할 수 있어야 함
2. 버전별 비교 기준이 파일과 UI에 일관되게 보여야 함
3. 추천 버전과 서비스 버전이 분리되어야 함

이 3가지를 먼저 잡아야 이후 자동 학습 시스템이 들어와도 운영이 흔들리지 않습니다.

추가로 실제 실행 순서는 `ml/live_run_checklist.md`를 기준 문서로 사용합니다.
