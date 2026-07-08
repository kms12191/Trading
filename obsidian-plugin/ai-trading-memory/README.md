# AI Trading Memory Obsidian Plugin

내부 시연용 Obsidian 플러그인입니다. 투자노트 템플릿 생성, Obsidian 노트의 앱 동기화, 앱 자동메모리의 marker 영역 반영을 검증합니다.

## 1차 범위

- `AI Trading: 기본 투자노트 템플릿 생성`
- `AI Trading: 현재 노트 앱으로 동기화`
- `AI Trading: AI-Trading 폴더 전체 동기화`
- `AI Trading: 자동메모리 가져오기`

## 설치 방법

1. 이 폴더 전체를 Obsidian Vault의 플러그인 폴더로 복사합니다.

```text
<Vault>/.obsidian/plugins/ai-trading-memory/
```

2. Obsidian을 다시 열거나 Community plugins 화면을 새로고침합니다.

3. Community plugins에서 `AI Trading Memory`를 활성화합니다.

4. 설정 화면에서 값을 입력합니다.

```text
API Base URL: http://localhost:5050
테스트 토큰: 내부 시연용 Bearer 토큰
동기화 폴더: AI-Trading
```

## 내부 시연 흐름

1. 명령 팔레트에서 `AI Trading: 기본 투자노트 템플릿 생성` 실행
2. `AI-Trading/00_나의_투자원칙.md` 작성
3. `AI Trading: AI-Trading 폴더 전체 동기화` 실행
4. 앱 DB와 Vector DB 색인 흐름 확인
5. 앱에서 자동메모리 생성
6. `AI Trading: 자동메모리 가져오기` 실행
7. `자동메모리/*.md` 파일의 marker 영역만 갱신되는지 확인

## 자동수정 안전 규칙

플러그인은 marker 사이의 내용만 자동으로 교체합니다.

```markdown
<!-- ai-trading:favorite-symbols:start -->
- 자동메모리 내용
<!-- ai-trading:favorite-symbols:end -->
```

marker 밖의 사용자 직접 작성 내용은 수정하지 않습니다.

## API 계약

### POST `/api/knowledge/obsidian/sync-note`

현재 노트 또는 폴더 내 Markdown 노트를 앱으로 전송합니다.

### GET `/api/knowledge/obsidian/auto-memory`

앱에서 생성된 자동메모리 요약을 가져옵니다.

응답 예시는 다음 구조를 기대합니다.

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
    ]
  }
}
```

## 테스트

플러그인 핵심 유틸은 Obsidian 없이 Node.js로 테스트할 수 있습니다.

```bash
npm --prefix obsidian-plugin/ai-trading-memory test
```
