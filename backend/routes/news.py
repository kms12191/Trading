import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from backend.services.symbol_metadata import SYMBOL_METADATA
from backend.services.error_message_service import format_error_payload

news_bp = Blueprint("news", __name__)

@news_bp.route("/api/news", methods=["GET"])
def get_news_feed():
    """뉴스 데이터베이스로부터 수집된 최근 뉴스 피드 목록을 필터링 및 검색하여 반환합니다."""
    market = request.args.get("market", "ALL")
    query = request.args.get("query", "")
    symbol = request.args.get("symbol", "")
    limit = request.args.get("limit", 10)
    offset = request.args.get("offset", 0)
    
    if symbol:
        meta = SYMBOL_METADATA.get(symbol.upper(), {})
        display_name = meta.get("display_name", "")
        if display_name:
            query = display_name
        else:
            query = symbol
    
    news_repository = current_app.news_repository
    news_summary_service = current_app.news_summary_service
    try:
        items = news_repository.list_articles(
            market=market,
            query=query,
            limit=int(limit),
            offset=int(offset),
        )

        # 조회된 기사들 중 가장 최신 기사 딱 1개에 대해서만 우선적으로 실시간 자동 요약 갱신 실행
        updates = []
        if items:
            item = items[0]
            existing_summary = (item.get("ai_summary") or "").strip()
            existing_model = item.get("ai_summary_model")
            
            if not existing_summary or (existing_model == "fallback" and news_summary_service.enabled):
                try:
                    summary_payload = news_summary_service.summarize(item)
                    item["ai_summary"] = summary_payload["ai_summary"]
                    item["ai_summary_model"] = summary_payload["ai_summary_model"]
                    item["ai_summary_generated_at"] = datetime.utcnow().isoformat() + "Z"
                    item["ai_summary_prompt_version"] = summary_payload["ai_summary_prompt_version"]
                    
                    updates.append({
                        "id": item["id"],
                        "ai_summary": item["ai_summary"],
                        "ai_summary_model": item["ai_summary_model"],
                        "ai_summary_generated_at": item["ai_summary_generated_at"],
                        "ai_summary_prompt_version": item["ai_summary_prompt_version"]
                    })
                except Exception as sum_err:
                    current_app.logger.warning(f"Failed to auto-summarize article {item.get('id')}: {str(sum_err)}")

        if updates:
            try:
                news_repository.upsert_article_summaries(updates)
            except Exception as db_err:
                current_app.logger.error(f"Failed to save auto-generated summaries: {str(db_err)}")

        total_count = news_repository.count_articles(
            market=market,
            query=query,
        )

        return jsonify({
            "success": True,
            "data": {
                "items": items,
                "totalCount": total_count,
                "limit": int(limit),
                "offset": int(offset),
                "market": market.upper(),
                "query": query,
            }
        })
    except requests.exceptions.HTTPError as e:
        return jsonify(format_error_payload(e, "뉴스 제공자 호출 실패")), 502
    except Exception as e:
        return jsonify(format_error_payload(e, "뉴스 피드 조회 실패")), 500

@news_bp.route("/api/news/sync", methods=["POST"])
def sync_news_feed():
    """Tavily API 등을 통해 웹 상에서 최신 뉴스를 실시간으로 데이터베이스에 동기화 수집합니다."""
    news_ingest_service = current_app.news_ingest_service
    try:
        data = request.get_json(silent=True) or {}
        symbol = str(data.get("symbol") or "").strip().upper()

        if symbol:
            result = news_ingest_service.run_for_symbol(
                symbol=symbol,
                display_name=str(data.get("display_name") or "").strip(),
                market=str(data.get("market") or "").strip(),
                asset_type=str(data.get("asset_type") or "").strip(),
            )
        else:
            result = news_ingest_service.run_once()
        return jsonify({
            "success": True,
            "data": result,
        })
    except Exception as e:
        return jsonify(format_error_payload(e, "뉴스 수집 실패")), 500

@news_bp.route("/api/news/summaries/ensure", methods=["POST"])
def ensure_news_summaries():
    """지정 뉴스 목록에 대해 LLM 기반 AI 요약 정보가 적재되어 있는지 확인하고, 누락된 요약을 생성합니다."""
    news_repository = current_app.news_repository
    news_summary_service = current_app.news_summary_service
    try:
        data = request.json or {}
        article_ids = data.get("article_ids") or []
        article_ids = [str(article_id).strip() for article_id in article_ids if str(article_id).strip()]

        if not article_ids:
            return jsonify({
                "success": True,
                "data": {
                    "items": [],
                    "generatedCount": 0,
                }
            })

        articles = news_repository.list_articles_by_ids(article_ids)
        article_by_id = {article["id"]: article for article in articles if article.get("id")}
        updates = []
        items = []

        for article_id in article_ids:
            article = article_by_id.get(article_id)
            if not article:
                continue

            existing_summary = (article.get("ai_summary") or "").strip()
            existing_model = article.get("ai_summary_model")
            if existing_summary and (existing_model != "fallback" or not news_summary_service.enabled):
                items.append({
                    "id": article_id,
                    "ai_summary": existing_summary,
                    "ai_summary_model": article.get("ai_summary_model"),
                    "ai_summary_generated_at": article.get("ai_summary_generated_at"),
                    "ai_summary_prompt_version": article.get("ai_summary_prompt_version"),
                })
                continue

            summary_payload = news_summary_service.summarize(article)
            update_row = {
                "id": article_id,
                "ai_summary": summary_payload["ai_summary"],
                "ai_summary_model": summary_payload["ai_summary_model"],
                "ai_summary_generated_at": datetime.utcnow().isoformat() + "Z",
                "ai_summary_prompt_version": summary_payload["ai_summary_prompt_version"],
            }
            updates.append(update_row)
            items.append(update_row)

        if updates:
            news_repository.upsert_article_summaries(updates)

        return jsonify({
            "success": True,
            "data": {
                "items": items,
                "generatedCount": len(updates),
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to ensure news summaries: {str(e)}"
        }), 500
