import os
import argparse
import json
import sys
from pathlib import Path
import yaml
import pandas as pd
import numpy as np

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

from lightgbm import LGBMClassifier
import optuna

# 프로젝트 루트를 sys.path에 추가 (model_utils 로드를 위해)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from ml.src.model_utils import (
    build_sample_weights,
    build_time_series_folds,
    calculate_metrics,
    compute_scale_pos_weight
)

# Optuna 로그 레벨을 WARNING으로 설정하여 가독성 증대
optuna.logging.set_verbosity(optuna.logging.WARNING)

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)

def save_config(path: str, config: dict) -> None:
    with open(path, "w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)

def resolve_ml_path(config_path: str, target_path: str) -> Path:
    base_dir = Path(config_path).resolve().parent.parent
    path = Path(target_path)
    return path if path.is_absolute() else base_dir / path


def read_features_csv(path: Path) -> pd.DataFrame:
    """종목코드 문자열 보존을 위해 symbol dtype을 고정합니다."""
    return pd.read_csv(path, dtype={"symbol": "string"}, low_memory=False)

def main() -> None:
    parser = argparse.ArgumentParser(description="Optuna를 사용하여 LightGBM 하이퍼파라미터를 최적화합니다.")
    parser.add_argument("--config", default="configs/lgbm_stock_v1.yaml", help="학습 설정 파일 경로")
    parser.add_argument("--trials", type=int, default=20, help="최적화 실행 횟수 (trial 수)")
    parser.add_argument("--update-config", action="store_true", help="최적 파라미터를 설정 파일에 자동 반영할지 여부")
    args = parser.parse_args()

    config_path = args.config
    config = load_config(config_path)
    
    features_path = resolve_ml_path(config_path, config["data"]["features_path"])
    
    print(f"[Optuna HPO] 피처 로드 중: {features_path}")
    df = read_features_csv(features_path)
    
    feature_columns = config["model"]["feature_columns"]
    target_column = config["model"]["target_column"]
    
    training_options = config.get("training", {})
    class_weight_mode = str(training_options.get("class_weight_mode", "none"))
    balance_symbols = bool(training_options.get("balance_symbol_weights", False))
    cv_splits = int(training_options.get("time_series_cv_splits", 5))
    if cv_splits < 2:
        cv_splits = 5 # 교차 검증 최소 5개
        
    random_state = int(config["model"]["random_state"])

    # 시계열 교차 검증 인덱스 생성
    folds = list(build_time_series_folds(df["date"], cv_splits))
    
    print(f"[Optuna HPO] 총 {len(folds)}개의 시계열 Fold로 교차 검증을 수행합니다. (Trials: {args.trials})")

    def objective(trial):
        # 튜닝할 파라미터 정의
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }
        
        # scale_pos_weight 옵션 적용 여부
        if training_options.get("use_scale_pos_weight"):
            params["scale_pos_weight"] = compute_scale_pos_weight(df[target_column])
            
        fold_scores = []
        
        for fold_idx, (train_dates, valid_dates) in enumerate(folds):
            train_df = df[pd.to_datetime(df["date"]).isin(train_dates)].copy()
            valid_df = df[pd.to_datetime(df["date"]).isin(valid_dates)].copy()
            
            if train_df.empty or valid_df.empty:
                continue
                
            # 샘플 가중치 연산
            sample_weights = build_sample_weights(
                train_df,
                target_column=target_column,
                class_weight_mode=class_weight_mode,
                balance_symbols=balance_symbols
            )
            
            model = LGBMClassifier(
                random_state=random_state,
                n_jobs=-1,
                verbose=-1,
                **params
            )
            
            model.fit(
                train_df[feature_columns],
                train_df[target_column],
                sample_weight=sample_weights
            )
            
            # 검증 셋 예측 및 지표 연산
            prob = model.predict_proba(valid_df[feature_columns])[:, 1]
            metrics = calculate_metrics(valid_df[target_column], pd.Series(prob))
            
            # ROC-AUC를 타겟 지표로 지정
            auc = metrics.get("roc_auc")
            if auc is not None and not np.isnan(auc):
                fold_scores.append(auc)
                
        if not fold_scores:
            return 0.0
        return np.mean(fold_scores)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=args.trials)
    
    print("\n" + "="*50)
    print("[Optuna HPO] 하이퍼파라미터 튜닝이 완수되었습니다!")
    print(f"최적의 시계열 CV ROC-AUC: {study.best_value:.6f}")
    print("최적의 파라미터:")
    print(json.dumps(study.best_params, indent=2))
    print("="*50 + "\n")

    if args.update_config:
        # 최적 파라미터를 YAML에 갱신
        config["lightgbm"] = study.best_params
        # num_leaves나 max_depth 등을 int 형변환 확실히
        for k, v in config["lightgbm"].items():
            if isinstance(v, (np.integer, int)):
                config["lightgbm"][k] = int(v)
            elif isinstance(v, (np.floating, float)):
                config["lightgbm"][k] = float(v)
                
        save_config(config_path, config)
        print(f"[Optuna HPO] {config_path} 설정 파일의 'lightgbm' 영역이 갱신되었습니다.")

if __name__ == "__main__":
    main()
