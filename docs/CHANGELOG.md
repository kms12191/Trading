# Changelog

본 문서는 Toss 메인 트레이딩 MVP 프로젝트의 주요 변경 이력 및 리팩토링 로그를 보관하는 파일입니다.

## [2026-07-15] - 프론트엔드/백엔드 대대적 리팩토링 및 클린 코드 작업

### Frontend Refactoring
- **AssetDetail 리팩토링**
  - 1차: 공통 순수 유틸을 `frontend/src/pages/assetDetailModel.js`로 분리하고 dead code warning 제거.
  - 2차: 종목 상세의 가격 자릿수와 차트 price format 계산을 `assetDetailModel.js`로 이동하고, 데이터 로딩/차트 effect 의존성 경고 정리.
  - 3차: 종목 상세의 뉴스, 공시, ML 지표, 캔들 포맷 순수 유틸을 `assetDetailModel.js`로 이동하고 Node 테스트 보강.
  - 컴포넌트 분리 공통화:
    - 상단 메타 헤더와 차트 패널 -> `assetDetailHeader.jsx`, `assetDetailChartPanel.jsx`로 분리.
    - 보유/주문 가능 요약 카드 및 미체결 주문 관리 패널 -> `assetDetailOrderPanels.jsx`로 분리.
    - 조건감시 등록/수정/상태 패널 -> `assetDetailAutoRulesPanel.jsx`로 분리.
    - 뉴스/공시 탭 콘텐츠 -> `assetDetailNewsDisclosurePanel.jsx`로 분리.
    - 커뮤니티 글/답글 패널 -> `assetDetailCommunityPanel.jsx`로 분리.
    - ML 참고 신호 카드와 해석 로직 -> `assetDetailMlSignalPanel.jsx`로 분리.

- **Dashboard 리팩토링**
  - 1차: 데스크톱/모바일 대시보드 공통 순수 유틸을 `frontend/src/pages/dashboardModel.js`로 분리하고 Node test 추가.
  - 2차: 보유종목 정렬을 `sortDashboardHoldings` 공통 모델로 이동, 계정/관심종목 로딩 effect 의존성과 set-state 경고 정리.

- **AdminMlData (ML 관리자 콘솔) 리팩토링**
  - 1차: 데스크톱/모바일 ML 관리자 공통 순수 유틸을 `frontend/src/pages/adminMlDataModel.js`로 분리하고 Node test 추가.
  - 2차~15차: 과밀화된 `AdminMlData.jsx` 컴포넌트(약 2,900줄)를 기능별 공통 패널 컴포넌트로 분리하고 구조화.
    - 배럴 파일(`adminMlDataPanels.jsx`) 생성 및 코어 패널(`adminMlDataCorePanels.jsx`), 운영/레지스트리/리포트 패널(`adminMlDataOperationalPanels.jsx`), 작업 이력 패널(`adminMlDataHistoryPanels.jsx`), 모델 결과 패널(`adminMlDataResultPanels.jsx`), 신뢰도 검증 패널(`adminMlDataTrustPanels.jsx`), 워크플로우 패널(`adminMlDataWorkflowPanels.jsx`)로 세분화 이관.

- **기타 컴포넌트 정리**
  - **Settings**: 설정 화면 공통 키 상태 정규화, 닉네임 검증, 거래소별 저장/테스트 payload 생성을 `frontend/src/pages/settingsModel.js`로 분리하고 Node test 추가.
  - **Inquiry**: 문의 화면 공통 문의 라벨, 첨부파일 검증, 목록 정렬/필터/페이지네이션, 등록 폼 검증을 `frontend/src/pages/inquiryModel.js`로 분리하고 Node test 추가.
  - **AssetsTab**: 데스크톱/모바일 자산 탭 공통 통화 포맷, 계좌 요약, 보유 종목 표시 행, 정렬, 배분 그래디언트 계산을 `frontend/src/pages/assetsTabModel.js`로 분리하고 Node test 추가.
  - **Watchlist**: 시장 필터, 차트 config, 캔들 정규화, 선택 종목 보정 로직을 `frontend/src/pages/watchlistModel.js`로 분리하고 effect 경고 정리.
  - **Home & MarketRankings**: 가격/등락률/거래대금 포맷, 국내외 판별, 랭킹 정렬, 관심종목 키 계산을 `frontend/src/pages/homeModel.js`로 분리하여 코드 중복 제거.
  - **Auth**: 로그인 화면의 미사용 이메일 로그인 상태/핸들러 및 회원가입 화면의 미사용 Supabase 응답 변수 제거.
  - **AdminUsers & AdminInquiries & AdminSymbolReconciliation**: 관리자 유저 목록, 문의 답변 모달, 종목 정리 관리자 화면의 인증 헤더/로더 안정화 및 effect 의존성 경고 정리.
  - **AssetLogo**: 공통 자산 로고 URL 생성 로직을 `frontend/src/components/assetLogoModel.js`로 분리하여 컴포넌트 최적화.

### Backend Refactoring
- **Chatbot Tool Registry 리팩토링**
  - 종목 별칭, 심볼 검색어 추출, 후보 선택 응답 순수 로직을 `backend/services/chatbot/tool_symbol_model.py`로 분리하고 pytest 추가.

### Quality Assurance & Lint Clean
- 프론트엔드 컴파일 및 린트 경고 정리 작업을 완료하여 **0 errors, 0 warnings** 달성.
- 각 분리된 순수 비즈니스 로직(Model.js)에 대한 Node 단위 테스트 보강.
