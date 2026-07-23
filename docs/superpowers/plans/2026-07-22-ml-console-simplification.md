# ML 운영 콘솔 UI 단순화 및 최신화 구현 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ML 운영 콘솔 UI에서 오래된 레거시(v6, v7) 모델을 전면 제거하고, 4대 활성 모델(주식 v11/v8, 코인 v10, 국내/해외 v1) 중심의 직관적인 3단 탭 및 서브탭 구조로 단권화합니다.

**Architecture:** `adminMlDataModel.js`에서 프리셋 목록을 최신화하고, `adminMlDataWorkflowPanels.jsx`와 `AdminMlData.jsx`를 개편하여 기본 뷰(서빙 요약 / 원클릭 자동화 / 이력 모달)와 고급 도구 3대 서브탭(Optuna 튜닝 / 수동 수집 / 유니버스 관리)을 구성합니다.

**Tech Stack:** React 19, Tailwind v4, Vite, JavaScript (ESM)

## Global Constraints

- 모든 설명 및 사용자 인터랙션은 한국어로 작성함.
- ESLint 정적 분석 에러 0건 유지.
- `file://` 링크 표준 준수.

---

### Task 1: `adminMlDataModel.js` 레거시 (v6, v7) 프리셋 제거 및 최신화

**Files:**
- Modify: `frontend/src/pages/adminMlDataModel.js:65-180`

**Interfaces:**
- Consumes: Existing preset definitions
- Produces: Cleaned `trainingPresets`, `tuningPresets`, `automationPresets`, `v8TuningPresets` export arrays without v6/v7

- [ ] **Step 1: Edit adminMlDataModel.js to remove v6 and v7 presets**

Remove all `{ key: 'stock-v6' }`, `{ key: 'crypto-v6' }`, `{ key: 'stock-v7' }`, `{ key: 'crypto-v7' }` definitions from `trainingPresets`, `tuningPresets`, and `automationPresets`.

- [ ] **Step 2: Run ESLint to verify no syntax errors**

Run: `cd frontend && npx eslint src/pages/adminMlDataModel.js`
Expected: PASS with 0 errors

- [ ] **Step 3: Commit changes**

```bash
git add frontend/src/pages/adminMlDataModel.js
git commit -m "refactor: purge legacy v6 and v7 presets from adminMlDataModel.js"
```

---

### Task 2: 고급 도구 3대 서브탭 및 메인 운영 콘솔 UI 개편

**Files:**
- Modify: `frontend/src/pages/adminMlDataWorkflowPanels.jsx:38-120`
- Modify: `frontend/src/pages/AdminMlData.jsx:85-150`

**Interfaces:**
- Consumes: `operationalAutomationPresets`, `v8TuningPresets`, `presets`
- Produces: `AdvancedToolsSubTabs` component providing 3 tabs (`Optuna HPO 튜닝`, `커스텀 수집/학습`, `유니버스 관리`)

- [ ] **Step 1: Add AdvancedToolsSubTabs to adminMlDataWorkflowPanels.jsx**

Implement clean sub-tabs state for Advanced Tools (Tab 1: Optuna HPO, Tab 2: Custom Data Collect, Tab 3: Universe Management).

- [ ] **Step 2: Update AdminMlData.jsx to utilize the restructured workflow panels**

Update `AdminMlData.jsx` to render the clean serving status banner, 4 operational automation cards, job history section, and the 3-subtab Advanced Tools container.

- [ ] **Step 3: Run ESLint to verify zero errors**

Run: `cd frontend && npx eslint .`
Expected: PASS with 0 errors

- [ ] **Step 4: Commit changes**

```bash
git add frontend/src/pages/adminMlDataWorkflowPanels.jsx frontend/src/pages/AdminMlData.jsx
git commit -m "feat: restructure ML console UI with 3 sub-tabs and clean operational view"
```

---

### Task 3: 최종 검증 및 빌드 테스트

**Files:**
- Test: `frontend/src/pages/AdminMlData.jsx`

- [ ] **Step 1: Run frontend build check**

Run: `cd frontend && npm run build`
Expected: PASS with clean bundle output

- [ ] **Step 2: Commit final verification**

```bash
git add .
git commit -m "chore: complete ML console UI simplification and build verification"
```
