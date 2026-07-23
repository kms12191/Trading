#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$PROJECT_ROOT/ml/local_logs"

mkdir -p "$PLIST_DIR" "$LOG_DIR"

write_plist() {
  local label="$1"
  local interval="$2"
  local arguments="$3"
  local run_at_load="$4"
  local plist_path="$PLIST_DIR/$label.plist"
  local run_at_load_xml=""
  if [[ "$run_at_load" == "true" ]]; then
    run_at_load_xml='<key>RunAtLoad</key><true/>'
  fi
  cat > "$plist_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$PROJECT_ROOT/scripts/run_and_deploy_local_ml.sh</string>$arguments
  </array>
  <key>StartInterval</key><integer>$interval</integer>
  $run_at_load_xml
  <key>WorkingDirectory</key><string>$PROJECT_ROOT</string>
  <key>EnvironmentVariables</key><dict>
    <key>HOME</key><string>$HOME</string>
    <key>PATH</key><string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key><string>$LOG_DIR/$label.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/$label.error.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist_path"
}

write_plist "com.teamproject.ml.crypto.predict" 1800 "<string>--asset</string><string>crypto</string>" true
write_plist "com.teamproject.ml.crypto.train" 604800 "<string>--asset</string><string>crypto</string><string>--train</string>" false
write_plist "com.teamproject.ml.kr-stock.predict" 86400 "<string>--asset</string><string>kr_stock</string>" false
write_plist "com.teamproject.ml.us-stock.predict" 86400 "<string>--asset</string><string>us_stock</string>" false

echo "launchd 등록 완료: $PLIST_DIR"
