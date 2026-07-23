# AI 위탁 ML 운영 인수인계 (2026-07-23)

## 현재 운영 구조

- 로컬 Mac: 코인 v10 예측 생성, 주간 재학습, 릴리스 패키지 생성, AWS 업로드만 담당한다.
- AWS EC2: API, 조건매매, 보유 포지션의 손절·익절·비상정지, 주문 대사만 담당한다.
- AWS에서는 `WORKER_MODE=trading`으로 ML 자동화 스케줄러가 시작되지 않는다.
- AWS에서 `ML_RELEASE_REQUIRED=true`이므로 검증된 `ml/releases/current/<asset>` 릴리스가 없거나 만료되면 신규 매수는 보류된다.
- 코인 릴리스는 생성 후 90분, 주식 릴리스는 생성 후 36시간을 넘으면 신규 매수를 차단한다. 보유 포지션 매도 보호는 계속 동작한다.

## 중복 실행 방지

- `AI_FUND_TRADING_ENABLED`: AI 위탁 매매 스케줄러의 전체 스위치다. 현재 AWS는 `false`다.
- `AI_FUND_EXECUTION_ENABLED`: 실제 주문을 낼 실행 노드만 명시적으로 허용한다. 로컬은 항상 `false`, AWS만 `true`로 설정해야 한다.
- `scripts/run_and_deploy_local_ml.sh`는 `ml/local_runtime/<asset>.lock` 디렉터리 잠금을 사용한다. 같은 자산의 예측·재학습·수동 실행이 겹치면 뒤 작업은 성공 코드로 건너뛴다.
- launchd는 코인 예측만 즉시 실행 및 30분 간격으로 실행한다. 코인 재학습과 국내·미국 주식 예측은 `RunAtLoad` 없이 예약 시점에만 실행한다.

## 릴리스 흐름

1. `scripts/run_local_ml_serving.py --asset crypto`가 로컬 v10 모델로 예측 CSV를 갱신한다.
   - 매 실행 전 248개 유니버스의 최신 30분봉 240개를 수집·중복 병합하며, 80% 미만 수집 성공 시 릴리스를 만들지 않는다.
2. 모델, 위험 모델, 설정, 예측 CSV를 `ml/local_releases/releases/<asset>/<timestamp>`에 복사하고 SHA-256 매니페스트를 작성한다.
3. `scripts/deploy_ml_release_aws.sh <release-dir>`가 AWS에 업로드한다.
4. AWS `scripts/activate_ml_release.py`가 파일 해시를 재검증한 뒤 상대 심볼릭 링크 `ml/releases/current/<asset>`를 원자적으로 교체한다.
5. Docker API·워커는 호스트 `ml/releases`를 읽기 전용으로 마운트해 현재 릴리스만 읽는다.
   - 매니페스트의 `prediction_data_at`가 코인 기준 90분을 넘으면 생성 시각이 새로워도 신규 매수를 차단한다.

## 검증된 상태

- 로컬에서 `lgbm_crypto_signal_v10.joblib`, `lgbm_crypto_risk_v10.joblib`, 30분 원본 캔들로 코인 v10 릴리스를 생성했다.
- 생성 릴리스는 `lgbm_crypto_signal_v10`, 165개 예측 행과 필수 파일 SHA-256을 포함했다.
- AWS 컨테이너에서 현재 코인 릴리스가 `READY`로 판정되고, 확신도 30% 기준 후보 조회가 성공하는 것을 확인했다.
- AWS AI 위탁 주문 스케줄러는 현재 `AI_FUND_TRADING_ENABLED=false`라 실행되지 않는다.
- BTT 실제 체결 주문은 `FILLED` 한 건만 남겼고, 거래소 주문 ID가 없는 `NEEDS_REVIEW` 고아 원장 행은 삭제했다.
- 동일 종목의 `NEEDS_REVIEW` 또는 미확정 BUY 원장이 있으면 새 BUY 주문을 차단하는 테스트와 코드를 추가했다.

## 숏 모델 점검 결과

- 존재: `ml/models/lgbm_crypto_short_v1.joblib`, `ml/models/lgbm_crypto_short_v1.metrics.json`.
- 학습 번들: `ml/src/run_pipeline_bundle.py --short-config ...`는 숏 모델 학습, 평가, `short_only` 비용 반영 백테스트를 실행한다.
- 연구 성능 화면: `backend/services/ai_fund_crypto_short_performance.py`가 metrics와 `crypto_backtest_short_v1.json`을 읽어 운영 검토 상태를 만든다.
- 미완료: 실시간 `ml/src/predict.py`는 숏 전용 joblib을 로드하지 않는다. 현재 CSV의 `SHORT` 표기는 위험 모델 확률 기반이며, 숏 수익 모델의 확률이 아니다.
- 미완료: AI 위탁 스케줄러는 현물 코인 후보의 `LONG`만 주문하고, 바이낸스 USD-M 선물의 `OPEN_SHORT` 실행 경로로 연결하지 않는다.

## 다음 담당자 우선 작업

1. `predict.py`에 `--short-model` 입력과 `short_probability`, `short_model_version` 열을 추가한다.
2. 코인 v10 설정에 숏 모델 경로·진입 임계값을 명시하고, 로컬 릴리스 패키지에 숏 모델·숏 설정·숏 예측을 포함한다.
3. 바이낸스 선물 전용 후보 선별과 `OPEN_SHORT` TradeIntent를 구현한다. 현물 Coinone/Binance Spot에는 SHORT를 절대 전송하지 않는다.
4. 수수료·펀딩비·레버리지·청산가·최대 손실·포지션 모드 검증을 모두 통과한 경우에만 선물 주문을 허용한다.
5. PAPER/CANARY에서 숏 주문 원장·체결·포지션 대사·강제 청산·비상정지를 검증한 뒤에만 `LIVE`를 고려한다.

## 운영 명령

```bash
# 로컬 예측 생성과 AWS 배포
./scripts/run_and_deploy_local_ml.sh --asset crypto

# 수동 재학습 후 AWS 배포
./scripts/run_and_deploy_local_ml.sh --asset crypto --train

# launchd 등록 상태
launchctl print "gui/$(id -u)/com.teamproject.ml.crypto.predict"
launchctl print "gui/$(id -u)/com.teamproject.ml.crypto.train"
```

## 실거래 재개 전 확인 목록

- AWS `AI_FUND_TRADING_ENABLED=true`
- AWS `AI_FUND_EXECUTION_ENABLED=true`
- AWS `ML_RELEASE_REQUIRED=true`
- AWS 컨테이너에서 코인 릴리스 상태 `READY`
- 거래소 IP 허용, API 권한, 잔고, 주문 최소 단위 확인
- 미확정 BUY/SELL 주문이 없는지 확인
- 대시보드에서 릴리스 생성 시각과 후보 수 확인
