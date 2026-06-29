# 주식 v11 뉴스 raw + Selection Cap 업데이트 리포트

- 생성일: 2026-06-29
- 목적: 실제 뉴스 raw 연동과 US 편향 억제용 market/sector cap 적용 결과를 점검

## 1. 적용 내용

- `backend/scripts/export_news_features.py`
  - Supabase `news_articles`를 ML raw CSV로 export
  - 빈 `symbol` 기사도 `company_name`, `raw_payload.query_text`, 기사 제목/요약 내 종목명으로 심볼 복원
- `ml/src/policy_utils.py`
  - `selection_policy` 기반 `market/sector/unknown sector` cap 추가
- `ml/src/backtest_signals.py`
  - 백테스트 선택 단계에서 cap 적용
- `ml/src/tune_stock_policy.py`
  - cap 파라미터를 Optuna 탐색 공간에 포함

## 2. 뉴스 raw export 결과

- 기사 원본 수: `1000`
- `news_features.csv` 행 수
  - 변경 전: `13`
  - 변경 후: `39`
- `stock_event_features.csv` 행 수: `18090`

### 관찰

- 종목 매핑은 늘었지만, 실제 뉴스 날짜 범위는 `2026-06-21 ~ 2026-06-24` 중심이라 아직 짧다.
- 즉, 현재 개선은 "연결 성공 + 종목 매핑 보강" 단계이고, "충분한 장기 뉴스 히스토리 확보" 단계는 아직 아니다.

## 3. v11 재학습 결과

### 신호 모델

- ROC AUC: `0.78295`
- Average Precision: `0.72048`
- 시계열 CV ROC AUC: `0.72458`
- 시계열 상위 10% 적중: `0.41265`

### 위험 모델

- ROC AUC: `0.59752`
- Average Precision: `0.46705`
- 시계열 CV ROC AUC: `0.55131`
- 시계열 상위 10% 적중: `0.27550`

## 4. 기존 v11 대비 변화

### 분류 성능

- 신호 ROC AUC: `0.78134 -> 0.78295` 상승
- 신호 AP: `0.71856 -> 0.72048` 상승
- 위험 ROC AUC: `0.59369 -> 0.59752` 상승
- 위험 CV ROC AUC: `0.54820 -> 0.55131` 상승

### 현재 운영 설정 백테스트 (`top_n=1`)

- 복합 초과수익(순): `0.03442 -> 0.02365` 하락
- 복합 승률(순): `0.57895 -> 0.66667` 상승
- 복합 최대낙폭: `-0.28592 -> -0.28470` 소폭 개선

## 5. cap 민감도 테스트 (`top_n=2`)

### cap 미적용

- 복합 초과수익(순): `0.01525`
- 복합 승률(순): `0.51429`
- 복합 최대낙폭: `-0.36359`
- 선택 행 수: `35`

### cap 적용

- 복합 초과수익(순): `0.03030`
- 복합 승률(순): `0.68182`
- 복합 최대낙폭: `-0.25798`
- 선택 행 수: `22`

### 해석

- `top_n=2` 이상에서는 cap이 실제로 효과가 있었다.
- 다만 현재 Optuna 결과가 `top_n=1`이라 운영 설정에서는 cap 영향이 거의 없다.

## 6. 최종 판단

- 실제 뉴스 raw 연결은 성공했다.
- 하지만 아직 뉴스 히스토리 길이와 종목 매핑 범위가 부족해서 수익률 개선까지 바로 이어지지는 않았다.
- market/sector cap은 구조적으로 유효하며, `top_n>1` 운영에서 더 큰 가치가 있다.

## 7. 다음 우선순위

1. 뉴스 수집기에서 일반 키워드(`AI`, `반도체`, `금리`) 비중을 줄이고 종목 직접 매핑 가능한 쿼리를 늘린다.
2. `news_articles` 장기 backfill 또는 과거 뉴스 공급원을 추가해 최소 수개월 이상 종목별 뉴스 히스토리를 확보한다.
3. `SYMBOL_METADATA`의 market/sector 누락을 줄여 `UNKNOWN` 선택 비중을 낮춘다.
4. 운영 정책을 `top_n=1` 고정으로 둘지, `top_n=2 + cap`으로 전환할지 별도 비교 실험을 진행한다.

## 8. 다음 턴 추가 반영

- `news_query_planner.py`
  - 정적 종목 기반 NAVER 쿼리 추가
  - watchlist 종목도 `실적`, `공시`, `전망`, `수주` 등으로 다변화
  - 과도하게 일반적인 `AI`, `인공지능` 정적 키워드는 제거
- `predict.py`
  - 예측 CSV에 `market_regime_state`, `policy_blocked`, `policy_block_reason`, `override_applied` 추가
- `policy_utils.py`
  - `override_policy` 지원 추가
  - 매우 강한 신호만 제한적으로 `risk_off` 차단을 우회 가능하게 설정
- `lgbm_stock_v11.yaml`
  - `backtest.top_n=2`
  - `override_policy` 활성화

## 9. 현재 운영 상태

### 최신 예측 파일

- 이전: `HOLD 90`
- 현재: `HOLD 81`, `LONG 9`

### 주요 차단 사유

- 대부분 `market_breadth|sector_breadth|sector_strength`
- 즉, 현재 막히는 핵심 원인은 뉴스가 아니라 시장 breadth/sector breadth 필터다.

### override로 통과한 상위 후보 예시

- `MU`
- `009150`
- `034730`
- `000660`
- `LLY`

## 10. 현재 설정 기준 복합 백테스트

- 설정: `top_n=2 + selection cap + override_policy`
- 복합 초과수익(순): `0.00601`
- 복합 승률(순): `0.58571`
- 복합 최대낙폭: `-0.57111`

### 해석

- 라이브 추천 가용성은 좋아졌지만, 백테스트 성과는 직전 `top_n=2 cap only` 민감도 테스트보다 약하다.
- 원인은 override가 `risk_off` 구간 후보까지 더 통과시키면서 선택 수가 늘고, drawdown이 커졌기 때문이다.
- 따라서 override는 "운영 관찰용"으로는 의미가 있지만, 지금 수치만 보면 아직 최종 운영 정책으로 확정하기는 이르다.
