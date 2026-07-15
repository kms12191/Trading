# 관리자 종목 마스터 정리 기능 구현 계획

## 1. 목적

DB에 임시 또는 오류 심볼이 남는 문제를 관리자 화면에서 점검하고 정리할 수 있게 한다.

예시:

- `SKHYV` 같은 임시 해외주식 심볼이 랭킹 수집 또는 온디맨드 backfill 과정에서 DB에 적재됨
- 이후 실제 브로커/API 기준으로 더 이상 존재하지 않거나 유효하지 않음
- 관리자 화면에서 해당 심볼을 발견하고 비활성화 또는 삭제할 수 있어야 함

## 2. 핵심 원칙

- `kis_stock_turnover_latest`는 랭킹/시세 캐시 테이블이므로 비교적 적극적으로 정리할 수 있다.
- `kis_stock_master`는 종목명/종목코드 기준 DB이므로 기본 정리는 hard delete가 아니라 `is_active=false` 비활성화다.
- 실제 삭제는 참조가 없는 항목만 관리자 승인 후 수행한다.
- 랭킹 목록에 없다는 이유만으로 삭제하면 안 된다. 랭킹 밖 정상 종목일 수 있다.
- 가능한 한 브로커/API 존재 확인 결과, 마지막 갱신 시각, 참조 개수를 함께 사용해 판단한다.
- 관리자 작업 결과는 반드시 이력 테이블에 남긴다.

## 3. 현재 관련 테이블

### 3.1 `kis_stock_master`

주식 종목 마스터 테이블이다.

주요 역할:

- 종목코드와 종목명 검색
- `/api/symbol/lookup`의 주식 기준 데이터
- 자동완성 후보 제공
- 해외주식 온디맨드 backfill 저장 대상

정리 정책:

- 기본 작업은 `is_active=false`
- hard delete는 참조가 없고 비활성 기간이 충분할 때만 허용

### 3.2 `kis_stock_turnover_latest`

주식 랭킹/시세 스냅샷 캐시 테이블이다.

주요 역할:

- 홈/랭킹 화면의 거래대금, 거래량, 상승률, 하락률 기준 데이터
- `kis_stock_master`에 없는 해외주식의 보조 lookup 소스

정리 정책:

- 오래 갱신되지 않았거나 실제 존재 확인에 실패한 항목은 삭제 후보가 될 수 있다.
- 단, 참조가 있는 경우 삭제하지 않는다.

## 4. 관리자 UI 요구사항

위치:

```text
관리자 페이지 > 시장 데이터 관리 > 종목 마스터 정리
```

필수 기능:

- 스캔 실행
- 최신 스캔 결과 조회
- 의심 심볼 목록 표시
- 상태별 필터
- 선택 비활성화
- 선택 삭제
- 비활성 심볼 복구

### 4.1 요약 카드

최신 스캔 결과 상단에 다음 값을 표시한다.

- 전체 검사 심볼 수
- 정상 수
- 의심 수
- 비활성 예정 수
- 비활성 수
- 삭제 가능 수
- 스캔 시작 시각
- 스캔 종료 시각
- 스캔 상태

### 4.2 필터

다음 필터를 제공한다.

- 전체
- 정상
- 의심
- 비활성 예정
- 비활성
- 삭제 가능

### 4.3 결과 테이블 컬럼

테이블에는 다음 컬럼을 표시한다.

- 선택 체크박스
- 심볼
- 종목명
- 시장 국가
- 시장 구분
- 원천 테이블
- 상태
- 사유
- 마지막 갱신 시각
- 참조 개수
- 권장 작업
- 행별 액션

### 4.4 행별 액션

각 행은 다음 액션을 제공한다.

- 상세
- 비활성화
- 삭제
- 복구

삭제 버튼은 `reference_count=0`이고 서버가 재검증했을 때만 성공해야 한다.

## 5. 백엔드 API 계획

관리자 권한 확인은 기존 관리자 API 패턴을 따른다.

### 5.1 최신 결과 조회

```http
GET /api/admin/market-symbols/reconciliation/latest
```

역할:

- 최신 reconciliation run 조회
- 해당 run의 item 목록 조회
- 관리자 화면 초기 렌더링에 사용

응답 예시:

```json
{
  "success": true,
  "data": {
    "run": {
      "id": "uuid",
      "status": "COMPLETED",
      "checked_count": 4120,
      "normal_count": 4090,
      "suspicious_count": 18,
      "deactivation_candidate_count": 7,
      "deletable_count": 5
    },
    "items": []
  }
}
```

### 5.2 스캔 실행

```http
POST /api/admin/market-symbols/reconcile
```

역할:

- `kis_stock_master`와 `kis_stock_turnover_latest`의 심볼 목록을 읽는다.
- 브로커/API 기준으로 존재 여부를 확인한다.
- 참조 개수를 계산한다.
- run 및 item 결과를 DB에 저장한다.

권장 요청 body:

```json
{
  "market_country": "ALL",
  "dry_run": true,
  "limit": 1000
}
```

주의:

- 1차 구현에서는 실제 삭제 또는 비활성화를 수행하지 않는다.
- 이 API는 스캔 결과 저장까지만 담당한다.

### 5.3 선택 비활성화

```http
POST /api/admin/market-symbols/deactivate
```

역할:

- 선택된 `kis_stock_master` 심볼을 `is_active=false`로 변경한다.
- 작업 이력을 남긴다.

요청 예시:

```json
{
  "symbols": ["SKHYV"],
  "reason": "브로커 존재 확인 실패"
}
```

### 5.4 선택 삭제

```http
POST /api/admin/market-symbols/delete
```

역할:

- 선택된 심볼을 삭제한다.
- 삭제 전 서버에서 참조 개수를 다시 계산한다.
- 참조가 있으면 삭제하지 않는다.

요청 예시:

```json
{
  "symbols": ["SKHYV"],
  "source_table": "kis_stock_turnover_latest"
}
```

삭제 허용 조건:

- 참조 개수 0
- 관리자 권한 확인 완료
- `kis_stock_turnover_latest` 항목이거나, `kis_stock_master`에서 비활성 상태이고 보존 기간이 지남

### 5.5 비활성 복구

```http
POST /api/admin/market-symbols/restore
```

역할:

- `kis_stock_master.is_active=true`로 복구한다.
- 복구 이력을 남긴다.

## 6. 신규 DB 테이블 계획

### 6.1 `admin_symbol_reconciliation_runs`

스캔 실행 단위 이력을 저장한다.

컬럼:

- `id`
- `started_at`
- `finished_at`
- `status`
- `checked_count`
- `normal_count`
- `suspicious_count`
- `deactivation_candidate_count`
- `deletable_count`
- `raw_summary`
- `created_by`

상태 예시:

- `RUNNING`
- `COMPLETED`
- `FAILED`

### 6.2 `admin_symbol_reconciliation_items`

스캔 결과의 개별 심볼 판정 결과를 저장한다.

컬럼:

- `id`
- `run_id`
- `symbol`
- `name`
- `source_table`
- `market_country`
- `market_segment`
- `status`
- `reason`
- `suggested_action`
- `broker_check_result`
- `reference_count`
- `last_seen_at`
- `created_at`

상태 예시:

- `NORMAL`
- `SUSPICIOUS`
- `DEACTIVATION_CANDIDATE`
- `INACTIVE`
- `DELETABLE`

권장 작업 예시:

- `NONE`
- `REVIEW`
- `DEACTIVATE`
- `DELETE_CACHE`
- `DELETE_MASTER`
- `RESTORE`

## 7. 판정 정책

### 7.1 `kis_stock_turnover_latest`

삭제 가능 후보 조건:

- 브로커/API 존재 확인 실패
- 또는 3일 이상 갱신 없음
- 참조 개수 0

권장 처리:

- `DELETABLE`
- `suggested_action=DELETE_CACHE`

### 7.2 `kis_stock_master`

판정 기준:

- 1회 확인 실패: `SUSPICIOUS`
- 3회 연속 확인 실패: `DEACTIVATION_CANDIDATE`
- 관리자 승인 후: `is_active=false`
- 참조 0개 + 비활성 7일 경과 + 관리자 승인: hard delete 가능

권장 처리:

- 기본은 `DEACTIVATE`
- hard delete는 마지막 단계로 제한

## 8. 참조 개수 확인 대상

삭제 전 다음 테이블에서 `symbol` 또는 `ticker` 참조 여부를 확인한다.

- `user_watchlist` 또는 현재 관심종목 테이블
- `trade_proposals`
- `broker_order_history`
- `auto_trading_rules`
- 기타 프로젝트 내 `symbol` 또는 `ticker` 기반 금융 데이터 테이블

참조가 하나라도 있으면 hard delete를 금지한다.

## 9. 구현 순서

### 1차 구현

1. migration 추가
   - `admin_symbol_reconciliation_runs`
   - `admin_symbol_reconciliation_items`

2. 백엔드 서비스 추가
   - DB 심볼 수집
   - 브로커/API 존재 확인
   - 참조 개수 계산
   - 판정 상태 생성
   - 결과 저장

3. 관리자 API 추가
   - 최신 결과 조회
   - 스캔 실행
   - 비활성화
   - 삭제
   - 복구

4. 관리자 UI 추가
   - 요약 카드
   - 필터
   - 결과 테이블
   - 행별 액션

5. 안전 검증
   - 참조 있는 심볼 삭제 차단
   - 관리자 권한 없는 요청 차단
   - 실패 응답에 `format_error_payload()` 사용

### 2차 구현

- 자동 비활성화 스케줄러
- 반복 실패 횟수 누적
- 비활성 7일 경과 자동 삭제 후보화
- 관리자 알림 또는 배지 추가

## 10. 반드시 지킬 안전장치

- hard delete 전에는 서버에서 참조 개수를 다시 계산한다.
- 삭제 API는 클라이언트가 보낸 `reference_count`를 신뢰하지 않는다.
- 거래내역, 관심종목, 자동매매 규칙에 참조가 있으면 삭제하지 않는다.
- `kis_stock_master`는 기본적으로 삭제하지 않고 비활성화한다.
- 모든 관리자 작업은 작업 이력을 남긴다.
- 모든 실패 응답은 `format_error_payload()`를 사용한다.
- 사용자에게 raw exception, stack trace, 외부 API raw payload를 직접 노출하지 않는다.

## 11. 완료 기준

- 관리자가 스캔을 실행할 수 있다.
- 스캔 결과가 DB에 저장된다.
- 최신 스캔 결과를 관리자 화면에서 볼 수 있다.
- `SKHYV` 같은 임시 심볼이 의심 또는 삭제 가능 후보로 표시된다.
- `kis_stock_master` 항목은 관리자 승인으로 비활성화할 수 있다.
- 참조 없는 `kis_stock_turnover_latest` 항목은 관리자 승인으로 삭제할 수 있다.
- 참조가 있는 심볼은 삭제 요청이 실패한다.
- 관리자 권한이 없는 사용자는 API를 사용할 수 없다.

