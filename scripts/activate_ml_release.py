#!/usr/bin/env python3
"""AWS에서 검증된 ML 릴리스를 현재 서빙 릴리스로 전환한다."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.ml_release_service import activate_release


def main() -> int:
    parser = argparse.ArgumentParser(description="ML 현재 릴리스 원자적 전환")
    parser.add_argument("--releases-root", type=Path, required=True)
    parser.add_argument("--asset", required=True, choices=["crypto", "kr_stock", "us_stock"])
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args()
    print(activate_release(args.releases_root, args.asset, args.release_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
