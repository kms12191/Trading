import argparse
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SENTIMENT_SCORE = {
    "positive": 1.0,
    "negative": -1.0,
    "caution": -0.5,
    "info": 0.0,
    "neutral": 0.0,
}

CONFIDENCE_SCORE = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.3,
}

DART_TEXT_RISK_KEYWORDS = [
    "거래정지",
    "상장폐지",
    "관리종목",
    "불성실",
    "감사의견",
    "횡령",
    "배임",
    "회생",
    "영업정지",
    "감자",
    "소송",
    "제재",
    "위험",
    "리스크",
    "손실",
    "악재",
]

CATEGORY_GROUPS = {
    "dart_contract_flag": ["수주", "공급계약", "계약"],
    "dart_financing_flag": ["유상증자", "자금조달", "증권", "사채", "전환"],
    "dart_shareholder_return_flag": ["배당", "자사주", "주주환원", "소각"],
    "dart_risk_event_flag": ["거래정지", "상장폐지", "관리종목", "불성실", "감사의견", "횡령", "배임", "회생", "영업정지", "감자"],
    "dart_earnings_flag": ["영업실적", "손익구조", "매출액", "영업이익"],
}

BASE_DART_COLUMNS = [
    "dart_disclosure_count",
    "dart_sentiment_score",
    "dart_positive_count",
    "dart_negative_count",
    "dart_caution_count",
    "dart_info_count",
    "dart_ai_analyzed_count",
    "dart_summary_available_count",
    "dart_summary_length",
    "dart_key_point_count",
    "dart_risk_point_count",
    "dart_check_item_count",
    "dart_metric_count",
    "dart_confidence_score",
    "dart_text_risk_keyword_count",
    *CATEGORY_GROUPS.keys(),
]

OUTPUT_DART_COLUMNS = [
    "dart_disclosure_count_3d",
    "dart_sentiment_sum_3d",
    "dart_negative_count_3d",
    "dart_positive_count_3d",
    "dart_caution_count_3d",
    "dart_summary_available_count_3d",
    "dart_summary_length_sum_3d",
    "dart_key_point_count_3d",
    "dart_risk_point_count_3d",
    "dart_check_item_count_3d",
    "dart_metric_count_3d",
    "dart_confidence_score_sum_3d",
    "dart_text_risk_keyword_count_3d",
    "dart_disclosure_count_7d",
    "dart_sentiment_sum_7d",
    "dart_negative_count_7d",
    "dart_positive_count_7d",
    "dart_caution_count_7d",
    "dart_summary_available_count_7d",
    "dart_summary_length_sum_7d",
    "dart_key_point_count_7d",
    "dart_risk_point_count_7d",
    "dart_check_item_count_7d",
    "dart_metric_count_7d",
    "dart_confidence_score_sum_7d",
    "dart_text_risk_keyword_count_7d",
    "dart_disclosure_count_20d",
    "dart_sentiment_sum_20d",
    "dart_negative_count_20d",
    "dart_positive_count_20d",
    "dart_caution_count_20d",
    "dart_summary_available_count_20d",
    "dart_summary_length_sum_20d",
    "dart_key_point_count_20d",
    "dart_risk_point_count_20d",
    "dart_check_item_count_20d",
    "dart_metric_count_20d",
    "dart_confidence_score_sum_20d",
    "dart_text_risk_keyword_count_20d",
    "dart_ai_analyzed_count_20d",
    "dart_contract_flag_20d",
    "dart_financing_flag_20d",
    "dart_shareholder_return_flag_20d",
    "dart_risk_event_flag_20d",
    "dart_earnings_flag_20d",
]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def normalize_stock_code(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    return text.upper()


def normalize_disclosure_date(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def build_analysis_map(analyses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in analyses:
        rcept_no = str(row.get("rcept_no") or "").strip()
        if rcept_no:
            result[rcept_no] = row
    return result


def has_category_keyword(*values: object, keywords: list[str]) -> float:
    text = " ".join(str(value or "") for value in values)
    return 1.0 if any(keyword in text for keyword in keywords) else 0.0


def count_items(value: object) -> float:
    if isinstance(value, list):
        return float(len(value))
    if isinstance(value, dict):
        return float(len(value))
    return 0.0


def text_length(value: object) -> float:
    text = str(value or "").strip()
    return float(len(text))


def count_risk_keywords(*values: object) -> float:
    text = " ".join(str(value or "") for value in values)
    return float(sum(text.count(keyword) for keyword in DART_TEXT_RISK_KEYWORDS))


def build_daily_dart_features(disclosures: list[dict[str, Any]], analyses: list[dict[str, Any]]) -> pd.DataFrame:
    analysis_by_rcept_no = build_analysis_map(analyses)
    rows: list[dict[str, Any]] = []

    for disclosure in disclosures:
        symbol = normalize_stock_code(disclosure.get("stock_code"))
        date = normalize_disclosure_date(disclosure.get("rcept_dt"))
        rcept_no = str(disclosure.get("rcept_no") or "").strip()
        if not symbol or not date or not rcept_no:
            continue

        analysis = analysis_by_rcept_no.get(rcept_no)
        sentiment = str((analysis or {}).get("sentiment") or "info").strip().lower()
        category = str((analysis or {}).get("category") or "")
        confidence = str((analysis or {}).get("confidence") or "").strip().lower()
        plain_summary = (analysis or {}).get("plain_summary")
        headline = (analysis or {}).get("headline")
        sentiment_message = (analysis or {}).get("sentiment_message")
        report_name = str(disclosure.get("report_nm") or "")

        row = {
            "symbol": symbol,
            "date": date,
            "dart_disclosure_count": 1.0,
            "dart_sentiment_score": SENTIMENT_SCORE.get(sentiment, 0.0),
            "dart_positive_count": 1.0 if sentiment == "positive" else 0.0,
            "dart_negative_count": 1.0 if sentiment == "negative" else 0.0,
            "dart_caution_count": 1.0 if sentiment == "caution" else 0.0,
            "dart_info_count": 1.0 if sentiment == "info" else 0.0,
            "dart_ai_analyzed_count": 1.0 if analysis else 0.0,
            "dart_summary_available_count": 1.0 if text_length(plain_summary) > 0 else 0.0,
            "dart_summary_length": text_length(plain_summary),
            "dart_key_point_count": count_items((analysis or {}).get("key_points")),
            "dart_risk_point_count": count_items((analysis or {}).get("risk_points")),
            "dart_check_item_count": count_items((analysis or {}).get("check_items")),
            "dart_metric_count": count_items((analysis or {}).get("metrics")),
            "dart_confidence_score": CONFIDENCE_SCORE.get(confidence, 0.0),
            "dart_text_risk_keyword_count": count_risk_keywords(headline, sentiment_message, plain_summary, category, report_name),
        }
        for column, keywords in CATEGORY_GROUPS.items():
            row[column] = has_category_keyword(category, report_name, keywords=keywords)
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=["symbol", "date", *BASE_DART_COLUMNS])

    return (
        pd.DataFrame(rows)
        .groupby(["symbol", "date"], as_index=False)[BASE_DART_COLUMNS]
        .sum()
        .sort_values(["symbol", "date"])
        .reset_index(drop=True)
    )


def build_shifted_dart_features(feature_dates: pd.DataFrame, daily_features: pd.DataFrame) -> pd.DataFrame:
    if feature_dates.empty:
        return pd.DataFrame(columns=["symbol", "date", *OUTPUT_DART_COLUMNS])

    base = feature_dates[["symbol", "date"]].copy()
    base["symbol"] = base["symbol"].map(normalize_stock_code)
    base["date_key"] = base["date"].map(normalize_disclosure_date)
    base = base[base["date_key"] != ""].drop_duplicates(subset=["symbol", "date_key"])
    base["date"] = pd.to_datetime(base["date_key"], errors="coerce")

    daily = daily_features.copy()
    if daily.empty:
        daily = pd.DataFrame(columns=["symbol", "date", *BASE_DART_COLUMNS])
    for column in BASE_DART_COLUMNS:
        if column not in daily.columns:
            daily[column] = 0.0
    daily["symbol"] = daily["symbol"].map(normalize_stock_code)
    daily["date_key"] = pd.to_datetime(daily["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    timeline = (
        pd.concat(
            [
                base[["symbol", "date", "date_key"]],
                daily.assign(date=pd.to_datetime(daily["date_key"], errors="coerce"))[["symbol", "date", "date_key"]],
            ],
            ignore_index=True,
        )
        .dropna(subset=["date"])
        .drop_duplicates(subset=["symbol", "date_key"])
        .sort_values(["symbol", "date"])
        .reset_index(drop=True)
    )
    merged = timeline.merge(daily[["symbol", "date_key", *BASE_DART_COLUMNS]], on=["symbol", "date_key"], how="left")
    merged[BASE_DART_COLUMNS] = merged[BASE_DART_COLUMNS].fillna(0.0)

    frames: list[pd.DataFrame] = []
    for _, group in merged.groupby("symbol", sort=False):
        group = group.sort_values("date").copy()
        shifted = group[BASE_DART_COLUMNS].shift(1).fillna(0.0)
        output = group[["symbol", "date"]].copy()
        for window in [3, 7, 20]:
            rolling = shifted.rolling(window, min_periods=1).sum()
            output[f"dart_disclosure_count_{window}d"] = rolling["dart_disclosure_count"]
            output[f"dart_sentiment_sum_{window}d"] = rolling["dart_sentiment_score"]
            output[f"dart_negative_count_{window}d"] = rolling["dart_negative_count"]
            output[f"dart_positive_count_{window}d"] = rolling["dart_positive_count"]
            output[f"dart_caution_count_{window}d"] = rolling["dart_caution_count"]
            output[f"dart_summary_available_count_{window}d"] = rolling["dart_summary_available_count"]
            output[f"dart_summary_length_sum_{window}d"] = rolling["dart_summary_length"]
            output[f"dart_key_point_count_{window}d"] = rolling["dart_key_point_count"]
            output[f"dart_risk_point_count_{window}d"] = rolling["dart_risk_point_count"]
            output[f"dart_check_item_count_{window}d"] = rolling["dart_check_item_count"]
            output[f"dart_metric_count_{window}d"] = rolling["dart_metric_count"]
            output[f"dart_confidence_score_sum_{window}d"] = rolling["dart_confidence_score"]
            output[f"dart_text_risk_keyword_count_{window}d"] = rolling["dart_text_risk_keyword_count"]
        output["dart_ai_analyzed_count_20d"] = shifted["dart_ai_analyzed_count"].rolling(20, min_periods=1).sum()
        for column in CATEGORY_GROUPS:
            output[f"{column}_20d"] = shifted[column].rolling(20, min_periods=1).max()
        frames.append(output)

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["symbol", "date", *OUTPUT_DART_COLUMNS])
    for column in OUTPUT_DART_COLUMNS:
        if column not in result.columns:
            result[column] = 0.0
    result["date_key"] = pd.to_datetime(result["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result = result.merge(base[["symbol", "date_key"]], on=["symbol", "date_key"], how="inner")
    result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
    return result[["symbol", "date", *OUTPUT_DART_COLUMNS]]


def fetch_supabase_rows(table: str, select: str, params: dict[str, str], batch_size: int = 1000) -> list[dict[str, Any]]:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        raise RuntimeError("SUPABASE_URL과 SUPABASE_SERVICE_ROLE_KEY가 필요합니다.")

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        request_params = {"select": select, "limit": str(batch_size), "offset": str(offset), **params}
        response = requests.get(
            f"{supabase_url}/rest/v1/{table}",
            headers=headers,
            params=request_params,
            timeout=30,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size
    return rows


def main() -> None:
    load_env_file(PROJECT_ROOT / "backend" / ".env")
    parser = argparse.ArgumentParser(description="DART 공시 분석 결과를 ML raw 피처 CSV로 변환합니다.")
    parser.add_argument("--dates-source-path", default="ml/data/raw/kr_stock_candles.csv")
    parser.add_argument("--output", default="ml/data/raw/dart_features.csv")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    args = parser.parse_args()

    dates_source_path = (PROJECT_ROOT / args.dates_source_path).resolve()
    dates_source_frame = pd.read_csv(dates_source_path, dtype={"symbol": "string"}, low_memory=False)
    feature_dates = dates_source_frame[["symbol", "date"]].drop_duplicates()
    start_date = args.start_date or pd.to_datetime(feature_dates["date"]).min().strftime("%Y-%m-%d")
    end_date = args.end_date or pd.to_datetime(feature_dates["date"]).max().strftime("%Y-%m-%d")

    disclosures = fetch_supabase_rows(
        "dart_disclosures",
        "rcept_no,stock_code,report_nm,rcept_dt",
        {"rcept_dt": f"gte.{start_date}", "order": "rcept_dt.asc,rcept_no.asc"},
    )
    disclosures = [
        row
        for row in disclosures
        if normalize_disclosure_date(row.get("rcept_dt")) and normalize_disclosure_date(row.get("rcept_dt")) <= end_date
    ]
    analyses = fetch_supabase_rows(
        "dart_disclosure_analyses",
        "rcept_no,category,sentiment,confidence,headline,plain_summary,sentiment_message,key_points,risk_points,check_items,metrics",
        {},
    )

    daily = build_daily_dart_features(disclosures, analyses)
    shifted = build_shifted_dart_features(feature_dates, daily)
    output_path = (PROJECT_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shifted.to_csv(output_path, index=False)
    print(f"DART 피처 파일 생성 완료: {output_path} ({len(shifted):,} rows)")


if __name__ == "__main__":
    main()
