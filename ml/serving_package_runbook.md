# ML 서빙 패키지 배포 런북

## 목적

EC2 배포 시 학습용 raw 데이터와 전체 processed 산출물을 올리지 않고, 실제 서빙에 필요한 모델 패키지만 업로드한다.

서빙 패키지는 다음 파일만 포함한다.

- 상승 모델 `joblib`
- 리스크 모델 `joblib`
- 모델 config YAML
- 상승/리스크 metrics JSON
- summary JSON
- 선택 옵션: 예측 CSV 스냅샷
- `manifest.json`

## 패키지 생성

예측 CSV 스냅샷 없이 모델 서빙 파일만 생성한다.

```bash
python3 -m ml.src.export_serving_package \
  --asset-key kr_stock \
  --output-root ml/serving_packages \
  --no-predictions \
  --archive
```

US 모델:

```bash
python3 -m ml.src.export_serving_package \
  --asset-key us_stock \
  --output-root ml/serving_packages \
  --no-predictions \
  --archive
```

코인 모델:

```bash
python3 -m ml.src.export_serving_package \
  --asset-key crypto \
  --output-root ml/serving_packages \
  --no-predictions \
  --archive
```

챗봇/대시보드가 사전 생성 예측 CSV를 바로 읽어야 하는 배포라면 `--no-predictions`를 제거한다.

## EC2 업로드 대상

생성된 `.tar.gz` 하나만 EC2에 업로드한다.

예:

```text
ml/serving_packages/kr_stock-lgbm_kr_stock_signal_v1.tar.gz
```

EC2에서 압축 해제 후 `manifest.json`을 기준으로 모델 파일과 config를 로드한다.

## manifest 확인 포인트

`manifest.json`에서 다음 항목을 확인한다.

- `asset_key`
- `model_version`
- `risk_model_version`
- `policy_version`
- `data_end_date`
- `feature_columns`
- `prediction_policy`
- `files[].sha256`
- `runtime_contract.fail_closed_when`

`feature_columns`가 비어 있거나 `files`의 필수 파일이 누락되면 배포하지 않는다.

## 운영 원칙

- EC2에는 raw 학습 데이터와 전체 processed 디렉터리를 올리지 않는다.
- 모델 입력은 `manifest.feature_columns` 순서를 그대로 따른다.
- 추천 정책은 `manifest.prediction_policy`를 기준으로 해석한다.
- `manifest.data_end_date`가 오래된 패키지는 live serving으로 승격하지 않는다.
- 새 모델은 먼저 SHADOW 성격으로 배포하고, 운영 성능 확인 후 LIVE로 승격한다.
