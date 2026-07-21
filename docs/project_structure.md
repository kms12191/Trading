# 프로젝트 구조 문서

본 문서는 현재 저장소에 실제로 존재하는 디렉토리와 파일을 기준으로 정리한 구조 안내서입니다.
과거 문서에 섞여 있던 "추가 예정" 구조는 최소화했고, 아직 없는 모듈은 존재하는 것처럼 적지 않습니다.

## 루트 구조

```text
teamproject/
├── .env.example
├── README.md
├── agents.md
├── design.md
├── database_specification.md
├── project_structure.md
├── system_workflow.md
├── toss_api_guide.md
├── kis_api_guide.md
├── backend/
├── frontend/
├── ml/
└── supabase/
```

## backend

```text
backend/
├── app.py
├── worker.py
├── requirements.txt
├── routes/
│   ├── home.py
│   ├── keys.py
│   ├── ml.py
│   ├── admin_inquiries.py
│   ├── admin_symbols.py
│   ├── admin_users.py
│   ├── chatbot.py
│   ├── knowledge.py
│   ├── news.py
│   ├── disclosures.py
│   ├── trade.py
│   └── transfer.py
├── scripts/
│   ├── backfill_dart_disclosures.py
│   ├── export_dart_features.py
│   ├── export_news_features.py
│   ├── export_training_candles.py
│   ├── sync_dart_corp_codes.py
│   └── sync_kis_market_universe.py
├── services/
│   ├── auth_service.py
│   ├── auto_trading_rule_engine.py
│   ├── binance_client.py
│   ├── broker_order_history_service.py
│   ├── chatbot/
│   │   ├── __init__.py
│   │   ├── chat_service.py
│   │   ├── conversation_repository.py
│   │   ├── function_calling.py
│   │   ├── llm_client.py
│   │   ├── memory_service.py
│   │   ├── order_form_policy.py
│   │   ├── order_parser.py
│   │   ├── portfolio_summary_service.py
│   │   ├── prompt_registry.py
│   │   ├── qa_event_repository.py
│   │   ├── rag_service.py
│   │   ├── recommendation_service.py
│   │   ├── safety_guard.py
│   │   ├── tool_symbol_model.py
│   │   ├── tool_registry.py
│   │   └── web_fallback_search_service.py
│   ├── coinone_client.py
│   ├── crypto_asset_service.py
│   ├── crypto_asset_sync_service.py
│   ├── crypto_cost_basis_service.py
│   ├── dart_ingest.py
│   ├── dart_repository.py
│   ├── disclosure_knowledge_index_service.py
│   ├── disclosure_knowledge_sync_service.py
│   ├── embedding_service.py
│   ├── error_message_service.py
│   ├── exchange_client.py
│   ├── home_service.py
│   ├── keys_service.py
│   ├── kis_client.py
│   ├── kis_market_universe.py
│   ├── knowledge_chunk_service.py
│   ├── knowledge_repository.py
│   ├── lock_service.py
│   ├── market_calendar_scheduler.py
│   ├── market_repository.py
│   ├── market_snapshot_scheduler.py
│   ├── ml_automation_service.py
│   ├── ml_job_service.py
│   ├── ml_model_service.py
│   ├── ml_registry_service.py
│   ├── ml_scheduler.py
│   ├── ml_split_model_promotion_service.py
│   ├── news_ingest.py
│   ├── news_quality_service.py
│   ├── news_query_planner.py
│   ├── news_repository.py
│   ├── news_summary_service.py
│   ├── order_entry_service.py
│   ├── open_order_status_sync_service.py
│   ├── obsidian_service.py
│   ├── rag_retrieval_service.py
│   ├── supabase_client.py
│   ├── symbol_reconciliation_service.py
│   ├── symbol_metadata.py
│   ├── token_cache_service.py
│   ├── toss_client.py
│   └── upbit_client.py
└── utils/
    ├── crypto_helper.py
    └── file_helpers.py
```

### backend 역할 구분

- `app.py`
  - Flask 앱 생성
  - Blueprint 등록
  - CORS 설정
  - 환경 변수 로드
  - 일부 스케줄러를 gateway 내부에서 돌릴지 결정
- `worker.py`
  - 뉴스 수집
  - DART 공시 수집
  - ML 자동화
  - 홈 마켓 스냅샷
  - 조건감시 자동/반자동 매도 스케줄러
  - 전체 사용자 미완료 주문 상태 동기화 스케줄러
- `routes/`
  - HTTP API 입구
  - `admin_users.py`는 관리자 전용 사용자 목록, 실제 챗봇 토큰 사용량, 유저별 거래내역 조회, role 변경 API를 제공합니다. 사용량 집계·정렬·페이지 제한은 service-role 전용 Supabase RPC에 위임하고, 관리용 거래내역은 `trade_proposals`, `broker_order_history`, `asset_transfer_proposals`의 제한 필드만 반환하며 보유자산/잔고는 노출하지 않습니다.
  - `disclosures.py`는 OpenDART 공시 목록 조회 및 수동 동기화 API를 담당
  - `transfer.py`는 코인원 ↔ 바이낸스 가상자산 출금 사전검증, 수수료 조회, 승인, 상태 추적 API를 담당
  - `knowledge.py`는 Obsidian Markdown 노트 동기화와 앱 자동메모리 조회 API를 담당
- `services/`
  - 거래소 연동, Supabase, 스케줄러, ML 운영 로직
  - `chatbot/conversation_repository.py`는 Supabase `chat_history`와 `chatbot_conversation_states`를 사용해 다중 워커 간 대화 이력, 만료 가능한 대기 작업, 최근 추천 상태를 공유
  - `chatbot/portfolio_summary_service.py`는 거래소별 KRW·USD·USDT 잔고를 원화로 환산하고 REAL/MOCK 계좌 합계를 분리
  - `chatbot/llm_client.py`는 OpenAI Chat Completions 스트림의 텍스트 delta를 전달하고 분할된 tool-call과 usage를 누적
  - `chatbot/qa_event_repository.py`는 챗봇 QA 분석용 자동 이벤트를 `chatbot_qa_events`에 service role로 저장하며, 민감한 거래소 raw payload 대신 trace·도구·지연시간 요약만 남깁니다.
  - `news_quality_service.py`는 예약 뉴스 저장 전 기사 제목·요약·URL·종목 신호를 기준으로 `PASS`/`HIGH_QUALITY` 품질 메타데이터를 계산하고 위키·사전·커뮤니티성 결과를 저장 전 제외합니다.
  - `news_repository.py`는 `news_articles` 일반 뉴스 7일, `HIGH_QUALITY` 뉴스 30일, `news_fetch_logs` 7일 물리 삭제를 수행하는 보관 정리 메서드를 포함합니다.
  - `ml_scheduler.py`의 뉴스 수집 루프는 같은 worker 흐름에서 뉴스 보관 정리를 하루 1회 시도하며, 정리 실패가 뉴스 수집을 막지 않도록 분리해 로깅합니다.
  - `order_entry_service.py`는 구조화 주문 필수값, 주식·현물·선물 거래 목적, One-way/Hedge 주문 변환, 서비스 레버리지 상한, 주문 해시와 HMAC 사전검증 토큰을 담당합니다.
  - `chatbot/order_form_policy.py`는 일반 채팅의 자연어 주문 의도를 주문 제안 생성 전에 차단하고 상단 `매매 요청` 버튼을 이용하라는 안내만 반환합니다. 종목·수량·가격·거래소를 추출하거나 저장하지 않습니다.
  - `chatbot/tool_symbol_model.py`는 챗봇 도구가 공유하는 종목 별칭, 심볼 검색어 추출, 종목 후보 정규화, 모호한 종목 선택 응답 생성을 담당합니다.
  - `chatbot/tool_registry.py`는 `get_crypto_market_context`를 통해 코인 현재가, 호가, 캔들, ML 활성 신호, 보유 스냅샷, 스프레드·슬리피지, Coinone/Binance 김치프리미엄과 주의사항을 통합한 읽기 전용 분석 도구를 제공합니다.
  - `crypto_asset_service.py`는 Supabase `crypto_assets` 단일 테이블을 기준으로 코인원/바이낸스 상장 상태, 거래 가능 여부, 표시명, 기본 거래소, 관리자 차단 상태를 조회·검색·수정합니다.
  - `crypto_asset_sync_service.py`는 코인원 Public currency 목록과 바이낸스 exchangeInfo를 병합해 `crypto_assets`에 상장/거래 가능 상태를 업서트합니다.
  - `obsidian_service.py`는 Markdown frontmatter/title/hash 정규화를 담당
  - `knowledge_chunk_service.py`는 저장된 노트 본문을 RAG/embedding 대상 chunk로 분할
  - `knowledge_repository.py`는 `user_knowledge_notes`, `user_memory_facts` Supabase 저장/조회 래퍼를 담당
- `scripts/`
  - 수집/변환/유니버스 동기화 보조 스크립트

### backend에서 문서상 주의할 점

- `agent.py`, `trading_engine.py`는 현재 저장소에 없습니다.
- 토큰 캐시는 현재 `token_cache_service.py`와 Supabase `token_caches`를 기준으로 보는 것이 맞습니다.
- `coinone_client.py`는 코인원 잔고/현재가/지정가 주문/미체결 주문 취소, 입금 주소 조회, Public 가상자산 입출금 수수료 조회, 출금을 담당하며, 시장가 주문은 아직 운영 경로가 아닙니다.
- `binance_client.py`는 `BinanceSpotClient`와 `BinanceFuturesClient`를 포함합니다. 현물 클라이언트는 입금 주소/입금 내역, 네트워크별 출금 수수료, 출금 요청을 지원합니다. API Key 저장은 `BINANCE` 레코드 하나를 사용하고, `BINANCE_UM_FUTURES`는 USD-M 선물 잔고/주문/이력 요청 식별자로만 사용합니다. 선물 주문은 레버리지와 교차/격리 마진 타입을 주문 직전에 반영하며, 선물 REAL 주문은 `BINANCE_FUTURES_REAL_ENABLED=true` 환경변수 없이는 차단됩니다.
- `auto_trading_rule_engine.py`는 Supabase `auto_trading_rules`의 `RUNNING` 규칙을 감시하고, 조건 도달 시 `trade_proposals`에 매도 제안을 생성하거나 사용자가 `AUTO`로 선택한 규칙에 한해 자동 매도 주문을 전송합니다.
- `open_order_status_sync_service.py`는 worker가 전체 사용자의 미완료 주문만 주기적으로 조회해 KIS/코인원/바이낸스/바이낸스 선물 실제 주문 상태를 `trade_proposals`에 반영하는 서비스입니다.
- `error_message_service.py`는 거래소 원문 에러를 사용자 친화적인 `message`, `error.title`, `error.action`, `error.code`, `error.raw_message` 구조로 변환하는 표준 에러 메시지 레이어입니다.
- `broker_order_history_service.py`는 Toss/KIS/Coinone/Binance 주문 원장 동기화 및 미체결/체결 상태 보정 흐름을 담당합니다.
- `upbit_client.py`는 남아 있지만 현재 핵심 운영 경로는 아닙니다.

## frontend

## 2026-07-01 OpenDART 공시 연동 추가 모듈

- `backend/routes/disclosures.py`: 종목 상세 공시 목록 조회 및 수동 공시 동기화 API
- `backend/services/dart_repository.py`: Supabase `dart_*` 테이블 조회/upsert 저장소
- `backend/services/dart_ingest.py`: OpenDART 전체 공시 목록 수집, 최근 1년 백필, `CORPCODE.xml` 매핑 동기화 서비스
- `backend/scripts/sync_dart_corp_codes.py`: 루트 `CORPCODE.xml`을 `dart_corp_codes`에 업서트하는 스크립트
- `backend/scripts/backfill_dart_disclosures.py`: 최근 1년 공시를 날짜 구간별로 수집해 `dart_disclosures`에 업서트하는 스크립트
- `supabase/migrations/20260701093000_create_dart_disclosures.sql`: DART 공시 캐시 테이블, 로그 테이블, RLS 정책 생성

```text
frontend/
├── package.json
├── package-lock.json
├── vite.config.js
└── src/
    ├── App.jsx
    ├── App.css
    ├── index.css
    ├── main.jsx
    ├── supabaseClient.js
    ├── dashboardConstants.js
    ├── dashboardUtils.js
    ├── assets/
    ├── components/
    │   ├── AssetLogo.jsx
    │   ├── assetLogoModel.js
    │   ├── assetLogoModel.test.mjs
    │   ├── DashboardComponents.jsx
    │   ├── Header.jsx
    │   ├── InvestmentSurveyModal.jsx
    │   ├── MemberOnlyModal.jsx
    │   ├── MemberOnlyNotice.jsx
    │   ├── SymbolSearch.jsx
    │   └── mobile/
    ├── lib/
    │   ├── apiError.js
    │   └── supabaseClient.js
    ├── features/
    │   └── chatbot/
    │       ├── ChatbotWidget.jsx
    │       ├── OrderEntryFlow.jsx
    │       ├── chatbotApi.js
    │       ├── chatbotStream.js
    │       ├── chatbotTimeline.js
    │       ├── chatbotTrace.js
    │       └── orderEntryModel.js
    └── pages/
        ├── AdminInquiries.jsx
        ├── AdminInquiryPanel.jsx
        ├── AdminMlData.jsx
        ├── adminMlDataCorePanels.jsx
        ├── adminMlDataHistoryPanels.jsx
        ├── adminMlDataOperationalPanels.jsx
        ├── adminMlDataPanels.jsx
        ├── adminMlDataResultPanels.jsx
        ├── adminMlDataTrustPanels.jsx
        ├── adminMlDataWorkflowPanels.jsx
        ├── adminMlDataModel.js
        ├── adminMlDataModel.test.mjs
        ├── AdminCryptoAssetEditModal.jsx
        ├── AdminCryptoAssetsPanel.jsx
        ├── adminCryptoAssetModel.js
        ├── AdminDeleteConfirmModal.jsx
        ├── AdminSymbolReconciliation.jsx
        ├── AdminSummaryCard.jsx
        ├── AdminUsers.jsx
        ├── AssetDetail.jsx
        ├── assetDetailAutoRulesPanel.jsx
        ├── assetDetailChartPanel.jsx
        ├── assetDetailCommunityPanel.jsx
        ├── assetDetailHeader.jsx
        ├── assetDetailMlSignalPanel.jsx
        ├── assetDetailModel.js
        ├── assetDetailModel.test.mjs
        ├── assetDetailNewsDisclosurePanel.jsx
        ├── assetDetailOrderPanels.jsx
        ├── AssetsTab.jsx
        ├── assetsTabModel.js
        ├── assetsTabModel.test.mjs
        ├── Dashboard.jsx
        ├── dashboardModel.js
        ├── dashboardModel.test.mjs
        ├── Home.jsx
        ├── homeModel.js
        ├── homeModel.test.mjs
        ├── Inquiry.jsx
        ├── inquiryModel.js
        ├── inquiryModel.test.mjs
        ├── Login.jsx
        ├── MarketRankings.jsx
        ├── News.jsx
        ├── SearchNotFound.jsx
        ├── Settings.jsx
        ├── settingsModel.js
        ├── settingsModel.test.mjs
        ├── Signup.jsx
        ├── TradeHistoryTab.jsx
        ├── tradeHistoryModel.js
        ├── tradeHistoryModel.test.mjs
        ├── WatchlistTab.jsx
        ├── watchlistModel.js
        ├── watchlistModel.test.mjs
        └── mobile/
```

### frontend 역할 구분

- `AdminSymbolReconciliation.jsx`는 기존 주식 종목 정리 스캔, 비활성화, 캐시 삭제, 복구 화면의 컨테이너입니다.
- `AdminCryptoAssetsPanel.jsx`는 코인 종목 마스터(`crypto_assets`) 조회, 코인원/바이낸스 공개 API 동기화, 표시명/별칭/기본 거래소/관리자 차단 상태 수정 진입을 제공합니다.
- `AdminCryptoAssetEditModal.jsx`는 코인 종목 표시명, 별칭, 거래소별 심볼, 노출 여부, 관리자 거래 차단 상태를 수정하는 모달입니다.
- `adminCryptoAssetModel.js`는 관리자 코인 종목 수정 모달의 초기 편집 상태 변환을 담당합니다.
- `AdminDeleteConfirmModal.jsx`와 `AdminSummaryCard.jsx`는 관리자 종목 정리 화면의 확인 모달과 요약 카드입니다.
- `SymbolSearch.jsx`는 코인 검색 결과의 `default_exchange`를 상세 페이지 URL query로 전달해 거래소 전용 종목이 잘못된 거래소로 열리지 않게 합니다.
- `AssetDetail.jsx`와 `mobile/MobileAssetDetail.jsx`는 URL의 `exchange` 또는 `/api/symbol/lookup`의 `default_exchange`를 우선 적용해 코인 상세 거래소를 확정합니다.

- `features/chatbot/OrderEntryFlow.jsx`
  - 챗봇 상단 버튼에서 빈 상태로 시작하는 데스크톱 3단계 매매 요청 UI
  - 연결 계좌와 거래 목적, 검색 결과 또는 서버 보유 목록, 주문 조건, 사전검증 결과를 순서대로 확인
  - 검증 토큰이 유효한 경우에만 구조화 챗봇 요청으로 `PENDING` 제안을 생성
- `features/chatbot/orderEntryModel.js`
  - 입력 변경 시 사전검증 무효화, 단계 이동 가능 여부, 자산별 수량·통화·거래 목적 용어, API 요청 DTO를 관리

- `Dashboard.jsx`
  - 메인 대시보드
  - 자산/시장/실거래 vs 모의 토글 흐름
- `dashboardModel.js`
  - `Dashboard.jsx`와 `MobileDashboardPage.jsx`가 공유하는 통화 포맷, 자산 평가, 보유자산 병합, 보유종목 정렬, 관심종목 판별 순수 유틸
- `dashboardModel.test.mjs`
  - `dashboardModel.js`의 순수 함수 Node test
- `AssetDetail.jsx`
  - 종목 상세
  - 차트, 호가, 체결, 주문 사전검증, ML 신호 카드
  - TOSS 주식 상세 헤더의 종목 유의사항 배지 연동
- `assetDetailAutoRulesPanel.jsx`
  - `AssetDetail.jsx`와 `MobileAssetDetail.jsx`가 공유하는 조건감시 등록, 수정, 상태 목록 패널
- `assetDetailCommunityPanel.jsx`
  - `AssetDetail.jsx`와 `MobileAssetDetail.jsx`가 공유하는 종목 커뮤니티 글 작성, 답글, 삭제·숨김 액션 패널
- `assetDetailNewsDisclosurePanel.jsx`
  - `AssetDetail.jsx`와 `MobileAssetDetail.jsx`가 공유하는 뉴스 목록, 뉴스 요약, DART 공시 목록, 공시 AI 분석 콘텐츠 패널
- `assetDetailMlSignalPanel.jsx`
  - `AssetDetail.jsx`와 `MobileAssetDetail.jsx`가 공유하는 ML 참고 신호 카드, 모델 품질, 정책 라벨, 신호 해석 표시 패널
- `assetDetailHeader.jsx`
  - `AssetDetail.jsx`와 `MobileAssetDetail.jsx`가 공유하는 종목 메타, 즐겨찾기, 종목 유의사항, 현재가 헤더 컴포넌트
- `assetDetailChartPanel.jsx`
  - `AssetDetail.jsx`와 `MobileAssetDetail.jsx`가 공유하는 Lightweight Charts 컨테이너, 캔들 주기 선택, 크게보기 패널
- `assetDetailOrderPanels.jsx`
  - `AssetDetail.jsx`와 `MobileAssetDetail.jsx`가 공유하는 보유/주문 가능 요약 카드와 미체결 주문 관리 패널
- `assetDetailModel.js`
  - `AssetDetail.jsx`와 `MobileAssetDetail.jsx`가 공유하는 주문 상태 라벨, 조건감시 라벨, 심볼 판별, 가격 자릿수/차트 price format, 뉴스·공시·ML 지표·캔들 포맷, 종목 유의사항 배지 tone 순수 유틸
- `assetDetailModel.test.mjs`
  - `assetDetailModel.js`의 순수 함수 Node test
- `AssetsTab.jsx`
  - 계좌별 자산 요약, 자산 배분, 보유 종목, 코인 자산 이동/출금 모달을 제공하는 데스크톱 자산 탭
- `assetsTabModel.js`
  - `AssetsTab.jsx`와 `MobileAssetsTab.jsx`가 공유하는 통화 포맷, 계좌 요약 카드, 보유 종목 표시 행, 정렬, 배분 그래디언트 순수 유틸
- `assetsTabModel.test.mjs`
  - `assetsTabModel.js`의 순수 함수 Node test
- `WatchlistTab.jsx`
  - 관심종목 목록, 드래그 순서 변경, 관심종목 차트와 뉴스 요약을 제공하는 데스크톱 탭
- `watchlistModel.js`
  - `WatchlistTab.jsx`와 `MobileWatchlistTab.jsx`가 공유하는 시장 필터, 차트 config, 캔들 정규화, 선택 종목 보정 순수 유틸
- `watchlistModel.test.mjs`
  - `watchlistModel.js`의 순수 함수 Node test
- `Home.jsx`
  - 홈 시장 랭킹, 국내·해외 주식/코인 필터, 관심종목 토글을 제공하는 데스크톱 홈 화면
- `homeModel.js`
  - `Home.jsx`와 `useMobileHomeMarket.js`가 공유하는 시장 랭킹 포맷, 국내·해외 판별, 정렬, 관심종목 키 계산 순수 유틸
- `homeModel.test.mjs`
  - `homeModel.js`의 순수 함수 Node test
- `MarketRankings.jsx`
  - 홈 시장 랭킹 더보기 화면이며 `homeModel.js`의 포맷/관심종목 키 계산을 재사용
- `AdminInquiryPanel.jsx`
  - 3분리 모델 자동화 상태 모니터링 및 수동 검증 패널
- `AdminMlData.jsx`
  - ML 운영 콘솔
  - readiness, serving audit, 활성 신호, 자동화 실행, 작업 이력, 고급 도구
  - 관리자 유저 관리 탭에서 `AdminUsers.jsx`를 렌더링
- `adminMlDataPanels.jsx`
  - ML 관리자 공통 패널의 배럴 파일
- `adminMlDataCorePanels.jsx`
  - `AdminMlData.jsx`와 `MobileAdminMlData.jsx`가 공유하는 상태 패널, 감사 배지, 승격 검증 요약, 작업 로그 모달, 버전 차이 요약 컴포넌트
- `adminMlDataHistoryPanels.jsx`
  - `AdminMlData.jsx`와 `MobileAdminMlData.jsx`가 공유하는 ML 작업 이력 패널
  - 데스크톱 테이블과 모바일 카드 레이아웃을 variant로 유지
- `adminMlDataOperationalPanels.jsx`
  - `AdminMlData.jsx`와 `MobileAdminMlData.jsx`가 공유하는 활성 신호, 운영 모델 감사, 모델 교체 판단, 모델 레지스트리, 준비 상태, 실행 체크리스트, 실험 리포트, 버전 비교 컴포넌트
- `adminMlDataResultPanels.jsx`
  - `AdminMlData.jsx`와 `MobileAdminMlData.jsx`가 공유하는 ML 모델 결과 카드, 예측 목록, 백테스트 요약 컴포넌트
- `adminMlDataTrustPanels.jsx`
  - `AdminMlData.jsx`와 `MobileAdminMlData.jsx`가 공유하는 운영 신뢰도 검증, TrustMetric, v8 Optuna 튜닝 패널
- `adminMlDataWorkflowPanels.jsx`
  - `AdminMlData.jsx`와 `MobileAdminMlData.jsx`가 공유하는 ML 콘솔 헤더, 자동화 실행, 고급 데이터 도구, 모델 결과, 레지스트리 상태, 학습 도구, 작업 이력 패널
- `adminMlDataModel.js`
  - `AdminMlData.jsx`와 `MobileAdminMlData.jsx`가 공유하는 ML 프리셋, 경로/수치 포맷, 승격 검증 요약, 작업 로그 복사 텍스트, 데이터 품질 상세 순수 유틸
- `adminMlDataModel.test.mjs`
  - `adminMlDataModel.js`의 순수 함수 Node test
- `AdminUsers.jsx`
  - 관리자 유저 관리 탭의 데스크톱/반응형 UI
  - UTC 기준 실제 챗봇 토큰 사용량 집계와 사용자별 사용 내역을 조회
  - 현재 기본 모델 `gpt-4.1-mini` 가격 기준으로 통산/30일/유저별/요청별 예상 비용을 추정 표시
- `TradeHistoryTab.jsx`
  - 거래 제안, 브로커 원장, 자산이동 내역을 통합 표시하는 데스크톱 거래내역 탭
- `tradeHistoryModel.js`
  - `TradeHistoryTab.jsx`와 `MobileTradeHistoryTab.jsx`가 공유하는 거래 상태 라벨, 금액/수량 포맷, 브로커 원장 연결, 자산이동 행 변환 순수 유틸
- `tradeHistoryModel.test.mjs`
  - `tradeHistoryModel.js`의 순수 함수 Node test
- `Settings.jsx`
  - 프로필 닉네임 저장, 거래소 API Key 등록 현황, 연결 테스트, 저장 검증을 제공하는 데스크톱 설정 화면
- `settingsModel.js`
  - `Settings.jsx`와 `MobileSettings.jsx`가 공유하는 키 상태 정규화, 닉네임 검증, 거래소별 저장/테스트 payload 생성 순수 유틸
- `settingsModel.test.mjs`
  - `settingsModel.js`의 순수 함수 Node test
- `Inquiry.jsx`
  - 고객센터, FAQ, 1:1 문의 등록, 문의 내역 조회/삭제를 제공하는 데스크톱 문의 화면
- `inquiryModel.js`
  - `Inquiry.jsx`와 `MobileInquiry.jsx`가 공유하는 문의 라벨, 첨부파일 검증, 저장 경로 생성, 목록 정렬·필터·페이지네이션, 요약/폼 검증 순수 유틸
- `inquiryModel.test.mjs`
  - `inquiryModel.js`의 순수 함수 Node test
- `supabaseClient.js`, `lib/supabaseClient.js`
  - Supabase 초기화 경로가 2개 존재
  - 향후 통합 시 import 호출부 전수 확인이 필요

### frontend에서 문서상 주의할 점

- 현재 프로젝트는 Next.js 구조가 아니라 `Vite + React` 구조입니다.
- `frontend/README.md`는 기본 템플릿이었으나 실제 구조 기준으로 별도 정리해야 합니다.

## ml

```text
ml/
├── README.md
├── automation_plan.md
├── dataset_ops_runbook.md
├── experiments.md
├── live_run_checklist.md
├── requirements.txt
├── serving_package_runbook.md
├── test_yf.py
├── configs/
├── data/
│   ├── ops/
│   ├── processed/
│   ├── raw/
│   └── reference/
├── models/
├── notebooks/
├── reports/
├── serving_packages/
└── src/
    ├── backtest_signals.py
    ├── build_features.py
    ├── compare_experiments.py
    ├── compare_model_versions.py
    ├── evaluate.py
    ├── export_serving_package.py
    ├── model_utils.py
    ├── policy_utils.py
    ├── predict.py
    ├── run_pipeline_bundle.py
    ├── train_model.py
    ├── tune_hyperparameters.py
    ├── tune_stock_policy.py
    └── write_experiment_report.py
```

### ml 역할 구분

- `configs/`
  - 현재 기준 주식 신호 `v1~v11`
  - 주식 위험 `v1~v11`
  - 코인 신호/위험 `v1~v9`
  - 3분리 shadow 모델 설정: `lgbm_kr_stock_v1.yaml`, `lgbm_kr_stock_risk_v1.yaml`, `lgbm_us_stock_v1.yaml`, `lgbm_us_stock_risk_v1.yaml`
- `data/raw/`
  - 원천 캔들 및 외부 피처 CSV
- `data/ops/`
  - `job_history.json`
  - `model_registry.json`
- `models/`
  - 학습된 joblib 및 metrics JSON
- `reports/`
  - 비교 리포트와 최신 실험 리포트
- `serving_packages/`
  - EC2 업로드용 서빙 패키지 출력 디렉토리
  - `manifest.json`, 모델 joblib, risk 모델 joblib, config, metrics, summary만 포함하며 raw 학습 데이터는 포함하지 않습니다.

## supabase

```text
supabase/
├── config.toml
└── migrations/
```

이 디렉토리는 존재합니다. 다만 현재 애플리케이션 동작의 일부는 파일 기반 이력과 Supabase best-effort 동기화가 섞여 있으므로, "모든 운영 상태가 Supabase 마이그레이션만으로 완전히 재현된다"고 적으면 사실과 다릅니다.

## 문서 업데이트 원칙

- 실제 파일이 없으면 존재한다고 적지 않습니다.
- 계획 문서는 `automation_plan.md`처럼 계획 문서로 남기고, 현재 구조 문서와 섞지 않습니다.
- API, DB, ML 버전은 코드 기준으로 맞추고, 실험 리포트 숫자는 별도 리포트 문서에서만 관리합니다.

---

1. **역할의 명확성**: 파일명만 봐도 해당 코드가 프론트엔드 화면, 백엔드 API Gateway, Toss 통신 로직, DB 마이그레이션 중 영역인지 즉시 식별할 수 있습니다.
2. **Toss 전환 안정성**: KIS 레거시 구현을 보존하면서 신규 Toss 클라이언트를 별도 모듈로 추가하므로, 기존 기능을 훼손하지 않고 점진적으로 전환할 수 있습니다.
3. **ML 실험 격리**: `ml/` 디렉토리에서 주식/코인 모델의 학습 데이터, 피처 생성, 모델 학습을 격리하므로 Flask 서비스 코드와 실험 코드가 섞이지 않습니다.
4. **협업 병목 제거**: 프론트엔드 개발자는 `frontend/` 내부 UI와 Supabase Realtime 구독에 집중하고, 백엔드 개발자는 `backend/` 내부에서 Toss API 스펙과 보안 정책에 맞춰 작업할 수 있습니다.
5. **배포 편리성**: `Docker` 빌드 시 프론트엔드 도커파일과 백엔드 도커파일을 루트의 서브디렉토리 기준으로 각각 빌드하기 최적화된 구조입니다.

---

## 5. KIS order execution and estimated holdings additions

* `backend/services/kis_client.py`
  * `get_daily_order_executions()`: KIS domestic stock daily order/execution inquiry.
  * `get_order_execution_status()`: Normalizes KIS order state into `EXECUTED`, `PARTIALLY_FILLED`, `CANCELED`, `ORDERED`, or `UNKNOWN`.
* `backend/routes/trade.py`
  * `POST /api/trade/orders/sync-status`: Syncs KIS DB order records with real KIS execution status, then falls back to balance checks.
  * `POST /api/trade/estimated-holdings`: Builds DB-estimated holdings from executed `trade_proposals`, enriches stock positions with broker prices, and calculates valuation profit and profit rate.

## 6. Disclosure summary RAG additions

* `backend/services/disclosure_knowledge_index_service.py`: Builds summary-only DART disclosure documents/chunks for `knowledge_chunks`.
* `backend/services/embedding_service.py`: Embeds pending knowledge chunks with OpenAI embeddings.
* `backend/services/rag_retrieval_service.py`: Embeds a question and retrieves ranked context through Supabase vector search.
* `backend/scripts/backfill_disclosure_summary_chunks.py`: Rebuilds `DISCLOSURE` chunks from cached DART AI/rule summaries.
* `backend/scripts/embed_pending_knowledge_chunks.py`: Embeds pending chunks, defaulting to `DISCLOSURE`.
* `supabase/migrations/20260709103000_add_knowledge_chunk_vector_search.sql`: Adds the vector index and `match_knowledge_chunks` RPC.
* This flow excludes news and DART original text; only saved disclosure summaries and metadata are indexed.

## 7. Retention cleanup

* `backend/services/news_retention_service.py`: Keeps general news for 7 days, high-quality news for 30 days, and DART disclosures with their analyses and `DISCLOSURE` chunks for 30 days.
* `backend/services/ml_scheduler.py`: Runs the disclosure cleanup before the daily news ingest under the existing distributed lock.
* `supabase/migrations/20260720120000_add_disclosure_retention_cleanup.sql`: Defines the service-role-only RPC used for atomic 5,000-row disclosure cleanup batches.
