# STOCK 모델 버전 비교

## 비교표

| 버전 | 신호 모델 | 위험 모델 | ROC AUC | AP | CV ROC AUC | CV 상위10% | 상승전용 초과수익(순) | 상승전용 MDD | 복합 초과수익(순) | 복합 MDD | 복합 승률(순) | test_periods | top_n | 예측 포지션 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| v8 | lgbm_stock_signal_v8 | lgbm_stock_risk_v8 | 0.7663 | 0.7091 | 0.7025 | 0.4196 | 0.58% | -75.37% | 0.02% | -9.43% | 57.89% | 19 | 1 | HOLD:90 |
| v11 | lgbm_stock_signal_v11 | lgbm_stock_risk_v11 | 0.7759 | 0.7193 | 0.7229 | 0.4411 | 1.17% | -68.96% | 2.71% | -20.89% | 64.10% | 42 | 3 | HOLD:90 |

## 운영 판단

- 현재 비교 기준상 운영 후보는 `v11` 입니다.
- 복합 초과수익(순): 2.71%
- 복합 최대낙폭: -20.89%
- 복합 승률(순): 64.10%
- 최신 추천 티어 분포: HOLD:85, WATCH:5
- 최신 WATCH 후보: 271560, UNH, 302440, 207940, PANW
- 최신 차단 사유 상위: market_breadth:90, sector_strength:71, market_regime:68, sector_breadth:64

## 근거 파일

### v8
- metrics: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/models/lgbm_stock_signal_v8.metrics.json`
- composite backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_composite_v8.json`
- up_only backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_up_only_v8.json`
- predictions: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_predictions_lgbm_v8.csv`

### v11
- metrics: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/models/lgbm_stock_signal_v11.metrics.json`
- composite backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_composite_v11.json`
- up_only backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_up_only_v11.json`
- predictions: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_predictions_lgbm_v11.csv`
