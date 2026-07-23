# AWS EC2 백엔드 배포 가이드

이 문서는 현재 프로젝트의 Flask 백엔드를 AWS EC2에 Docker Compose로 배포하고, 이후 코드 수정 후 다시 배포하는 절차를 정리한 가이드입니다. 로컬 프론트엔드 또는 추후 Vercel 프론트엔드는 AWS 백엔드 API에 연결하고, 백그라운드 자동매매/조건감시 기능은 `backend-worker` 컨테이너가 담당합니다. AI 위탁 실거래 코드를 수정한 배포에서는 API와 worker를 반드시 같은 이미지 버전으로 함께 재시작합니다.

## 1. 현재 배포 구조

```text
[Mac 로컬 프로젝트]
  |
  | rsync + ssh
  v
[AWS EC2 Ubuntu]
  /home/ubuntu/teamproject
    |
    +-- backend-api     Flask + gunicorn, 외부 80번 포트로 API 제공
    +-- backend-worker  조건감시/자동매매/백그라운드 작업
```

현재 기본 접속 정보는 다음과 같습니다.

```text
EC2 사용자: ubuntu
Elastic IP: 52.79.188.213
서버 프로젝트 경로: /home/ubuntu/teamproject
로컬 키 파일: ~/Downloads/AE.pem
```

API health check 주소:

```bash
curl http://52.79.188.213/api/health
```

정상 응답:

```json
{"status":"ok","success":true}
```

## 2. AWS 보안그룹 이해

EC2 인스턴스는 보안그룹 인바운드 규칙으로 외부 접근을 제한합니다.

필수 규칙:

```text
SSH   TCP 22   내 IP/32
HTTP  TCP 80   0.0.0.0/0
HTTPS TCP 443  0.0.0.0/0
```

현재 백엔드는 HTTP 80번으로 열려 있습니다. 그래서 `curl http://52.79.188.213/api/health`가 성공하면 서버와 API는 살아있는 것입니다.

SSH 22번은 보안을 위해 `내 IP/32`만 여는 것을 권장합니다. 카페, 학원, 핫스팟처럼 네트워크가 바뀌면 내 공인 IP가 바뀌기 때문에 SSH가 timeout 날 수 있습니다.

현재 Mac의 공인 IP 확인:

```bash
curl https://checkip.amazonaws.com
```

예를 들어 결과가 `211.234.197.130`이면 SSH 인바운드 소스는 다음처럼 맞춰야 합니다.

```text
211.234.197.130/32
```

SSH 연결이 안 될 때 포트 확인:

```bash
nc -vz 52.79.188.213 22
```

결과 해석:

```text
succeeded/open       22번 포트 접근 가능
Operation timed out  보안그룹, 현재 IP, 네트워크 차단 문제
Connection refused   서버는 닿지만 SSH 데몬 문제
```

급할 때만 SSH를 임시로 `0.0.0.0/0`으로 열 수 있습니다. 배포가 끝나면 반드시 다시 `내 IP/32`로 줄여야 합니다.

### 코인원 API IP 허용 목록

AI 위탁 실거래에서 코인원 주문은 EC2 worker 컨테이너가 전송합니다. 따라서 코인원 API 키의 IP 허용 목록에는 개발 Mac IP가 아니라 worker의 실제 외부 송신 IP를 등록해야 합니다.

EC2에서 확인:

```bash
docker compose exec backend-worker curl -s https://checkip.amazonaws.com
```

직접 인터넷에 연결된 EC2는 보통 Elastic IP가 보이고, NAT Gateway를 경유하는 사설 서브넷은 NAT Gateway의 Elastic IP가 보입니다. 표시된 IP를 코인원 API 키의 허용 목록에 등록한 뒤에만 실주문을 시작합니다.

## 3. 터미널에서 AWS 접속

Mac 터미널에서 접속합니다.

```bash
ssh -i ~/Downloads/AE.pem ubuntu@52.79.188.213
```

접속되면 프롬프트가 다음처럼 바뀝니다.

```text
ubuntu@ip-172-31-1-95:~$
```

서버의 프로젝트 폴더로 이동:

```bash
cd /home/ubuntu/teamproject
```

서버에서 빠져나오기:

```bash
exit
```

## 4. Docker Compose 서비스

현재 [docker-compose.yml](docker-compose.yml)은 두 서비스를 정의합니다.

### backend-api

역할:

```text
Flask API 서버
gunicorn으로 실행
외부 80번 포트 -> 컨테이너 5050번 포트 연결
```

실행 명령:

```text
gunicorn -b 0.0.0.0:5050 -w 2 --timeout 120 --access-logfile - --error-logfile - app:app
```

헬스체크:

```bash
curl http://localhost:5050/api/health
```

### backend-worker

역할:

```text
조건감시 자동/반자동 매도
자동매매 백그라운드 루프
일부 스케줄러성 작업
```

실행 명령:

```text
python worker.py
```

`backend-worker`는 `profiles: worker`로 분리되어 있습니다. 따라서 `docker compose up -d --build backend-api`만 실행하면 worker가 새로 자동 실행되지는 않습니다.

자동매매/챗봇 조건감시 테스트가 필요하면 worker도 명시적으로 실행해야 합니다.

```bash
docker compose --profile worker up -d --build backend-worker
```

## 5. 환경변수 관리

Docker Compose는 서버의 다음 파일을 읽습니다.

```text
/home/ubuntu/teamproject/backend/.env
```

이 파일은 비밀값을 담기 때문에 Git, rsync, Docker image에 포함하지 않습니다. 로컬 `.dockerignore`와 배포 스크립트에서도 `.env`는 제외합니다.

필수 환경변수 예시:

```env
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
ENCRYPTION_KEY=...
OPENAI_API_KEY=...
```

거래소 기능에 필요한 값:

```env
TOSS_API_KEY=...
TOSS_SECRET_KEY=...
KIS_APPKEY=...
KIS_APPSECRET=...
COINONE_ACCESS_TOKEN=...
COINONE_SECRET_KEY=...
BINANCE_API_KEY=...
BINANCE_SECRET_KEY=...
```

RAG/임베딩 관련 값:

```env
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_TIMEOUT_SECONDS=30
```

worker 관련 값:

```env
SCHEDULER_RUN_IN_GATEWAY=false
WORKER_MODE=trading
AUTO_TRADING_RULES_ENABLED=true
AUTO_TRADING_RULES_INTERVAL_SECONDS=10
AI_FUND_TRADING_ENABLED=false
AI_FUND_TRADING_INTERVAL_SECONDS=30
```

`WORKER_MODE=trading`은 조건매매, 미완료 주문 상태 동기화, AI 위탁만 실행합니다. 뉴스 수집, DART 공시 수집, ML 자동화, 홈 시장 스냅샷, 장 캘린더 스케줄러는 이 worker에서 시작하지 않습니다.

### 로컬 ML 릴리스 운영

실거래 AWS는 학습을 수행하지 않고, 로컬 머신이 생성·검증한 릴리스만 읽습니다. 코인 신규 매수는 릴리스 생성 시각이 90분 이내일 때만, 주식 신규 매수는 36시간 이내일 때만 허용합니다. 예측이 만료되면 신규 매수만 보류하며, 보유 포지션의 손절·익절·비상정지·체결 대사는 계속 동작합니다.

로컬에서 예측 릴리스를 생성합니다.

```bash
python3 scripts/run_local_ml_serving.py --asset crypto
./scripts/deploy_ml_release_aws.sh ml/local_releases/releases/crypto/<release-id>
```

주식은 `--asset kr_stock`, `--asset us_stock`으로 각각 실행합니다. 재학습은 `--train`을 명시했을 때만 수행합니다.

맥이 켜져 있는 동안 자동 실행하려면 다음을 한 번 실행합니다. 생성에 성공한 릴리스만 AWS로 업로드·활성화됩니다.

```bash
./scripts/install_local_ml_launchd.sh
```

AWS `backend/.env`에는 `ML_RELEASE_REQUIRED=true`를 설정하고, 최초 릴리스가 `ml/releases/current/<asset>`에 검증되어 반영된 것을 확인하기 전까지 `AI_FUND_TRADING_ENABLED=false`를 유지합니다.

AI 위탁 실거래는 서버 전역 `COINONE_ACCESS_TOKEN` 값이 아니라 Supabase `user_api_keys`에 저장된 사용자별 암호화 키를 사용합니다. 따라서 worker에는 아래 값이 반드시 있어야 합니다.

```env
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
ENCRYPTION_KEY=...
```

초기 배포와 IP 허용 목록 검증 전에는 `AI_FUND_TRADING_ENABLED=false`로 둡니다. 최신 worker 로그와 코인원 IP 허용 목록을 확인한 후에만 `true`로 바꾸고 worker를 재시작합니다.

주의:

```bash
docker compose config
```

이 명령은 `.env` 값을 터미널에 펼쳐 보여줄 수 있습니다. 화면 공유나 로그 저장 중에는 조심해야 합니다.

## 6. 스크립트 배포 방식

로컬 프로젝트 루트에서 실행합니다.

```bash
cd /Users/kangheesung/10-19_개발/13_프로젝트/13.05_트레이딩/teamproject
./scripts/deploy_backend_aws.sh
```

스크립트는 3단계로 동작합니다.

```text
[1/3] AWS SSH 연결 확인
[2/3] 프로젝트 파일 업로드
[3/3] Docker 이미지 재빌드 및 backend-api 재시작
```

스크립트 기본값:

```bash
AWS_HOST="${AWS_HOST:-ubuntu@52.79.188.213}"
AWS_KEY="${AWS_KEY:-$HOME/Downloads/AE.pem}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/teamproject}"
```

다른 키나 서버를 쓰고 싶으면 실행 시 덮어쓸 수 있습니다.

```bash
AWS_KEY=~/Downloads/other.pem AWS_HOST=ubuntu@1.2.3.4 ./scripts/deploy_backend_aws.sh
```

스크립트는 다음 항목들을 업로드에서 제외합니다.

```text
.git
.env
node_modules
venv/.venv/env
dist
*.pem
캐시 파일
ML raw 데이터
ML 전체 학습 산출물/리포트/노트북
```

챗봇 추천에 필요한 모델은 전체 `ml/` 디렉토리를 올리지 않고, 서빙 패키지로 별도 생성해 업로드합니다. 패키지는 모델 `joblib`, risk 모델 `joblib`, config, metrics, summary, `manifest.json`만 포함하며 raw 학습 데이터는 포함하지 않습니다.

```bash
python3 -m ml.src.export_serving_package \
  --asset-key kr_stock \
  --output-root ml/serving_packages \
  --no-predictions \
  --archive
```

해외주식/코인은 `--asset-key us_stock`, `--asset-key crypto`로 각각 생성합니다. EC2에는 생성된 `.tar.gz`만 업로드합니다.

```text
ml/serving_packages/kr_stock-lgbm_kr_stock_signal_v1.tar.gz
```

사전 생성 예측 CSV를 서버 UI/챗봇 추천 캐시로 같이 쓰는 배포라면 `--no-predictions`를 제거합니다. 세부 절차는 `ml/serving_package_runbook.md`를 기준으로 합니다.

## 7. 재배포 절차

팀원이 머지했거나 로컬에서 코드를 수정한 뒤 다시 배포할 때는 아래 순서로 진행합니다.

1. 로컬에서 최신 코드 준비

```bash
git status
```

필요하면 pull 또는 merge를 먼저 합니다.

```bash
git pull
```

2. 로컬에서 기본 검증

```bash
python3 -m pytest tests/backend/test_knowledge_chunk_service.py tests/backend/test_knowledge_repository.py tests/backend/test_knowledge_routes.py tests/backend/test_rag_retrieval_service.py tests/backend/test_disclosure_knowledge_index_service.py tests/backend/test_disclosure_knowledge_sync_service.py
```

프론트도 함께 수정했다면:

```bash
cd frontend
npm run build
cd ..
```

AI 위탁 자동투자 변경이 포함됐다면 추가로 실행합니다.

```bash
PYTHONPATH=. pytest backend/tests/test_admin_ai_fund_trading_scheduler.py -q
```

3. AWS 보안그룹 SSH 확인

```bash
curl https://checkip.amazonaws.com
```

AWS 보안그룹의 SSH 22번 소스를 현재 IP `/32`로 맞춥니다.

4. AI 위탁 포함 백엔드/worker 배포

```bash
DEPLOY_WORKER=true ./scripts/deploy_backend_aws.sh
```

`DEPLOY_WORKER=true`는 `backend-api`와 `backend-worker`를 같은 이미지로 재빌드해 재시작합니다. 일반 API 수정만 배포할 때는 기존처럼 `./scripts/deploy_backend_aws.sh`를 사용합니다.

5. worker 상태와 최신 코드 확인

```bash
ssh -i ~/Downloads/AE.pem ubuntu@52.79.188.213
cd /home/ubuntu/teamproject
docker compose ps
docker compose logs --tail=100 backend-worker
```

`backend-worker`의 시작 시간이 배포 시각과 일치하는지, 이전 버전의 `DRY_RUN` 또는 코인원 미상장 심볼 오류가 없는지 확인합니다.

6. 상태 확인

서버 안에서:

```bash
curl http://localhost/api/health
docker compose ps
```

Mac에서:

```bash
curl http://52.79.188.213/api/health
```

7. SSH 보안그룹 다시 줄이기

배포 중 임시로 `0.0.0.0/0`을 열었다면 반드시 현재 IP `/32`로 되돌립니다.

## 8. 로그 확인

API 로그:

```bash
cd /home/ubuntu/teamproject
docker compose logs -f backend-api
```

worker 로그:

```bash
cd /home/ubuntu/teamproject
docker compose logs -f backend-worker
```

최근 일부만 보기:

```bash
docker compose logs --tail=100 backend-api
docker compose logs --tail=100 backend-worker
```

로그 화면 종료:

```text
Ctrl + C
```

## 9. 옵시디언/공시 RAG 배포 체크리스트

RAG API 자체는 `backend-api`에 포함됩니다. 따라서 API 컨테이너가 새로 배포되면 라우트 코드는 반영됩니다.

필수 Supabase migration:

```text
20260701093000_create_dart_disclosures.sql
20260703103000_create_dart_disclosure_analyses.sql
20260708110000_create_user_knowledge_memory.sql
20260708113000_create_knowledge_chunks.sql
20260709103000_add_knowledge_chunk_vector_search.sql
```

필수 환경변수:

```env
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
OPENAI_API_KEY=...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

공시 요약 chunk 생성:

```bash
cd /home/ubuntu/teamproject
docker compose exec backend-api python scripts/backfill_disclosure_summary_chunks.py
```

pending chunk 임베딩:

```bash
docker compose exec backend-api python scripts/embed_pending_knowledge_chunks.py
```

옵시디언 노트 동기화:

```text
POST /api/knowledge/obsidian/sync-note
```

동기화 요청은 Supabase 로그인 사용자의 Authorization Bearer 토큰이 필요합니다. 노트 동기화는 `user_knowledge_notes`에 원문을 저장하고, `knowledge_chunks`를 생성한 뒤 해당 노트 chunk를 즉시 임베딩합니다.

RAG 검색:

```text
POST /api/knowledge/retrieve-context
```

이 API는 Supabase `match_knowledge_chunks` vector RPC가 적용되어 있어야 정상 동작합니다.

## 10. 자동매매/worker 주의사항

자동매매와 조건감시는 `backend-worker`가 실행 중이어야 동작합니다.

worker 실행:

```bash
docker compose --profile worker up -d --build backend-worker
```

worker 중지:

```bash
docker compose stop backend-worker
```

상태 확인:

```bash
docker compose ps
```

권장 테스트 순서:

```text
1. PROPOSAL 모드로 조건 도달 시 매도 제안 생성 확인
2. 로그와 Supabase trade_proposals/auto_trading_rules 상태 확인
3. AUTO 모드는 실주문 가능성이 있으므로 소액/모의 환경에서만 신중히 테스트
```

실거래 API 키가 들어간 환경에서는 `AUTO` 실행 모드가 실제 주문으로 이어질 수 있습니다. 처음 테스트는 `PROPOSAL` 모드를 권장합니다.

### AI 위탁 실거래 전환 순서

AI 위탁은 `admin_ai_fund_configs.is_active=true`와 `operation_mode=LIVE` 설정을 worker가 읽어 주문을 시도합니다. worker 컨테이너를 올리는 것만으로는 주문하지 않지만, 이미 활성화된 설정이 있으면 시작 직후 주문 조건을 평가합니다.

```text
1. AI_FUND_TRADING_ENABLED=false 상태로 API와 worker 코드 배포
2. backend-worker 로그에서 최신 코드와 거래소 후보 필터 동작 확인
3. EC2 worker의 외부 송신 IP를 코인원 API 키 허용 목록에 등록
4. backend/.env의 AI_FUND_TRADING_ENABLED=true 적용
5. docker compose --profile worker up -d --force-recreate backend-worker
6. 대시보드에서 운용 금액과 1회 투자 비중을 저장한 뒤 AI 위탁 운용 시작
7. backend-worker 로그와 ai_fund_orders, admin_ai_trade_logs의 실제 체결 상태 확인
```

## 11. 자주 만난 문제와 해결

### SSH timeout

증상:

```text
ssh: connect to host 52.79.188.213 port 22: Operation timed out
```

확인:

```bash
curl https://checkip.amazonaws.com
nc -vz 52.79.188.213 22
```

해결:

```text
AWS 보안그룹 SSH 22번 소스를 현재 IP/32로 수정
필요 시 임시로 0.0.0.0/0 테스트 후 바로 닫기
```

### rsync 옵션 오류

증상:

```text
rsync: unrecognized option `--info=progress2'
```

원인:

```text
macOS 기본 rsync가 구버전이라 --info=progress2를 지원하지 않음
```

현재 스크립트는 `--progress`를 사용하므로 macOS 기본 rsync에서 동작합니다.

### API는 되는데 SSH만 안 됨

확인:

```bash
curl http://52.79.188.213/api/health
```

health check가 성공하면 서버와 HTTP 80은 정상입니다. 이 경우 SSH 22번 보안그룹 또는 현재 네트워크 문제만 보면 됩니다.

### worker가 예전 코드로 돌고 있음

`docker compose ps`에서 worker가 오래 전부터 `Up` 상태이면 기존 컨테이너가 계속 살아있는 것입니다. 새 코드 반영을 위해 worker를 다시 빌드합니다.

```bash
docker compose --profile worker up -d --build backend-worker
```

## 12. 운영 습관

배포 전:

```text
git status 확인
테스트 실행
프론트 수정 시 npm run build
AWS SSH 보안그룹 현재 IP 확인
```

배포 중:

```text
스크립트 [1/3], [2/3], [3/3] 단계 확인
Docker build 실패 로그 읽기
컨테이너 상태 확인
```

배포 후:

```text
/api/health 확인
backend-api 로그 확인
backend-worker 로그 확인
SSH 0.0.0.0/0 닫기
```

서버 재부팅이 필요하다는 메시지가 보일 수 있습니다.

```text
*** System restart required ***
```

당장 배포를 막는 메시지는 아닙니다. 여유 있을 때 재부팅하면 됩니다. 현재 Compose 서비스는 `restart: unless-stopped`라 EC2 재부팅 후 컨테이너가 다시 올라오도록 설정되어 있습니다.
