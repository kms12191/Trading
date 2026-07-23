# Local ML Serving Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로컬 머신이 생성한 검증된 ML 릴리스를 AWS 거래 워커에 원자적으로 반영하고, 예측 만료 시 신규 매수만 차단한다.

**Architecture:** 로컬 `ml_local_runner.py`는 코인·주식 예측과 주기적 재학습을 실행한 뒤 릴리스 매니페스트를 만든다. `deploy_ml_release_aws.sh`가 릴리스를 AWS 임시 디렉터리에 업로드하고 검증 스크립트가 해시를 검사한 뒤 `current/<asset_key>` 심볼릭 링크를 교체한다. AWS 거래 서비스는 현재 자산 릴리스의 매니페스트를 읽어 신선도를 판정하며, 신규 진입만 차단한다.

**Tech Stack:** Python 3.11, pytest, SSH/rsync, Docker Compose, CSV, JSON manifest.

## Global Constraints

- AWS 거래 워커는 모델 학습이나 예측 생성을 수행하지 않는다.
- 코인 매수 예측은 생성 시각 기준 90분 이내여야 한다.
- 국내·미국 주식 매수 예측은 해당 시장의 가장 최근 거래일 장마감 후 생성되어야 한다.
- 예측 만료는 신규 매수만 막고 익절·손절·비상정지·주문 대사는 계속 허용한다.
- 배포 전과 AWS 반영 전 모두 SHA-256 해시 검증에 실패하면 기존 릴리스를 유지한다.

---

### Task 1: ML 릴리스 매니페스트와 AWS 현재 릴리스 리더

**Files:**
- Create: `backend/services/ml_release_service.py`
- Test: `backend/tests/test_ml_release_service.py`

**Interfaces:**
- Produces: `MlReleaseService(releases_root: Path)`
- Produces: `MlReleaseService.load_current_manifest() -> dict | None`
- Produces: `MlReleaseService.is_asset_fresh(asset_key: str, now: datetime) -> tuple[bool, str]`

- [ ] **Step 1: Write failing tests for a valid crypto release and hash mismatch**

```python
def test_crypto_release_is_fresh_within_ninety_minutes(tmp_path):
    service = MlReleaseService(tmp_path)
    _write_current_release(tmp_path, asset_key="crypto", created_at="2026-07-23T00:00:00+00:00")
    assert service.is_asset_fresh("crypto", datetime(2026, 7, 23, 1, 29, tzinfo=timezone.utc)) == (True, "READY")

def test_release_with_invalid_file_hash_is_rejected(tmp_path):
    service = MlReleaseService(tmp_path)
    _write_current_release(tmp_path, asset_key="crypto", created_at="2026-07-23T00:00:00+00:00", invalid_hash=True)
    assert service.load_current_manifest() is None
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `PYTHONPATH=. pytest backend/tests/test_ml_release_service.py -q`

Expected: FAIL because `ml_release_service` does not exist.

- [ ] **Step 3: Implement manifest parsing, required-file hash validation, and freshness policy**

```python
class MlReleaseService:
    def load_current_manifest(self) -> dict | None:
    manifest_path = self.releases_root / "current" / asset_key / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest if self._validate_files(manifest) else None

    def is_asset_fresh(self, asset_key: str, now: datetime) -> tuple[bool, str]:
        manifest = self.load_current_manifest()
        if not manifest or manifest.get("asset_key") != asset_key:
            return False, "RELEASE_UNAVAILABLE"
        created_at = _parse_utc(manifest["created_at"])
        if asset_key == "crypto" and now - created_at <= timedelta(minutes=90):
            return True, "READY"
        return False, "STALE_RELEASE"
```

- [ ] **Step 4: Run tests to verify pass**

Run: `PYTHONPATH=. pytest backend/tests/test_ml_release_service.py -q`

Expected: PASS.

### Task 2: 매수 후보가 현재 AWS 릴리스만 읽도록 변경

**Files:**
- Modify: `backend/services/ai_fund_crypto_selection.py`
- Modify: `backend/services/ai_fund_stock_selection.py`
- Modify: `backend/routes/admin_ai_fund.py`
- Test: `backend/tests/test_ai_fund_crypto_selection.py`
- Test: `backend/tests/test_ai_fund_stock_selection.py`

**Interfaces:**
- Consumes: `MlReleaseService.is_asset_fresh()`
- Produces: 후보 조회 availability의 `RELEASE_UNAVAILABLE` 또는 `STALE_RELEASE` 상태

- [ ] **Step 1: Write failing tests proving a stale release blocks candidates while exit flow remains independent**

```python
def test_crypto_candidates_are_withheld_when_current_release_is_stale(tmp_path, monkeypatch):
    predictions = _write_fresh_crypto_predictions(tmp_path)
    monkeypatch.setattr("backend.services.ai_fund_crypto_selection.MlReleaseService.is_asset_fresh", lambda *_: (False, "STALE_RELEASE"))
    snapshot = AiFundCryptoSelectionService(predictions).get_snapshot(0.3)
    assert snapshot["candidates"] == []
    assert snapshot["availability"]["status"] == "STALE_RELEASE"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `PYTHONPATH=. pytest backend/tests/test_ai_fund_crypto_selection.py backend/tests/test_ai_fund_stock_selection.py -q`

Expected: FAIL because selection services do not consult the release state.

- [ ] **Step 3: Inject current-release validation before LONG candidate filtering**

```python
fresh, status = self.release_service.is_asset_fresh("crypto", datetime.now(timezone.utc))
if not fresh:
    return self._empty_snapshot(rows, status)
```

Keep `AdminAiManagedTrader.evaluate_exit_signal()` and the scheduler's held-position loop unchanged so that protective sells do not require a fresh release.

- [ ] **Step 4: Run focused selection tests**

Run: `PYTHONPATH=. pytest backend/tests/test_ai_fund_crypto_selection.py backend/tests/test_ai_fund_stock_selection.py -q`

Expected: PASS.

### Task 3: 로컬 ML 러너와 원자적 AWS 릴리스 배포 도구

**Files:**
- Create: `scripts/run_local_ml_serving.py`
- Create: `scripts/deploy_ml_release_aws.sh`
- Create: `scripts/activate_ml_release.py`
- Modify: `.env.example`
- Modify: `docs/AWS_DEPLOYMENT_GUIDE.md`
- Test: `backend/tests/test_ml_release_service.py`

**Interfaces:**
- Produces: `python scripts/run_local_ml_serving.py --asset crypto --predict-only`
- Produces: `./scripts/deploy_ml_release_aws.sh ml/releases/<release-id>`
- Produces: `python scripts/activate_ml_release.py --releases-root <path> --release-id <id>`

- [ ] **Step 1: Write failing tests for release assembly and atomic activation**

```python
def test_activate_release_replaces_current_only_after_manifest_validation(tmp_path):
    release = _write_release(tmp_path, "crypto-v10-20260723T000000Z")
    activate_release(tmp_path, release.name)
    assert (tmp_path / "current" / "crypto").resolve() == release.resolve()

def test_activate_release_keeps_existing_current_when_release_is_invalid(tmp_path):
    current = _write_release(tmp_path, "previous")
    activate_release(tmp_path, current.name)
    invalid = _write_release(tmp_path, "invalid", invalid_hash=True)
    with pytest.raises(ValueError):
        activate_release(tmp_path, invalid.name)
    assert (tmp_path / "current" / "crypto").resolve() == current.resolve()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=. pytest backend/tests/test_ml_release_service.py -q`

Expected: FAIL because `activate_release` does not exist.

- [ ] **Step 3: Implement local predict-first runner and deployment scripts**

```python
# run_local_ml_serving.py
run_predict(config_path)
release_dir = build_release(asset_key, predictions_path, model_paths, config_path)
validate_release(release_dir)

# deploy_ml_release_aws.sh
rsync -a --delete "$LOCAL_RELEASE/" "$AWS_HOST:$REMOTE_DIR/ml/releases/$RELEASE_ID/"
ssh "$AWS_HOST" "cd $REMOTE_DIR && python scripts/activate_ml_release.py --releases-root ml/releases --release-id $RELEASE_ID"
```

The runner accepts `--train` separately. Its default mode never retrains, preventing accidental recurring full training on a laptop.

- [ ] **Step 4: Run unit tests and shell syntax validation**

Run: `PYTHONPATH=. pytest backend/tests/test_ml_release_service.py -q && bash -n scripts/deploy_ml_release_aws.sh`

Expected: PASS with no shell syntax errors.

### Task 4: 실행 스케줄, 운영 문서, 전체 검증

**Files:**
- Create: `scripts/install_local_ml_launchd.sh`
- Modify: `docs/AWS_DEPLOYMENT_GUIDE.md`
- Modify: `.env.example`
- Test: `backend/tests/test_worker_modes.py`
- Test: `backend/tests/test_admin_ai_fund_routes.py`

**Interfaces:**
- Produces: macOS launchd jobs for `crypto --predict-only` every 30 minutes and `--train` weekly.
- Produces: AWS release root environment variable `ML_RELEASES_ROOT=/app/ml/releases`.

- [ ] **Step 1: Write a failing worker-mode test for stale-prediction buy blocking without disabling exits**

```python
def test_trading_mode_keeps_ai_fund_worker_enabled_without_ml_training(monkeypatch):
    assert is_trading_worker_mode("trading") is True
    assert "start_ml_automation_scheduler" not in _started_services_for("trading")
    assert "start_ai_fund_trading_scheduler" in _started_services_for("trading")
```

- [ ] **Step 2: Run the test to verify failure or update it when existing coverage proves the behavior**

Run: `PYTHONPATH=. pytest backend/tests/test_worker_modes.py -q`

Expected: PASS only after the test covers the explicit invariant.

- [ ] **Step 3: Add launchd installer and operation guide**

```bash
python scripts/run_local_ml_serving.py --asset crypto --predict-only
python scripts/run_local_ml_serving.py --asset crypto --train
./scripts/deploy_ml_release_aws.sh ml/releases/crypto-<timestamp>
```

Document stop/start commands, failure log locations, release rollback using the prior release ID, and the rule that `AI_FUND_TRADING_ENABLED` remains false until a fresh release is visible in the dashboard.

- [ ] **Step 4: Run full verification**

Run: `PYTHONPATH=. pytest backend/tests/test_ml_release_service.py backend/tests/test_ai_fund_crypto_selection.py backend/tests/test_ai_fund_stock_selection.py backend/tests/test_worker_modes.py backend/tests/test_admin_ai_fund_routes.py -q && bash -n scripts/deploy_ml_release_aws.sh && npm run build --prefix frontend && git diff --check`

Expected: all tests pass, frontend build passes, and no whitespace errors are reported.
