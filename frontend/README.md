# 프론트엔드 문서

이 프론트엔드는 `React 19 + Vite 8 + Tailwind CSS v4 + Supabase JS` 기반으로 구성되어 있습니다.
현재 구현은 Next.js가 아니라 Vite SPA 구조이며, 주요 화면은 대시보드, 종목 상세, 뉴스, 설정, ML 운영 콘솔입니다.

## 실행

```bash
cd frontend
npm install
npm run dev
```

기본 개발 서버 주소:

- `http://localhost:5173`

빌드:

```bash
npm run build
```

## 현재 주요 페이지

```text
src/pages/
├── Dashboard.jsx
├── AssetDetail.jsx
├── AdminMlData.jsx
├── News.jsx
├── Home.jsx
├── Settings.jsx
├── Login.jsx
├── Signup.jsx
├── AssetsTab.jsx
├── TradeHistoryTab.jsx
└── WatchlistTab.jsx
```

### 페이지 역할

- `Dashboard.jsx`
  - 메인 포트폴리오/시장 대시보드
- `AssetDetail.jsx`
  - 차트, 호가, 체결, 주문 사전검증, ML 신호 카드
- `AdminMlData.jsx`
  - readiness, serving audit, 활성 신호, 자동화 실행, 작업 이력, 고급 ML 도구
- `News.jsx`
  - 뉴스 목록 및 검색
- `Settings.jsx`
  - 사용자 설정과 투자 성향 관련 화면

## 주요 컴포넌트

```text
src/components/
├── DashboardComponents.jsx
├── Header.jsx
├── InvestmentSurveyModal.jsx
└── SymbolSearch.jsx
```

## Supabase 클라이언트

현재 Supabase 초기화 경로가 두 군데 있습니다.

- `src/supabaseClient.js`
- `src/lib/supabaseClient.js`
- `src/lib/transferBalanceAdjustments.js`

동작 자체는 가능하지만 장기적으로는 한 경로로 통합하는 것이 좋습니다. 문서에서도 두 파일이 동시에 존재한다는 사실을 기준으로 설명해야 맞습니다.

## 백엔드 연동 포인트

프론트는 주요 기능을 아래 API와 연결합니다.

- 대시보드/시장: `/api/home/*`, `/api/market/*`, `/api/dashboard/*`
- 상세 페이지: `/api/chart/*`, `/api/trade/*`, `/api/symbol/*`
- 뉴스: `/api/news`
- ML 운영: `/api/ml/*`

또한 일부 기능은 Supabase 직접 조회를 사용합니다.

- `trade_proposals`
- `news_articles`

## 현재 UI 기준 사실

- `AssetDetail.jsx`에는 ML 참고 신호 카드가 있습니다.
- 이 카드는 현재 `signal_grade`, `reason_summary`, 정책 차단 사유, 진입 거리, 거래량 확인, 시장 폭, 섹터 강도, 모델 성능 스냅샷까지 표시합니다.
- `AdminMlData.jsx`는 기본 화면과 고급 도구를 분리한 운영 콘솔 구조입니다.

## 환경 변수

`frontend/.env`에는 공개 설정만 둡니다.

```ini
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=replace-me
VITE_API_BASE_URL=http://localhost:5050
```

중요:

- `SUPABASE_SERVICE_ROLE_KEY`
- 거래소 Secret
- `OPENAI_API_KEY`

위 값들은 프론트에 두면 안 됩니다.
