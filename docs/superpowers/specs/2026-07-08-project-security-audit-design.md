# 프로젝트 보안 및 더미코드 전수 감사 설계서 (Security Audit Design)

본 문서는 프로젝트 전체 소스코드의 보안 취약점, 더미 코드, API 키 사용처를 전수 조사하기 위한 분석 설계서입니다. 유저의 요청에 따라 코드 수정은 엄격히 금지하며, 오직 분석 및 보고만 수행합니다.

## 1. 목적 및 범위

* **목적**: 시스템 전반의 보안성 점검, 개발 편의를 위한 임시 더미 코드 제거 리스트 도출, 환경 변수/API 키 사용 맵핑 확보.
* **범위**: 
  * `backend/` (routes, services, utils, scripts, app.py, worker.py)
  * `frontend/src/` (components, pages, lib, App.jsx, main.jsx 등)
  * `ml/` (src, configs 등)
  * `supabase/migrations/`
* **제약 사항**: **절대 코드 수정을 수행하지 않음.** 에이전트들은 읽기 전용 도구만 사용함.

## 2. 서브에이전트 역할 및 분석 대상

1. **Subagent-1 (Backend Core & Services)**
   * **대상 경로**: `backend/services/`, `backend/utils/`
   * **임무**: 암호화 흐름([keys_service.py](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이디NG/teamproject/backend/services/keys_service.py)), 토큰 캐시([token_cache_service.py](file:///Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이디NG/teamproject/backend/services/token_cache_service.py)), 거래소 클라이언트(Toss, Coinone, Binance, KIS) 내부의 보안성 및 하드코딩 여부 진단.
2. **Subagent-2 (Backend Application & Routes)**
   * **대상 경로**: `backend/app.py`, `backend/worker.py`, `backend/routes/`, `backend/scripts/`
   * **임무**: 라우트 권한 검증 및 에러 응답 체계, 백그라운드 워커 및 배치 스크립트의 자격 증명 사용 방식 점검.
3. **Subagent-3 (Frontend & Database)**
   * **대상 경로**: `frontend/src/`, `supabase/migrations/`
   * **임무**: 프론트엔드 환경 변수 노출(VITE_ 접두사 규칙 준수), 인증 처리, DB RLS 정책 적용 상태 점검.
4. **Subagent-4 (Machine Learning)**
   * **대상 경로**: `ml/`
   * **임무**: 학습/예측 스크립트, 데이터 수집 파이프라인 자격 증명 관리 상태 점검.

## 3. 감사 기준 (Security Checklist)

1. **자격증명 하드코딩**: 평문 API Key, Secret Key, Token, Password 검색.
2. **환경 변수 매핑**: `.env.example`에 정의된 각 환경 변수의 실제 사용처 매핑.
3. **보안 취약점 Audit**:
   * raw 에러 페이로드 유출 여부.
   * CORS 설정의 적절성.
   * Supabase RLS 정책 설정 현황.
4. **더미 및 Dead Code 검출**:
   * 디버그 로그(`console.log`, `print`), 주석 처리된 레거시 코드, 하드코딩 더미 데이터.

## 4. 최종 결과물 형식
* 취합된 마크다운 보고서로 작성하여 전달.
