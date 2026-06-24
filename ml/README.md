# LightGBM 사전학습 파이프라인

이 디렉토리는 챗봇이 사용할 종목 신호 점수를 만들기 위한 오프라인 ML 파이프라인입니다. 초기 개발은 맥북 M2 로컬 Python 환경에서 진행하고, 데이터가 커지거나 반복 튜닝이 필요할 때 Colab을 학습 보조 환경으로 사용합니다.

## 1. 모델 분리 원칙

주식과 코인은 시장 구조가 다르므로 같은 모델로 묶지 않습니다.

```text
주식 모델:
- lgbm_stock_signal_v1
- 일봉 중심
- 3거래일 뒤 상승/하락 위험 예측

코인 모델:
- lgbm_crypto_signal_v1
- 1시간봉 또는 4시간봉 중심
- 4시간 뒤 상승/하락 위험 예측
```

LightGBM 결과는 매매 실행 명령이 아니라 상승 확률, 하락 위험 확률, 종합 신호 점수입니다. 실제 주문은 기존 Human-in-the-Loop 승인 흐름을 반드시 거쳐야 합니다.

## 2. 로컬 실행

```bash
cd ml
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

원천 캔들 파일을 준비합니다.

```text
ml/data/raw/stock_candles.csv
ml/data/raw/crypto_candles.csv
```

필수 컬럼은 다음과 같습니다.

```text
symbol,date,open,high,low,close,volume
```

선택 컬럼은 다음과 같습니다.

```text
exchange,asset_type,market_country,currency
```

주식 모델:

```bash
python src/build_features.py --config configs/lgbm_stock_v1.yaml
python src/train_model.py --config configs/lgbm_stock_v1.yaml
python src/predict.py --config configs/lgbm_stock_v1.yaml
```

코인 모델:

```bash
python src/build_features.py --config configs/lgbm_crypto_v1.yaml
python src/train_model.py --config configs/lgbm_crypto_v1.yaml
python src/predict.py --config configs/lgbm_crypto_v1.yaml
```

## 3. API 수집 CSV 생성

학습용 CSV는 백엔드 수집 스크립트로 생성합니다. CSV에는 캔들 데이터만 저장하고, 사용자 API Key나 계좌 정보는 절대 포함하지 않습니다.

코인 바이낸스 캔들은 공개 API라서 개인 API Key 없이 바로 수집할 수 있습니다.

```bash
python ../backend/scripts/export_training_candles.py \
  --asset-type CRYPTO \
  --exchange BINANCE \
  --symbols BTCUSDT,ETHUSDT \
  --interval 1h \
  --count 500 \
  --output data/raw/crypto_candles.csv
```

Toss 주식 캔들은 사용자별로 DB에 저장된 암호화 API Key를 사용합니다. 프론트엔드에서 로그인한 사용자의 Supabase access token을 백엔드에 전달하면, 스크립트가 `user_api_keys`에서 해당 사용자의 Toss Key를 읽고 백엔드 내부에서만 복호화합니다.

```bash
python ../backend/scripts/export_training_candles.py \
  --asset-type STOCK \
  --exchange TOSS \
  --symbols 005930,NVDA \
  --interval 1d \
  --count 200 \
  --auth-token "$SUPABASE_ACCESS_TOKEN" \
  --output data/raw/stock_candles.csv
```

국내 주식은 장 운영 시간과 Toss API 제공 범위의 영향을 받을 수 있으므로, 장중에는 위 명령으로 실제 수집을 확인하고 장외에는 실패 응답 또는 빈 데이터를 정상적으로 기록해 원인을 확인합니다.

## 4. Colab 사용 기준

Colab은 다음 상황에서만 사용합니다.

```text
- 코인 분봉 데이터가 커져 로컬 학습 시간이 길어질 때
- 여러 threshold와 horizon을 반복 튜닝할 때
- 팀원에게 노트북 결과를 공유해야 할 때
- 뉴스 감성분석 또는 딥러닝 모델로 확장할 때
```

## 5. 보안 원칙

사용자 개인 계좌 데이터, 주문 이력, API Key는 학습 데이터로 사용하지 않습니다. 학습 데이터는 공개 또는 서비스가 수집한 시장 데이터 중심으로 구성합니다.
