# ML 운영 콘솔 UI 단순화 및 최신화 설계서 (Design Spec)

**작성일**: 2026-07-22  
**상태**: Approved (사용자 1번 제안 승인 완료)

---

## 1. 개요 (Overview)

ML 운영 콘솔 (`AdminMlData.jsx` 및 서브 패널들)에 남아있던 레거시 모델(v6, v7 등) 및 15개 이상의 복잡하게 중첩된 패널을 정리하여, **주식 v11/v8, 코인 v10(248종목), 국내/해외주식 v1 중심의 직관적이고 현대적인 UI**로 전면 재구조화합니다.

---

## 2. 주요 변경 사항 (Key Changes)

### 2.1 레거시 모델 (v6, v7) 정리 및 구형 더미 제거
- `adminMlDataModel.js`의 `trainingPresets`, `tuningPresets`, `automationPresets`에서 더 이상 사용하지 않는 v6, v7 항목을 전면 정리합니다.
- 최신 운영 규격만 노출:
  - **주식**: `stock-v8-full`, `stock-v11-full`
  - **코인**: `crypto-v10-full` (248개 알트코인 전종목)
  - **국내주식**: `kr-stock-v1-full`
  - **해외주식**: `us-stock-v1-full`

### 2.2 기본(운영) 화면 재구성
- **[Top] 실시간 서빙 현황 배너**: 현재 서버가 실시간 시그널 추출에 사용 중인 활성 서빙 모델(`코인 v10`, `주식 v11`, `국내 v1`, `해외 v1`)의 ROC AUC 및 주요 성능을 한눈에 요약.
- **[Center] 4대 원클릭 자동 수집+학습 카드**:
  - `주식 v8 자동 수집+학습`
  - `코인 v10 자동 수집+학습 (248종목 30m)`
  - `국내주식 v1 자동 수집+학습`
  - `해외주식 v1 자동 수집+학습`
- **[Bottom] 작업 이력 & 로그 모달**: 최근 30개 자동 수집/학습 작업 상태 및 실시간 로그 확인 모달.

### 2.3 고급 도구 (Advanced Tools) 서브탭 통합
고급 도구를 열었을 때 복잡하게 수직 나열되던 패널을 **3개 서브탭**으로 분류:
1. 🎯 **Optuna HPO 튜닝**: `crypto-v10-tune`, `stock-v8-tune` (최적 시도 수, 갱신 설정 포함)
2. 📥 **커스텀 데이터 수집/수동 학습**: 수동 캔들 수집 및 커스텀 파이프라인 수동 구동
3. 🪙 **유니버스 종목 관리**: 248개 코인 및 주식 감시 종목 유니버스 조회 및 갱신

---

## 3. UI 컴포넌트 구조 (Component Architecture)

```
AdminMlData.jsx
├── MlConsoleHeader (운영 콘솔 타이틀 & 고급 도구 열기/접기 버튼)
├── ServingStatusSummaryBanner (주식 v11, 코인 v10 활성 서빙 모델 상태)
├── OperationalAutomationPanel (4대 핵심 원클릭 자동화 카드)
├── JobHistorySection (작업 이력 및 로그 모달)
└── [Condition: showAdvancedTools]
    └── AdvancedToolsSubTabs
        ├── Tab 1: Optuna HPO 튜닝 (V8OptunaPanel - v10/v8 전용)
        ├── Tab 2: 커스텀 데이터 수집 (AdvancedDataToolsPanel)
        └── Tab 3: 유니버스 종목 관리 (UniverseManagementPanel)
```

---

## 4. 검증 계획 (Verification Plan)

- ESLint 정적 분석 통과 검증 (`npx eslint .`)
- 4대 메인 카드 클릭 시 해당 프리셋(`crypto-v10-full` 등) 정상 기동 및 백그라운드 작업 이력 등록 확인
- 고급 도구 서브탭 스위칭 정상 작동 및 v6/v7 더미 제거 확인
