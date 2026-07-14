#!/usr/bin/env bash
set -euo pipefail

AWS_HOST="${AWS_HOST:-ubuntu@52.79.188.213}"
AWS_KEY="${AWS_KEY:-$HOME/Downloads/AE.pem}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/teamproject}"
SSH_OPTS=(-i "$AWS_KEY" -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2)

if [[ ! -f "$AWS_KEY" ]]; then
  echo "AWS 키 파일을 찾을 수 없습니다: $AWS_KEY" >&2
  exit 1
fi

echo "[1/3] AWS SSH 연결 확인: ${AWS_HOST}"
ssh "${SSH_OPTS[@]}" "$AWS_HOST" "echo 'SSH 연결 성공'; mkdir -p '${REMOTE_DIR}'"

echo "[2/3] 프로젝트 파일 업로드: ${REMOTE_DIR}"
rsync -av --progress -e "ssh ${SSH_OPTS[*]}" \
  --exclude '.git' \
  --exclude '.env' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude 'env' \
  --exclude 'node_modules' \
  --exclude '.pytest_cache' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'dist' \
  --exclude '*.pem' \
  --exclude '.DS_Store' \
  --exclude '.agents' \
  --exclude '.codex' \
  --exclude '.kis_token_cache.json' \
  --exclude '.toss_token_cache.json' \
  --exclude '.*_cache.json' \
  --exclude 'frontend-dashboard-qa.png' \
  --exclude 'frontend/admin-inquiries-preview.png' \
  --exclude 'mobile(Copy)' \
  --exclude 'CORPCODE.xml' \
  --exclude 'ml/data/raw' \
  --include 'ml/data/processed/' \
  --include 'ml/data/processed/*_predictions_lgbm_v*.csv' \
  --include 'ml/data/processed/*_v*_summary.json' \
  --include 'ml/data/processed/*_backtest_*.json' \
  --exclude 'ml/data/processed/**' \
  --include 'ml/data/ops/' \
  --include 'ml/data/ops/model_registry.json' \
  --exclude 'ml/data/ops/**' \
  --include 'ml/models/' \
  --include 'ml/models/*.metrics.json' \
  --exclude 'ml/models/**' \
  --include 'ml/serving_packages/' \
  --include 'ml/serving_packages/*.tar.gz' \
  --exclude 'ml/serving_packages/**' \
  --exclude 'ml/reports' \
  --exclude 'ml/notebooks' \
  --exclude 'supabase/.temp' \
  ./ "${AWS_HOST}:${REMOTE_DIR}/"

echo "[3/3] Docker 이미지 재빌드 및 backend-api 재시작"
ssh "${SSH_OPTS[@]}" "$AWS_HOST" \
  "cd ${REMOTE_DIR} && docker compose up -d --build backend-api && docker compose ps"
