# PWA 도입 계획 및 재배포 체크리스트

## 1. 현재 배포 구조

현재 프로젝트는 프론트엔드와 백엔드가 분리되어 배포되어 있다.

```text
사용자 브라우저 / 모바일 브라우저
  |
  | HTTPS
  v
Vercel 프론트엔드
  - 위치: frontend/
  - 빌드: Vite React
  - 주요 진입점: frontend/src/main.jsx
  - 라우팅: frontend/src/App.jsx, frontend/src/routes/MobileRoutes.jsx, frontend/src/routes/DesktopRoutes.jsx
  - API 주소: VITE_API_BASE_URL
  |
  | API 요청
  v
AWS EC2 백엔드
  - 위치: backend/
  - 배포 경로: /home/ubuntu/teamproject
  - 실행 방식: Docker Compose
  - API 컨테이너: backend-api
  - 워커 컨테이너: backend-worker
  - 현재 기본 API 주소 예시: http://52.79.188.213
```

프론트엔드는 `frontend/package.json`의 `build` 스크립트로 Vite 정적 파일을 만들고, Vercel이 이 결과물을 배포한다.

백엔드는 `scripts/deploy_backend_aws.sh`를 통해 EC2의 `/home/ubuntu/teamproject`로 파일을 동기화한 뒤 `docker compose up -d --build backend-api`로 재기동하는 구조다.

## 2. PWA 적용 목표와 현재 저장소 상태

PWA 적용의 1차 목표는 모바일 사용자가 브라우저에서 앱처럼 설치하고, 홈 화면 아이콘으로 진입할 수 있게 만드는 것이다.

이 문서는 이미 완료된 배포 문서가 아니라 추가 작업 계획서다. 현재 저장소 기준으로 `frontend/public`에는 다음 PWA 파일이 아직 없다.

```text
frontend/public/manifest.webmanifest
frontend/public/pwa-icon-192.png
frontend/public/pwa-icon-512.png
frontend/public/service-worker.js
```

PWA 설치 가능성의 핵심은 HTTPS 환경과 web app manifest다. service worker는 설치 가능성 자체의 필수 조건으로 다루기보다, 앱 쉘 캐싱이나 오프라인 대응을 원할 때 추가하는 선택 작업으로 둔다.

이번 PWA 작업의 기본 범위는 프론트엔드에 한정한다.

```text
frontend/public/manifest.webmanifest
frontend/public/pwa-icon-192.png
frontend/public/pwa-icon-512.png
frontend/index.html

선택 작업:
frontend/src/main.jsx 또는 별도 registerServiceWorker 파일
frontend/public/service-worker.js 또는 Vite PWA 플러그인 설정
```

백엔드는 PWA 자체 때문에 반드시 수정할 필요는 없다. 다만 Vercel 도메인에서 AWS API를 호출할 때 CORS, HTTPS, 쿠키/인증 헤더, API URL 설정 문제가 있으면 백엔드 설정 변경과 AWS 재배포가 필요하다.

## 3. 작업 전 확인

1. 작업 루트 확인

```powershell
cd "D:\asdf\AE STOCK\Trading"
```

2. 프론트 빌드가 현재 통과하는지 확인

```powershell
npm.cmd --prefix frontend run build
```

3. Vercel 프론트 환경변수 확인

```text
VITE_SUPABASE_URL
VITE_SUPABASE_ANON_KEY
VITE_API_BASE_URL
```

운영 Vercel의 `VITE_API_BASE_URL`은 AWS 백엔드 주소를 가리켜야 한다. 현재 HTTP 주소를 쓰는 예시는 다음과 같다.

```text
VITE_API_BASE_URL=http://52.79.188.213
```

PWA 전환 전후의 가장 큰 리스크는 PWA 코드보다 API 도메인이 HTTP인 점이다. Vercel 프론트는 HTTPS로 제공되므로 `VITE_API_BASE_URL`이 `http://52.79.188.213`처럼 HTTP이면 로그인, 대시보드, 주문, 챗봇 호출에서 브라우저의 혼합 콘텐츠 정책에 걸릴 수 있다. 운영에서는 먼저 HTTPS API 도메인 준비 여부를 확인한다.

## 4. PWA 프론트 작업 단계

### 4.1 manifest 추가

`frontend/public/manifest.webmanifest`를 만든다.

포함할 항목:

```json
{
  "name": "AE Trading",
  "short_name": "AE Trading",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#020617",
  "theme_color": "#061321",
  "icons": [
    {
      "src": "/pwa-icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "/pwa-icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ]
}
```

### 4.2 아이콘 준비

`frontend/public` 아래에 최소 192px, 512px PNG 아이콘을 둔다.

```text
frontend/public/pwa-icon-192.png
frontend/public/pwa-icon-512.png
```

현재 `frontend/public/logo.png`, `favicon.svg`, `icons.svg`가 있으므로 기존 브랜드 이미지에서 PNG 아이콘을 파생할 수 있다.

### 4.3 index.html 연결

`frontend/index.html`의 `<head>`에 manifest와 theme color를 연결한다.

```html
<link rel="manifest" href="/manifest.webmanifest" />
<meta name="theme-color" content="#061321" />
<meta name="mobile-web-app-capable" content="yes" />
```

iOS 홈 화면 호환을 보조하려면 다음 메타와 apple touch icon을 추가할 수 있다. 다만 manifest를 우선 기준으로 두고, 이 태그들은 iOS 호환 보조용으로만 취급한다. 실제 iPhone Safari에서 홈 화면 추가, 아이콘, standalone 표시 여부를 별도로 확인해야 한다.

```html
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-title" content="AE Trading" />
<link rel="apple-touch-icon" href="/pwa-icon-192.png" />
```

### 4.4 service worker 전략 결정

초기 PWA는 먼저 manifest와 아이콘으로 설치 가능성을 확인한다. service worker는 앱 쉘 캐싱, 오프라인 안내 화면, 반복 방문 성능 개선이 필요할 때 별도 단계로 추가한다.

service worker를 추가한다면 권장 전략은 다음과 같다.

```text
정적 리소스: 캐시 가능
HTML: 네트워크 우선 또는 짧은 캐시
API 요청: 캐시하지 않음
투자/잔고/주문/챗봇 API: 반드시 네트워크 요청
```

이 프로젝트는 금융/투자 데이터를 다루므로 API 응답을 무리하게 오프라인 캐싱하면 오래된 잔고, 시세, 주문 상태, 챗봇 답변을 보여줄 수 있다. 따라서 service worker를 도입하더라도 `/api/*` 요청은 캐시 대상에서 제외하고 네트워크 요청으로 처리한다.

선택지는 두 가지다.

1. 직접 `frontend/public/service-worker.js` 작성
2. `vite-plugin-pwa` 도입

현재 `frontend/package.json`에는 PWA 플러그인이 없으므로, 의존성을 늘리지 않으려면 직접 service worker를 두는 방식이 가장 좁은 변경이다. 단, 1차 목표가 설치 가능성 확인이라면 이 단계는 생략해도 된다.

### 4.5 service worker 등록

service worker를 추가하기로 결정한 경우에만 `frontend/src/main.jsx` 또는 별도 파일에서 운영 빌드일 때 등록한다.

```js
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
  })
}
```

등록 실패는 앱 실행을 막지 않도록 `catch`에서 콘솔 경고만 남기는 방식이 안전하다.

## 5. 프론트 검증

1. 로컬 빌드

```powershell
npm.cmd --prefix frontend run build
```

2. 로컬 프리뷰

```powershell
npm.cmd --prefix frontend run preview
```

3. 브라우저 DevTools 확인

```text
Application > Manifest
Application > Service Workers: service worker를 추가한 경우에만 확인
Lighthouse > Progressive Web App
```

확인 항목:

```text
manifest가 정상 로드되는가
아이콘 192/512가 깨지지 않는가
service worker를 추가했다면 정상 등록되는가
service worker를 추가했다면 새 배포 후 이전 캐시가 과하게 남지 않는가
로그인, 대시보드, 모바일 라우트, 챗봇이 기존처럼 동작하는가
AWS API 요청이 캐시되지 않고 실시간으로 호출되는가
Vercel HTTPS 프론트에서 API 호출이 mixed content로 차단되지 않는가
```

## 6. Vercel 재배포 단계

Vercel이 Git 연동 배포라면 작업 브랜치를 push하면 자동 배포된다.

Vercel 프로젝트 설정에서 확인할 값:

```text
Framework Preset: Vite
Root Directory: frontend
Build Command: npm run build
Output Directory: dist
```

환경변수:

```text
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_API_BASE_URL=운영 AWS API 주소
```

배포 후 확인:

```text
https://배포도메인/manifest.webmanifest
https://배포도메인/pwa-icon-192.png
https://배포도메인/pwa-icon-512.png

service worker를 추가한 경우:
https://배포도메인/service-worker.js
```

모바일에서는 Chrome 또는 Edge에서 “홈 화면에 추가” 또는 “앱 설치”가 뜨는지 확인한다.

## 7. AWS 백엔드 재배포가 필요한 경우

PWA 프론트 파일만 추가했다면 AWS 백엔드 재배포는 필요 없다.

다음 중 하나라도 해당하면 AWS 백엔드 재배포가 필요하다.

```text
Vercel 운영 도메인을 CORS 허용 목록에 추가해야 하는 경우
API를 HTTPS 도메인으로 전환하는 경우
백엔드 라우트, 인증, 응답 헤더를 바꾸는 경우
PWA 설치 후 로그인/챗봇/API 호출에서 CORS 또는 mixed content 오류가 나는 경우
```

AWS 재배포는 기존 스크립트를 사용한다.

```bash
cd /path/to/Trading
./scripts/deploy_backend_aws.sh
```

스크립트 기본 대상:

```text
AWS_HOST=ubuntu@52.79.188.213
REMOTE_DIR=/home/ubuntu/teamproject
```

배포 후 백엔드 상태 확인:

```bash
curl http://52.79.188.213/api/health
```

정상 응답 예시:

```json
{"status":"ok","success":true}
```

## 8. HTTPS 주의사항

PWA 전환 전후로 가장 먼저 확인해야 할 항목은 HTTPS API 도메인이다. Vercel 프론트는 HTTPS로 제공되지만, AWS API가 `http://52.79.188.213` 그대로라면 다음 문제가 생길 수 있다.

```text
혼합 콘텐츠 차단
설치 앱 모드에서 API 호출 실패
service worker를 추가한 경우 HTTP API 요청 실패
브라우저별 동작 차이
```

운영 권장 구조:

```text
https://app.example.com       -> Vercel 프론트
https://api.example.com       -> AWS 백엔드
```

AWS 백엔드에 HTTPS를 붙이는 선택지는 다음과 같다.

```text
Nginx + Let's Encrypt
AWS ALB + ACM 인증서
Cloudflare 프록시 도메인
```

PWA 작업 전에 HTTPS API 도메인이 준비되지 않았다면, manifest 기반 설치 자체는 가능해도 로그인 후 API 기능에서 문제가 날 수 있으므로 이 부분을 먼저 검증해야 한다.

## 9. 최종 체크리스트

PWA 코드 작업:

```text
[ ] manifest.webmanifest 추가
[ ] 192/512 PNG 아이콘 추가
[ ] index.html manifest/theme 연결
[ ] iOS 보조용 apple meta/apple-touch-icon 추가 여부 결정
[ ] service worker 추가 여부 결정
[ ] service worker를 추가한다면 main.jsx에서 운영 빌드에만 등록
[ ] service worker를 추가한다면 API 요청은 캐시 대상에서 제외
```

로컬 검증:

```text
[ ] npm.cmd --prefix frontend run build 통과
[ ] npm.cmd --prefix frontend run preview로 manifest 확인
[ ] 모바일 라우트 /, /dashboard, /chatbot 확인
[ ] 로그인 상태와 Supabase 세션 확인
[ ] AWS API 요청이 정상 응답하는지 확인
```

Vercel 검증:

```text
[ ] Vercel Root Directory가 frontend인지 확인
[ ] Vercel VITE_API_BASE_URL이 HTTPS 운영 API를 가리키는지 확인
[ ] 배포 후 manifest/icon URL 직접 접속 확인
[ ] service worker를 추가했다면 service-worker.js URL 직접 접속 확인
[ ] service worker를 추가했다면 DevTools Application 탭에서 등록 확인
[ ] 모바일 브라우저에서 홈 화면 설치 확인
[ ] iOS 메타를 추가했다면 실제 iPhone Safari 홈 화면 추가 동작 확인
```

AWS 검증:

```text
[ ] 백엔드 변경이 없다면 AWS 재배포 생략
[ ] CORS/HTTPS/API 변경이 있으면 scripts/deploy_backend_aws.sh 실행
[ ] curl /api/health 확인
[ ] Vercel 도메인에서 로그인/챗봇/API 기능 확인
```

## 10. 권장 작업 순서

1. 현재 프론트 빌드 통과 여부 확인
2. 운영 API가 HTTPS 도메인으로 호출 가능한지 확인
3. manifest와 아이콘 추가
4. index.html에 manifest와 theme color 연결
5. iOS 보조 메타는 필요 시 추가하고 실제 iPhone에서 검증
6. service worker는 앱 쉘 캐싱/오프라인 대응이 필요할 때만 추가
7. service worker를 추가한다면 API 캐싱 제외
8. 로컬 build/preview 검증
9. Vercel Preview 배포에서 PWA 설치 가능 여부 확인
10. 운영 Vercel 배포
11. API 호출에서 HTTPS/CORS 문제가 있으면 백엔드 설정 후 AWS 재배포
12. 모바일 실제 기기에서 홈 화면 설치, 로그인, 챗봇, 대시보드 확인
