#!/usr/bin/env bash
set -euo pipefail

AWS_HOST="${AWS_HOST:-ubuntu@52.79.188.213}"
AWS_KEY="${AWS_KEY:-$HOME/.ssh/AE.pem}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/teamproject}"
LOCAL_RELEASE="${1:?로컬 릴리스 디렉터리를 전달하세요}"

if [[ ! -f "$LOCAL_RELEASE/manifest.json" ]]; then
  echo "manifest.json을 찾지 못했습니다: $LOCAL_RELEASE" >&2
  exit 1
fi
if [[ ! -f "$AWS_KEY" ]]; then
  echo "AWS 키 파일을 찾지 못했습니다: $AWS_KEY" >&2
  exit 1
fi

ASSET_KEY="$(python3 - "$LOCAL_RELEASE/manifest.json" <<'PY'
import json
import sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
print(manifest["asset_key"])
PY
)"
RELEASE_ID="$(basename "$(cd "$LOCAL_RELEASE" && pwd)")"
SSH_OPTS=(-i "$AWS_KEY" -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2)

ssh "${SSH_OPTS[@]}" "$AWS_HOST" "mkdir -p '$REMOTE_DIR/ml/releases/releases/$ASSET_KEY/$RELEASE_ID'"
rsync -a --delete -e "ssh ${SSH_OPTS[*]}" "$LOCAL_RELEASE/" "$AWS_HOST:$REMOTE_DIR/ml/releases/releases/$ASSET_KEY/$RELEASE_ID/"
ssh "${SSH_OPTS[@]}" "$AWS_HOST" \
  "cd '$REMOTE_DIR' && python3 scripts/activate_ml_release.py --releases-root ml/releases --asset '$ASSET_KEY' --release-id '$RELEASE_ID'"
