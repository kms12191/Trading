# AI 위탁운용 운영 콘솔 Implementation Plan

상태: 대체됨. 이 계획의 심볼 기반 전략 UI는 구현 대상에서 제거됐으며, 기존 대시보드 통합 자동선별 계획은 `2026-07-22-ai-fund-stock-selection-plan.md`를 따른다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 AI 위탁운용 화면에서 전략·주문 의도·백테스트·포트폴리오·운영 이력을 실제로 관리한다.

**Architecture:** Flask 라우트가 전략과 주문 의도의 CRUD 범위를 제공하고, React 대시보드는 기존 직접 Supabase 쓰기 대신 인증된 백엔드 API를 사용한다. 전략과 리밸런싱은 계속 `PENDING` TradeIntent만 만들며 승인 화면이 실행 관문 역할을 한다.

**Tech Stack:** React 19, Vite, Tailwind v4, Flask, Supabase PostgreSQL, Vitest, pytest.

## Global Constraints

- 기존 `AI 위탁 운용 시작`, 긴급 중지, 체결 이력 기능을 유지한다.
- 전략은 거래소 주문을 직접 호출하지 않는다.
- 관리자 역할 검증 보류 정책은 변경하지 않는다.
- 새 기능은 실패 테스트를 먼저 추가한다.

---

### Task 1: 전략·주문 의도 조회 API

**Files:**
- Modify: `backend/routes/admin_ai_fund.py`
- Modify: `backend/tests/test_admin_ai_fund_routes.py`

- [ ] 전략 목록, 전략 생성, 상태 변경, 주문 의도 목록 실패 테스트를 추가한다.
- [ ] 입력 전략 타입과 DCA·GRID 필수 설정을 검증하는 라우트를 구현한다.
- [ ] `pytest -q backend/tests/test_admin_ai_fund_routes.py`를 통과시킨다.

### Task 2: 운영 콘솔 데이터 모델과 API 클라이언트

**Files:**
- Create: `frontend/src/pages/adminAiFundConsoleModel.js`
- Modify: `frontend/src/pages/AdminAiFundDashboard.jsx`
- Test: `frontend/src/pages/adminAiFundConsoleModel.test.mjs`

- [ ] 전략 설정을 DCA·GRID API payload로 변환하는 실패 테스트를 추가한다.
- [ ] 폼 정규화와 API 응답 표현 모델을 구현한다.
- [ ] 모델 테스트를 통과시킨다.

### Task 3: 사용자 친화적 운영 화면

**Files:**
- Modify: `frontend/src/pages/AdminAiFundDashboard.jsx`
- Modify: `frontend/src/tests/AdminAiFundDashboard.test.jsx`

- [ ] 전략 생성, 승인 대기, 성과·운영 이벤트 섹션 렌더링 실패 테스트를 추가한다.
- [ ] 기존 화면에 접히지 않는 운영 패널을 구현하고 API 호출·로딩·오류 상태를 연결한다.
- [ ] `npm --prefix frontend run build`와 Vitest를 통과시킨다.

### Task 4: 문서·통합 검증

**Files:**
- Modify: `docs/superpowers/specs/2026-07-22-ai-fund-commercial-final-design.md`
- Modify: `docs/superpowers/specs/2026-07-22-ai-fund-operations-console-design.md`

- [ ] 운영 콘솔 완성 범위와 실제 사용 순서를 기록한다.
- [ ] 관련 pytest, Vitest, 프론트엔드 빌드, `git diff --check`를 실행한다.
