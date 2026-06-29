# STOCK 모델 버전 비교

## 비교표

| 버전 | 신호 모델 | 위험 모델 | ROC AUC | AP | CV ROC AUC | CV 상위10% | 상승전용 초과수익(순) | 상승전용 MDD | 복합 초과수익(순) | 복합 MDD | 복합 승률(순) | test_periods | top_n | 예측 포지션 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| v8 | lgbm_stock_signal_v8 | lgbm_stock_risk_v8 | 0.7663 | 0.7091 | 0.7025 | 0.4196 | 0.58% | -75.37% | 0.02% | -9.43% | 57.89% | 19 | 1 | HOLD:90 |
| v9 | lgbm_stock_signal_v9 | lgbm_stock_risk_v9 | 0.7623 | 0.7097 | 0.6998 | 0.4343 | 1.18% | -80.88% | -1.40% | -11.89% | 45.00% | 20 | 1 | HOLD:90 |
| v10 | lgbm_stock_signal_v10 | lgbm_stock_risk_v8 | 0.7623 | 0.7097 | 0.6998 | 0.4343 | 1.18% | -80.88% | -0.37% | -9.43% | 60.00% | 20 | 1 | HOLD:90 |

## 운영 판단

- 현재 비교 기준상 운영 후보는 `v8` 입니다.
- 복합 초과수익(순): 0.02%
- 복합 최대낙폭: -9.43%
- 복합 승률(순): 57.89%

## 근거 파일

### v8
- metrics: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/models/lgbm_stock_signal_v8.metrics.json`
- composite backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_composite_v8.json`
- up_only backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_up_only_v8.json`
- predictions: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_predictions_lgbm_v8.csv`

### v9
- metrics: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/models/lgbm_stock_signal_v9.metrics.json`
- composite backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_composite_v9.json`
- up_only backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_up_only_v9.json`
- predictions: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_predictions_lgbm_v9.csv`

### v10
- metrics: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/models/lgbm_stock_signal_v10.metrics.json`
- composite backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_composite_v10.json`
- up_only backtest: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_backtest_up_only_v10.json`
- predictions: `/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/ml/data/processed/stock_predictions_lgbm_v10.csv`
