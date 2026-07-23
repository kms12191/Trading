#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/ml/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi
ASSET=""
TRAIN_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --asset)
      ASSET="${2:?--asset 값이 필요합니다}"
      shift 2
      ;;
    --train)
      TRAIN_ARGS+=("--train")
      shift
      ;;
    *)
      echo "지원하지 않는 인자: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$ASSET" ]]; then
  echo "--asset 값이 필요합니다" >&2
  exit 1
fi

LOCK_ROOT="$PROJECT_ROOT/ml/local_runtime"
LOCK_DIR="$LOCK_ROOT/${ASSET}.lock"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "이미 실행 중인 로컬 ML 작업이 있어 건너뜁니다: $ASSET"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

RUN_COMMAND=("$PYTHON_BIN" scripts/run_local_ml_serving.py --asset "$ASSET")
if [[ ${#TRAIN_ARGS[@]} -gt 0 ]]; then
  RUN_COMMAND+=("${TRAIN_ARGS[@]}")
fi
RELEASE_DIR="$(cd "$PROJECT_ROOT" && "${RUN_COMMAND[@]}" | tail -n 1)"
if [[ ! -f "$RELEASE_DIR/manifest.json" ]]; then
  echo "생성 릴리스를 확인하지 못했습니다: $RELEASE_DIR" >&2
  exit 1
fi
cd "$PROJECT_ROOT"
./scripts/deploy_ml_release_aws.sh "$RELEASE_DIR"
