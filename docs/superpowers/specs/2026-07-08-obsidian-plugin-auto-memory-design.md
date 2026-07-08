# Obsidian 플러그인 자동메모리 설계서

## 1. 목적

본 설계는 트레이딩 앱의 자동 사용자 메모리, 앱 내 투자노트 템플릿, Obsidian Vault, Supabase Vector DB, LLM 챗봇을 하나의 지식 흐름으로 연결하기 위한 1차 내부 시연용 구조를 정의한다.

핵심 목표는 다음과 같다.

- 사용자가 Obsidian에서 투자 원칙과 매매 회고를 직접 작성할 수 있다.
- 앱은 사용자의 행동 패턴을 자동메모리로 요약한다.
- Obsidian 플러그인은 투자노트 템플릿을 Vault에 생성하고, 노트를 앱과 동기화한다.
- 앱에서 생성된 자동메모리는 Obsidian의 지정된 자동 영역에만 반영된다.
- 동기화된 노트와 자동메모리는 Vector DB에 색인되어 챗봇 답변 근거로 사용된다.
- 챗봇은 매매 주문을 직접 실행하지 않고, 필요 시 사용자 승인용 제안만 만든다.

---

## 2. 핵심 개념

### 2.1 자동메모리

자동메모리는 앱이 관찰한 사용자 행동을 요약한 기억이다.

예시는 다음과 같다.

- 사용자는 최근 30일간 삼성전자와 BTC를 반복적으로 확인했다.
- 사용자는 코인 질문에서 수익 가능성보다 리스크를 먼저 확인하는 답변을 선호한다.
- 사용자는 고변동 종목 매수 제안을 자주 거절했다.
- 사용자는 매수 전 손절 기준을 명시하는 답변에 더 잘 반응한다.

자동메모리는 원본 로그 전체가 아니라, 민감정보를 제거한 요약 fact로 저장한다.

### 2.2 앱 투자노트

앱 투자노트는 사용자가 앱 내부에서 템플릿 기반으로 작성할 수 있는 Markdown 호환 노트다. Obsidian을 모르는 사용자도 사용할 수 있어야 하며, 2차 확장 단계에서 Obsidian으로 내보내거나 가져올 수 있어야 한다.

대표 템플릿은 다음과 같다.

- 나의 투자 원칙
- 매매 전 체크리스트
- 손실 회고
- 종목 분석 노트
- 뉴스/공시 해석 노트
- 포트폴리오 리밸런싱 노트

### 2.3 Obsidian

Obsidian은 사용자가 앱 밖에서 직접 소유하고 관리하는 Markdown 기반 투자 지식 저장소다.

본 설계에서 Obsidian은 앱의 필수 저장소가 아니라, 고급 사용자를 위한 외부 편집 및 소유 계층이다. 사용자는 Obsidian에서 노트를 자유롭게 수정하고, 플러그인을 통해 앱으로 동기화할 수 있다.

### 2.4 Vector DB

Vector DB는 자동메모리, 투자노트, Obsidian 노트, 뉴스, DART 공시를 의미 기반으로 검색하기 위한 색인 계층이다.

원본 데이터는 각 도메인 테이블에 저장하고, 검색용 chunk와 embedding만 `knowledge_chunks`에 저장한다.

### 2.5 LLM 챗봇

챗봇은 다음 자료를 조합해 답변한다.

- Obsidian 또는 앱 투자노트에 기록된 사용자 원칙
- 자동메모리에서 추론한 사용자 행동 패턴
- 뉴스, 공시, 시세, ML 신호
- 현재 보유자산과 조건감시 설정

챗봇은 사용자 승인 없이 실거래 주문을 실행하지 않는다.

---

## 3. 1차 내부 시연 범위

1차는 일반 사용자 배포가 아니라 내부 시연용 플러그인으로 제한한다.

### 포함 범위

- Obsidian 플러그인 설정 화면
- API Base URL 입력
- 내부 테스트 토큰 입력
- 동기화 폴더명 설정, 기본값 `AI-Trading`
- 기본 투자노트 템플릿 생성
- 현재 노트 앱으로 동기화
- `AI-Trading` 폴더 전체 앱으로 동기화
- 앱 자동메모리 가져오기
- 자동메모리 marker 영역만 Obsidian 파일에 반영
- 앱 DB 저장 및 Vector DB 색인 대상 등록

### 제외 범위

- Obsidian 커뮤니티 플러그인 마켓 배포
- OAuth 기반 로그인 연결
- 완전 자동 백그라운드 양방향 동기화
- 삭제 동기화
- 복잡한 충돌 병합
- 사용자의 직접 작성 영역 자동 덮어쓰기
- API Key, 계좌번호, 인증정보 등 민감정보 노트 저장

---

## 4. 전체 아키텍처

```text
Obsidian Vault
    |
    v
Obsidian Plugin
    |
    | Markdown sync API
    v
Flask Backend
    |
    +-- note sync service
    +-- user memory service
    +-- knowledge indexing service
    |
    v
Supabase DB
    |
    +-- user_notes 또는 obsidian_documents
    +-- user_memory_facts
    +-- knowledge_chunks
    |
    v
RAG Retrieval
    |
    v
LLM Chatbot
```

데이터 흐름은 다음과 같다.

```text
사용자 행동
-> 앱 이벤트 기록
-> 자동메모리 요약
-> user_memory_facts 저장
-> knowledge_chunks 색인

Obsidian 노트
-> 플러그인 동기화
-> 원본 Markdown 저장
-> knowledge_chunks 색인

챗봇 질문
-> Vector DB 검색
-> 사용자 원칙 + 자동메모리 + 시장정보 조립
-> 안전 정책 적용
-> 답변 또는 승인 대기 제안 생성
```

---

## 5. Obsidian 플러그인 설계

### 5.1 플러그인 명령어

1차 내부 시연용 플러그인은 다음 명령어를 제공한다.

```text
AI Trading: 기본 투자노트 템플릿 생성
AI Trading: 현재 노트 앱으로 동기화
AI Trading: AI-Trading 폴더 전체 동기화
AI Trading: 자동메모리 가져오기
```

### 5.2 설정 항목

```text
apiBaseUrl: Flask API 주소
testToken: 내부 시연용 사용자 토큰
syncFolder: 동기화 폴더명, 기본값 AI-Trading
enableAutoMemoryPull: 자동메모리 가져오기 허용 여부
```

1차에서는 사용자가 직접 토큰을 입력한다. 일반 배포형으로 전환할 때 OAuth 또는 앱 연결 코드 방식으로 교체한다.

### 5.3 생성 폴더 구조

플러그인은 기본 템플릿 생성 시 다음 구조를 만든다.

```text
AI-Trading/
  00_나의_투자원칙.md
  01_매매전_체크리스트.md
  02_손실회고.md
  자동메모리/
    관심종목_자동요약.md
    반복실수_자동요약.md
  종목분석/
    README.md
```

### 5.4 Markdown frontmatter

템플릿 노트는 앱이 식별하기 쉽도록 frontmatter를 포함한다.

```markdown
---
source: ai-trading
template_key: investing-principles
sync_id:
symbol:
market:
tags: [ai-trading, principle]
---

# 나의 투자 원칙
```

`sync_id`는 앱에 최초 저장된 뒤 백엔드가 반환하는 고유 ID다. 이후 같은 Obsidian 파일과 앱 DB 레코드를 연결하는 데 사용한다.

---

## 6. 자동메모리 Marker 규칙

앱이 Obsidian 파일을 자동으로 수정할 수 있는 범위는 marker 사이로 제한한다.

예시는 다음과 같다.

```markdown
# 관심종목 자동요약

<!-- ai-trading:auto-memory:start -->
- 사용자는 최근 삼성전자와 BTC를 반복적으로 확인했습니다.
- 코인 질문에서는 리스크를 먼저 확인하는 경향이 있습니다.
<!-- ai-trading:auto-memory:end -->

## 내 메모
여기는 사용자가 자유롭게 작성합니다.
```

규칙은 다음과 같다.

- 플러그인은 marker 사이의 내용만 앱 자동메모리로 교체한다.
- marker 밖의 사용자 작성 내용은 절대 수정하지 않는다.
- marker가 없으면 플러그인은 자동으로 새 marker 블록을 추가하되, 기존 본문은 보존한다.
- 자동메모리 노트에 민감정보가 포함되면 백엔드에서 내려주지 않는다.
- 자동메모리 갱신 전후 content hash를 기록한다.

---

## 7. 백엔드 API 설계

### 7.1 노트 동기화

```text
POST /api/knowledge/obsidian/sync-note
```

요청 예시:

```json
{
  "sync_id": "optional-existing-id",
  "vault_name": "My Vault",
  "file_path": "AI-Trading/00_나의_투자원칙.md",
  "title": "나의 투자 원칙",
  "content": "# 나의 투자 원칙\n...",
  "frontmatter": {
    "template_key": "investing-principles",
    "symbol": "",
    "market": "",
    "tags": ["ai-trading", "principle"]
  },
  "content_hash": "sha256-hash",
  "modified_at": "2026-07-08T12:00:00Z"
}
```

응답 예시:

```json
{
  "success": true,
  "data": {
    "sync_id": "note-id",
    "status": "CREATED",
    "indexed": true
  }
}
```

상태값은 다음 중 하나다.

```text
CREATED
UPDATED
SKIPPED_UNCHANGED
REJECTED_SENSITIVE
FAILED
```

### 7.2 폴더 일괄 동기화

```text
POST /api/knowledge/obsidian/sync-batch
```

여러 Markdown 문서를 배열로 보낸다. 백엔드는 각 문서를 개별 검증하고 결과를 문서별로 반환한다.

### 7.3 자동메모리 조회

```text
GET /api/knowledge/obsidian/auto-memory
```

응답 예시:

```json
{
  "success": true,
  "data": {
    "favorite_symbols": [
      "사용자는 최근 삼성전자와 BTC를 반복적으로 확인했습니다."
    ],
    "repeated_mistakes": [
      "최근 30일간 손절 기준 없이 매수 검토한 기록이 증가했습니다."
    ],
    "risk_preferences": [
      "사용자는 고변동 코인 제안에서 리스크 설명을 먼저 확인하는 편입니다."
    ],
    "generated_at": "2026-07-08T12:00:00Z"
  }
}
```

---

## 8. DB 저장 구조

1차 내부 시연에서는 기존 RAG 계획과 호환되도록 다음 구조를 사용한다.

### 8.1 노트 원본

```text
user_notes 또는 obsidian_documents
- id
- user_id
- vault_name
- file_path
- title
- content
- content_hash
- frontmatter
- template_key
- symbol
- market
- tags
- modified_at
- created_at
- updated_at
- deleted_at
```

### 8.2 자동메모리

```text
user_memory_facts
- id
- user_id
- memory_type
- content
- confidence
- source
- evidence_count
- last_seen_at
- expires_at
- is_active
```

### 8.3 검색 인덱스

```text
knowledge_chunks
- id
- user_id
- source_type
- source_id
- symbol
- market
- chunk_text
- embedding
- metadata
- importance_score
- freshness_score
- content_hash
```

`source_type` 값은 다음을 사용한다.

```text
OBSIDIAN_NOTE
USER_NOTE
USER_MEMORY
NEWS
DART
TRADE_EVENT
CHAT
```

---

## 9. Vector DB 색인 흐름

노트가 앱에 저장되면 다음 과정을 거친다.

```text
Markdown 원본 저장
-> 민감정보 필터
-> chunk 분리
-> embedding 생성
-> knowledge_chunks upsert
-> 챗봇 검색 대상에 포함
```

중복 방지는 `source_type + source_id + chunk_index + content_hash` 기준으로 한다.

Obsidian 노트가 변경되면 기존 같은 `source_id` chunk를 비활성화하거나 삭제한 뒤 새 chunk를 저장한다.

---

## 10. 보안 및 민감정보 정책

자동메모리와 Obsidian 동기화에서 다음 정보는 저장하거나 Vector DB에 색인하지 않는다.

- API Key
- Secret Key
- Access Token
- 계좌번호
- 주민등록번호 또는 신분증 정보
- 전화번호 전체
- 이메일 인증 토큰
- 거래소 raw credential payload
- 사용자가 명시적으로 저장 제외한 문장

민감정보가 감지되면 백엔드는 다음 중 하나를 수행한다.

```text
1. 저장 거부
2. 민감 부분 마스킹 후 저장
3. Vector DB 색인 제외
```

1차 내부 시연에서는 안전을 위해 저장 거부를 기본값으로 한다.

---

## 11. 충돌 처리 정책

1차 내부 시연에서는 충돌 처리를 단순화한다.

### Obsidian -> 앱

- `sync_id`가 있으면 해당 문서 업데이트
- `sync_id`가 없으면 `user_id + vault_name + file_path`로 기존 문서 탐색
- `content_hash`가 같으면 `SKIPPED_UNCHANGED`
- `content_hash`가 다르면 앱 DB 업데이트

### 앱 -> Obsidian

- 자동메모리 marker 영역만 수정
- marker 밖의 본문은 수정하지 않음
- 일반 투자노트 본문은 앱이 자동 덮어쓰지 않음

### 삭제

1차 내부 시연에서는 삭제 동기화를 하지 않는다. 삭제는 앱 DB에서 `deleted_at` 기반 soft delete를 지원하되, Obsidian 파일 삭제까지 자동 반영하지 않는다.

---

## 12. 챗봇 활용 방식

챗봇은 사용자 질문을 받으면 다음 순서로 컨텍스트를 구성한다.

```text
1. 질문에서 종목, 시장, 기간, 의도 추출
2. 사용자의 Obsidian/투자노트 검색
3. 자동메모리 검색
4. 뉴스, DART, 시세, ML 신호 조회
5. 답변 생성
6. 매매 요청이면 PENDING 제안만 생성
```

예시 질문:

```text
내 투자 원칙 기준으로 삼성전자 지금 들어가도 될까?
```

답변은 다음 정보를 함께 사용한다.

- `00_나의_투자원칙.md`
- `종목분석/삼성전자_005930.md`
- 자동메모리의 관심 종목 및 리스크 선호
- 최신 뉴스와 DART 공시
- ML 신호와 현재 보유 여부

---

## 13. 1차 시연 시나리오

1차 시연은 다음 흐름을 성공 기준으로 삼는다.

```text
1. Obsidian에서 플러그인 설정에 API URL과 테스트 토큰 입력
2. "AI Trading: 기본 투자노트 템플릿 생성" 실행
3. `00_나의_투자원칙.md`에 투자 원칙 작성
4. "AI Trading: AI-Trading 폴더 전체 동기화" 실행
5. 앱 DB에 노트 저장
6. 노트 내용이 Vector DB 색인 대상이 됨
7. 챗봇에 "내 투자 원칙 기준으로 삼성전자 어때?" 질문
8. 챗봇이 Obsidian 노트를 근거로 답변
9. 앱에서 자동메모리 생성
10. Obsidian에서 "AI Trading: 자동메모리 가져오기" 실행
11. `자동메모리/관심종목_자동요약.md`의 marker 영역만 갱신
```

---

## 14. 2차 배포형 전환 조건

1차 내부 시연이 안정화되면 다음 항목을 충족한 뒤 일반 사용자 배포형으로 확장한다.

- 테스트 토큰 방식 제거
- 앱 연결 코드 또는 OAuth 기반 연결
- 플러그인 설정 UX 개선
- 충돌 감지 UI 제공
- 삭제 동기화 정책 확정
- 민감정보 감지 로그와 사용자 알림 제공
- 자동 동기화 주기 설정
- Obsidian 커뮤니티 플러그인 배포 가능성 검토

---

## 15. 열린 결정 사항

다음 항목은 구현 계획 전 회의에서 확정한다.

- 노트 원본 테이블명을 `user_notes`로 새로 둘지, `obsidian_documents`로 둘지
- 앱 내부 투자노트와 Obsidian 노트를 같은 테이블에 저장할지 분리할지
- 자동메모리 노트를 사용자가 수정했을 때 앱으로 다시 가져올지 여부
- 자동메모리 항목별 사용자가 숨김/삭제할 수 있는 UI 범위
- Vector DB 색인 시 뉴스/DART와 개인 노트의 랭킹 가중치
- 플러그인 내부 테스트 토큰 발급 방식

---

## 16. 설계 결론

1차는 내부 시연용 Obsidian 플러그인으로 시작한다.

핵심은 플러그인이 모든 것을 자동으로 덮어쓰는 것이 아니라, 다음 두 흐름을 안전하게 연결하는 것이다.

```text
Obsidian에서 사용자가 직접 쓴 투자 지식
-> 앱 DB
-> Vector DB
-> 챗봇 답변 근거

앱에서 요약한 자동메모리
-> Obsidian marker 영역
-> 사용자가 읽고 보완 가능한 외부 지식
```

이 구조는 내부 시연에서는 빠르게 검증할 수 있고, 이후 일반 사용자용 로그인/충돌처리/자동동기화로 확장할 수 있다.
