# Toss 메인 AI 트레이딩 프로젝트

이 저장소는 `React + Vite` 프론트엔드, `Flask` 백엔드, `Supabase` DB/Auth, `LightGBM` 기반 ML 파이프라인으로 구성된 트레이딩 보조 시스템입니다.
현재 코드는 Toss 주식, KIS 레거시 주식, Coinone 코인, Binance 현물/Usd-M 선물 데이터 조회/주문 보조/조건감시 자동매도/ML 운영과 인증 기반 트레이딩 챗봇 오케스트레이터를 포함합니다. 챗봇은 로그인 사용자만 사용할 수 있으며, 사용자별 대화 이력은 Supabase에 격리 저장됩니다.

## 현재 구현 범위

- 프론트엔드
  - 대시보드, 자산 탭, 뉴스 화면, 설정 화면
  - 종목 상세 페이지 차트/호가/체결/주문 사전검증
  - 코인원 가상자산 상세 페이지 지정가 주문 UI
  - 조건감시 익절/손절 등록 및 `매도 제안만 생성`/`조건 도달 시 자동 매도` 선택 UI
  - ML 운영 콘솔과 활성 신호 확인 UI
- 백엔드
  - `home`, `keys`, `ml`, `news`, `trade`, `transfer` Blueprint API
  - `chatbot` Blueprint API: Supabase Auth 검증, 로그인 사용자별 대화 이력 복원·저장, 도구 호출 및 LLM 응답
  - 챗봇 매매 제안은 `trade_proposals.status=PENDING`으로만 생성되며, 승인 카드에서만 주문 승인/거절 가능
  - 환경 미지정 챗봇 주문 제안은 MOCK이 기본이며 REAL은 사용자가 명시한 경우에만 허용됩니다.
  - 사전검증 실패, API 키 미등록, 지원하지 않는 주문유형, 실거래 10만 원 초과 요청은 PENDING 제안을 생성하지 않습니다.
  - 승인 요청은 Supabase RPC로 원자 선점되어 같은 `proposal_id`가 중복 주문으로 전송되지 않습니다.
  - 챗봇 SSE 오류는 사용자에게 `request_id`를 제공하고 서버 로그는 같은 `request_id`로 조회합니다.
  - 챗봇 사용량은 Supabase `chatbot_usage_counters` RPC로 워커 간 공유 집계
  - Toss/KIS/Coinone/Binance 클라이언트
  - 코인원 계좌 잔고 조회, 현재가 조회, 지정가 주문, 미체결 주문 취소
  - 바이낸스 현물/Usd-M 선물 주문 사전검증, 테스트 주문 검증, 미체결 주문 관리
  - 조건감시 자동/반자동 매도 워커
  - 코인원에서 바이낸스로 가상자산 출금 사전검증, 사용자 승인, 상태 추적
  - 뉴스 수집/요약
  - ML 자동 수집/학습 스케줄러, 승격 검증, serving 감사
- ML
  - 주식 신호 모델: `v1` ~ `v11`
  - 주식 위험 모델: `v1` ~ `v11`
  - 코인 신호/위험 모델: `v1` ~ `v8`
  - 예측 CSV, 백테스트 JSON, 모델 레지스트리 파일 생성

## 현재 저장소 기준 핵심 디렉토리

```text
teamproject/
├── backend/                  # Flask API Gateway 및 worker
├── frontend/                 # React + Vite UI
├── ml/                       # LightGBM 학습/예측 파이프라인
├── supabase/                 # Supabase 설정 및 마이그레이션
├── design.md                 # UI 디자인 규칙
├── database_specification.md # 코드가 실제 참조하는 DB 문서
├── project_structure.md      # 실제 디렉토리 구조 문서
└── system_workflow.md        # 시스템 흐름 문서
```

자세한 구조는 [project_structure.md](/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/project_structure.md:1)를 참고합니다.

## 실행 방법

### 1. 백엔드

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

- 기본 포트: `http://localhost:5050`
- 권장 운영 방식:
  - API Gateway: `backend/app.py`
  - 스케줄러 전용 프로세스: `backend/worker.py`
- 기본 설정상 `SCHEDULER_RUN_IN_GATEWAY=false` 이므로, 스케줄러 운영은 `worker.py`를 별도로 띄우는 구조가 기준입니다.
- 코인원 실주문은 현재 지정가 주문만 연결되어 있으며, 시장가 주문은 API 정책 검증 전까지 차단합니다.
- 조건감시 자동/반자동 매도는 기본 설정상 `AUTO_TRADING_RULES_ENABLED=false`입니다. 실제 감시를 켜려면 `backend/.env`에서 이 값을 `true`로 바꾸고 `worker.py`를 실행해야 합니다.
- 전체 사용자 미완료 주문 상태 동기화는 기본 설정상 `OPEN_ORDER_STATUS_SYNC_ENABLED=false`입니다. 켜면 worker가 KIS/코인원/바이낸스/바이낸스 선물의 `APPROVED`, `ORDERED`, `OPEN`, `PARTIALLY_FILLED`, `MODIFIED` 주문만 주기적으로 확인해 `trade_proposals` 상태를 보정합니다.

### 2. 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

- 기본 포트: `http://localhost:5173`
- 루트에서도 아래 래퍼 스크립트를 사용할 수 있습니다.

```bash
npm run dev
npm run build
```

### 3. ML 환경

```bash
cd ml
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

현재 기준 대표 실행 예시는 다음과 같습니다.

```bash
python src/run_pipeline_bundle.py \
  --config configs/lgbm_stock_v11.yaml \
  --risk-config configs/lgbm_stock_risk_v11.yaml \
  --summary-output data/processed/stock_v11_summary.json
```

```bash
python src/run_pipeline_bundle.py \
  --config configs/lgbm_crypto_v8.yaml \
  --risk-config configs/lgbm_crypto_risk_v8.yaml \
  --summary-output data/processed/crypto_v8_summary.json
```

## 주요 API

### 홈/시장

- `POST /api/home/market`
- `POST /api/home/overview`
- `GET /api/market/rankings`
  - `asset_type=STOCK|CRYPTO`, `region`, `ranking`, `limit` 쿼리를 받아 홈 더보기 화면용 최대 100개 랭킹을 반환합니다.
- `POST /api/market/kis/sync`
- `POST /api/dashboard/balance`

### 키 관리

- `GET /api/keys/status`
- `POST /api/keys/save`
- `POST /api/keys/toss/accounts`
- `POST /api/keys/test`

### 거래/상세 페이지

- `POST /api/trade/precheck`
- `POST /api/trade/order`
- `POST /api/trade/order/cancel`
- `POST /api/trade/order/modify`
- `POST /api/trade/order/cancel-replace`
- `POST /api/trade/orders/sync-status`
- `POST /api/trade/estimated-holdings`
- `GET /api/chart/candles`
- `GET /api/chart/orderbook`
- `GET /api/chart/trades`
- `GET /api/stocks/warnings`
- `GET /api/symbol/lookup`
- `GET /api/symbol/search`

### 가상자산 이동

- `GET /api/transfer/binance/deposit-address`
- `GET /api/transfer/coinone/deposit-address`
- `POST /api/transfer/withdraw/precheck`
- `POST /api/transfer/withdraw/approve`
- `GET /api/transfer/withdraw/status`

현재 출금 플로우는 대시보드 자산 탭에서 코인원 → 바이낸스 이동과 XRP 기준 바이낸스 → 코인원 이동을 지원합니다. 사전검증은 도착 거래소 입금 주소/Tag 일치 여부, 출금 가능 수량, 최소 출금 수량, 출금 수수료, 예상 수령 수량을 함께 반환합니다. 실제 출금은 사전검증 후 사용자가 최종 승인 체크를 완료했을 때만 실행됩니다.

### 뉴스

- `GET /api/news`
- `POST /api/news/sync`
  선택적으로 `{ "symbol": "...", "display_name": "...", "market": "DOMESTIC|GLOBAL", "asset_type": "STOCK|CRYPTO" }` 본문을 보내면 해당 종목만 즉시 수집할 수 있습니다.
- `POST /api/news/summaries/ensure`

현재 뉴스 수집 공급원은 `NAVER`와 `FINNHUB`입니다. 문서상 과거에 언급된 Tavily 수집은 현재 코드 기준 기본 경로가 아닙니다.

### 지식/Obsidian 메모리

- `POST /api/knowledge/obsidian/sync-note`
  - Obsidian 플러그인이 현재 Markdown 노트를 앱으로 동기화합니다.
  - `vault_name`, `file_path`, `content`, `modified_at`를 받아 `user_knowledge_notes`에 사용자별로 저장합니다.
  - 저장된 노트 본문은 즉시 `knowledge_chunks`로 분할되며, 각 chunk는 `embedding_status=PENDING` 상태로 저장됩니다.
- `GET /api/knowledge/obsidian/auto-memory`
  - 앱/챗봇이 수집한 `user_memory_facts`를 Obsidian 자동메모리 marker에 넣기 좋은 배열 형태로 반환합니다.

### ML 운영

- `POST /api/ml/export-candles`
- `GET /api/ml/jobs`
- `POST /api/ml/jobs/train`
- `POST /api/ml/jobs/tune`
- `GET /api/ml/automation/presets`
- `POST /api/ml/jobs/full-run`
- `GET /api/ml/model-results`
- `GET /api/ml/registry`
- `POST /api/ml/registry/activate`
- `GET /api/ml/readiness`
- `GET /api/ml/data-quality`
- `GET /api/ml/registry/promotion-check`
- `GET /api/ml/serving-audit`
- `GET /api/ml/active-model`
- `GET /api/ml/predictions/active`
- `POST /api/ml/report`
- `GET /api/ml/reports`

## ML 운영 기준 사실

- 자동화 preset 정의는 현재 `backend/services/ml_automation_service.py` 기준입니다.
- 기본 자동화 preset:
  - `stock-v8-full`
  - `crypto-v8-full`
- 레거시 자동화 preset:
  - `stock-v7-full`
  - `crypto-v7-full`
- 주식 `v11` 모델 파일과 설정은 존재하지만, 자동화 preset은 아직 `v11`로 승격되지 않았습니다.
- 작업 이력의 1차 저장소는 파일입니다.
  - `ml/data/ops/job_history.json`
  - `ml/data/ops/model_registry.json`
- Supabase `ml_dataset_jobs`, `ml_training_runs`, `ml_model_registry`는 best-effort 동기화 대상입니다.

## 보안 및 운영 메모

- 사용자 거래소 키는 `user_api_keys` 테이블에 암호화 저장하고, 백엔드에서만 복호화합니다.
- Toss/KIS OAuth 토큰의 현재 기준 캐시 경로는 Supabase `token_caches` 테이블입니다.
- 저장소에 `.toss_token_cache.json`, `.kis_token_cache.json` 파일이 남아 있어도 현재 운영 기준의 1차 토큰 소스라고 가정하면 안 됩니다.
- 분산 환경에서 뉴스/ML 자동화 중복 실행 방지를 위해 `active_locks` 기반 분산 락을 사용합니다.
- 조건감시 자동매도는 사용자가 `AUTO`를 선택한 규칙만 직접 주문을 전송합니다. 실거래 추정 금액이 내부 1회 한도 10만 원을 넘으면 자동 주문 대신 매도 제안으로 우회합니다.

## 같이 보면 좋은 문서

- [project_structure.md](/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/project_structure.md:1)
- [system_workflow.md](/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/system_workflow.md:1)
- [database_specification.md](/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject/database_specification.md:1)
- [ml/README.md](/Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레잉/teamproject/ml/README.md:1)

## 2026-07-09 DART summary RAG

- DART disclosure RAG is summary-only: it indexes saved disclosure analysis summaries and basic metadata, not original disclosure bodies.
- News is excluded from this indexing path.
- Build chunks with `python backend\scripts\backfill_disclosure_summary_chunks.py`.
- Embed pending chunks with `python backend\scripts\embed_pending_knowledge_chunks.py`.
- Retrieval uses `POST /api/knowledge/retrieve-context` and the Supabase `match_knowledge_chunks` vector RPC.

## 2026-07-09 Obsidian note RAG

- `POST /api/knowledge/obsidian/sync-note` stores the note, replaces its `OBSIDIAN` chunks, and immediately embeds only the chunks for that note.
- The sync response includes `chunk_count` and `embedding_count`; a successful sync is ready for chatbot RAG retrieval without running the manual embedding script.
- The manual script is still useful for backfill or retries. Set `KNOWLEDGE_EMBEDDING_SOURCE_TYPE=OBSIDIAN` when embedding Obsidian chunks.
