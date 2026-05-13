"""
Analysis Pipeline — connects rule-based engines with Groq/Gemini writing layer.
The engines make all analytical decisions.
Groq only rewrites outputs in polished Arabic.
"""

import os
import re
from typing import Any

from services.audio_downloader import download_audio
from bi_advisor.social_analysis_engine import SocialAnalysisEngine
from bi_advisor.recommendation_engine import MarketingRecommendationEngine
from bi_advisor.weekly_plan_generator import WeeklyMarketingPlanGenerator
from bi_advisor.engine import BusinessAdvisorEngine
from bi_advisor.memory import FileBusinessMemoryStore
from bi_advisor.domain import BusinessProfile as BIBusinessProfile, DataSourceStatus
from bi_advisor.sales_metrics_extractor import extract_metric_snapshot, build_sales_kpis
from bi_advisor.analysis_memory import AnalysisMemoryStore, build_snapshot
from bi_advisor.trend_engine import TrendEngine
from bi_advisor.content_sales_linker import (
    analyze_content_type_impact,
    analyze_posting_time_impact,
    analyze_duration_impact,
)
from bi_advisor.basket_analyzer import find_product_bundles
from bi_advisor.funnel_analyzer import detect_funnel_gap
from bi_advisor.caption_analyzer import analyze_caption_structure
from bi_advisor.product_content_analyzer import (
    extract_product_list,
    match_videos_to_products,
    compute_product_video_stats,
)
from bi_advisor.competitor_analyzer import compare_accounts
from bi_advisor.hook_scorer import score_hook_types
from bi_advisor.hashtag_gap_analyzer import find_hashtag_gaps
from bi_advisor.sales_normalizer import normalize_sales_rows, normalize_zid_orders, normalize_salla_orders
from services.groq_writer import GroqWriter
from services.gemini_analyzer import GeminiAnalyzer
from services.apify_service import fetch_comments_sync, fetch_social_media_sync

_BI_MEMORY_ROOT = os.getenv("BI_MEMORY_ROOT", "/tmp/mudar_bi_memory")


class AnalysisPipeline:

    def __init__(self):
        self.social_engine = SocialAnalysisEngine()
        self.rec_engine = MarketingRecommendationEngine()
        self.plan_generator = WeeklyMarketingPlanGenerator()
        self.writer = GroqWriter()
        self.gemini = GeminiAnalyzer()
        self._bi_memory = FileBusinessMemoryStore(_BI_MEMORY_ROOT)
        self._analysis_memory = AnalysisMemoryStore()
        self._trend_engine = TrendEngine()

    def run(self, normalized_data: dict) -> dict:
        raw_videos = normalized_data.get("videos", [])
        business_profile = normalized_data.get("business_profile", {})
        sales_summary = normalized_data.get("sales_summary") or {}
        transcripts = normalized_data.get("transcripts") or []
        competitor_accounts = normalized_data.get("competitor_accounts") or []
        sales_rows = self._extract_sales_rows(sales_summary)

        # Merge manually-provided transcripts (from frontend upload, if any)
        for i, t in enumerate(transcripts):
            if i < len(raw_videos) and isinstance(t, dict):
                raw_videos[i]["transcript"]    = t.get("transcript", "")
                raw_videos[i]["spoken_hook"]   = t.get("hook", "")
                raw_videos[i]["spoken_cta"]    = t.get("cta")
                raw_videos[i]["spoken_topic"]  = t.get("topic", "")
                raw_videos[i]["key_message"]   = t.get("key_message", "")

        # Auto-transcribe top videos that don't already have a transcript
        raw_videos = self._auto_transcribe_videos(raw_videos)

        # Phase 0a: Gemini enriches video content metadata (caption + transcript + vision)
        raw_videos = self.gemini.enrich_videos(raw_videos)

        # Phase 0b: Auto-fetch comments for top videos and analyze audience voice
        comment_voice = self._auto_fetch_and_analyze_comments(raw_videos, business_profile)

        # Phase 0c: Product recognition — match videos to sales product catalog
        product_insights = self._run_product_analysis(
            raw_videos, sales_rows, comment_voice, business_profile
        )

        # Phase 0d: Competitor analysis
        competitor_analysis = self._run_competitor_analysis(
            raw_videos, competitor_accounts, business_profile
        )

        # Phase 0e: Hook performance scoring
        hook_scores = score_hook_types(
            [self._to_social_row(v) for v in raw_videos], sales_rows
        )

        # Phase 0f: Hashtag gap analysis
        hashtag_gap = self._run_hashtag_gap(
            raw_videos, competitor_analysis, business_profile
        )

        # Phase 0g: Persona clustering (needs real comments)
        personas = []
        if comment_voice.get("source") == "real":
            raw_comments = comment_voice.get("_raw_comments", [])
            if len(raw_comments) >= 10:
                personas = self.gemini.cluster_audience_personas(raw_comments, business_profile)

        # Convert frontend video format → SocialAnalysisEngine format
        social_rows = [self._to_social_row(v) for v in raw_videos]
        selected_platforms = list({r["platform"] for r in social_rows}) or ["tiktok"]

        # Step 1: Rule-based content analysis
        analysis = self.social_engine.analyze(
            business_profile=business_profile,
            selected_platforms=selected_platforms,
            social_rows=social_rows,
            sales_rows=sales_rows,
        )

        # Step 2: Rule-based recommendations (strategies)
        strategies = self.rec_engine.generate(
            analysis=analysis,
            social_rows=social_rows,
            sales_rows=sales_rows,
        )

        # Step 3: Rule-based weekly plan
        weekly_plan = self.plan_generator.generate(
            business_profile=business_profile,
            selected_platforms=selected_platforms,
            social_rows=social_rows,
            analysis=analysis,
        )

        # Step 4: Sales-backed BI advisor analysis
        sales_analysis = self._run_sales_bi_analysis(
            sales_rows=sales_rows,
            social_rows=social_rows,
            business_profile=business_profile,
            selected_platforms=selected_platforms,
        )

        # Content type × sales correlation (which content types drove revenue)
        content_type_impact = analyze_content_type_impact(social_rows, sales_rows)

        # Phase 0h: Posting time heatmap (day × hour vs engagement + revenue)
        posting_time_impact = analyze_posting_time_impact(social_rows, sales_rows)

        # Phase 0i: Duration sweet spot
        duration_impact = analyze_duration_impact(social_rows, sales_rows)

        # Phase 0j: Basket analysis (products bought together)
        basket_analysis = find_product_bundles(sales_rows)

        # Phase 0k: Funnel gap detection
        funnel_analysis = detect_funnel_gap(social_rows, sales_rows)

        # Phase 0l: Caption structure analysis
        caption_analysis = analyze_caption_structure(social_rows, sales_rows)

        engine_output = {
            "insights": self._extract_insights(
                analysis, sales_analysis, sales_summary,
                content_type_impact, comment_voice, product_insights,
                competitor_analysis, hook_scores, hashtag_gap, personas,
                posting_time_impact, duration_impact, basket_analysis,
                funnel_analysis, caption_analysis,
            ),
            "strategies": strategies,
            "weekly_plan": weekly_plan,
            "root_cause": self._extract_root_cause(analysis),
            "dashboard_metrics": analysis.get("dashboard_metrics", {}),
            "content_patterns": analysis.get("content_patterns", {}),
            "data_quality": analysis.get("data_quality_summary", {}),
            "platform_comparison": analysis.get("platform_comparison", {}),
            "sales_analysis": sales_analysis,
            "content_type_impact": content_type_impact,
            "comment_voice": comment_voice,
            "product_insights": product_insights,
            "competitor_analysis": competitor_analysis,
            "hook_scores": hook_scores,
            "hashtag_gap":        hashtag_gap,
            "audience_personas":  personas,
            "posting_time":       posting_time_impact,
            "duration_impact":    duration_impact,
            "basket_analysis":    basket_analysis,
            "funnel_analysis":    funnel_analysis,
            "caption_analysis":   caption_analysis,
        }

        # Step 4b: Load history → compute trend → save new snapshot
        business_id = self._resolve_business_id(business_profile)
        trend_report = self._run_trend_analysis(business_id, engine_output)
        engine_output["trend_report"] = trend_report

        # Inject trend insights into the insights list so they surface to the user
        if trend_report.get("has_history"):
            for insight_ar in trend_report.get("arabic_insights", []):
                engine_output["insights"].append({
                    "type": "trend",
                    "title": "مقارنة مع التحليل السابق",
                    "detail": insight_ar,
                })
            if trend_report.get("strategy_signals"):
                for sig in trend_report["strategy_signals"]:
                    engine_output["insights"].append({
                        "type": "strategy_feedback",
                        "title": "تقييم الاستراتيجية السابقة",
                        "detail": sig.get("signal_ar", ""),
                        "outcome": sig.get("outcome", ""),
                    })

        print("[Engine Output] insights:", len(engine_output["insights"]),
              "| strategies:", len(engine_output["strategies"]),
              "| weekly_plan:", len(engine_output["weekly_plan"]),
              "| sales_analysis:", bool(sales_analysis.get("sales_kpis")),
              "| trend:", trend_report.get("overall_direction", "—"))

        # Step 5: Groq enriches language only — does NOT change analytical decisions
        enriched_output = self.writer.enrich(engine_output, business_profile)

        print("[Enriched Output] keys:", list(enriched_output.keys()))

        # Step 6: Gemini adds deep strategic marketing insights
        gemini_insights = self.gemini.generate_deep_insights(engine_output, business_profile)
        if gemini_insights:
            enriched_output["gemini_insights"] = gemini_insights

        return enriched_output

    # ── Business ID helper ───────────────────────────────────────────────────

    def _resolve_business_id(self, business_profile: dict) -> str:
        raw = (
            business_profile.get("business_id")
            or business_profile.get("business_name")
            or "default"
        )
        return re.sub(r"\W+", "_", str(raw)).lower().strip("_")

    # ── Trend analysis (memory save + compare) ───────────────────────────────

    def _run_trend_analysis(self, business_id: str, engine_output: dict) -> dict:
        """
        1. Load previous snapshots for this business.
        2. Build a snapshot from the current analysis output.
        3. Run TrendEngine to compare current vs. history.
        4. Save the new snapshot.
        Returns a plain dict (JSON-serializable) representing TrendReport.
        """
        try:
            previous_snapshots = self._analysis_memory.load_snapshots(business_id)
            snapshot = build_snapshot(business_id, engine_output, len(previous_snapshots))

            all_snapshots = previous_snapshots + [snapshot]
            report = self._trend_engine.analyze(all_snapshots)

            self._analysis_memory.save_snapshot(snapshot)

            # Serialize dataclass to plain dict
            return {
                "has_history": report.has_history,
                "total_analyses": report.total_analyses,
                "previous_period": report.previous_period,
                "current_period": report.current_period,
                "overall_direction": report.overall_direction,
                "improving": report.improving,
                "declining": report.declining,
                "stable": report.stable,
                "arabic_summary": report.arabic_summary,
                "arabic_insights": report.arabic_insights,
                "strategy_signals": report.strategy_signals,
                "platform_shifted": report.platform_shifted,
                "content_type_changed": report.content_type_changed,
                "platform_shift_note": report.platform_shift_note,
                "content_type_note": report.content_type_note,
                "metric_trends": [
                    {
                        "metric_key": t.metric_key,
                        "label_ar": t.label_ar,
                        "previous": t.previous,
                        "current": t.current,
                        "delta_pct": t.delta_pct,
                        "direction": t.direction,
                        "insight_ar": t.insight_ar,
                    }
                    for t in report.metric_trends
                ],
            }
        except Exception as exc:
            print(f"[TrendAnalysis] Error: {exc}")
            return {"has_history": False, "overall_direction": "error", "arabic_insights": []}

    # ── Sales-backed BI analysis ─────────────────────────────────────────────

    def _run_sales_bi_analysis(
        self,
        sales_rows: list[dict],
        social_rows: list[dict],
        business_profile: dict,
        selected_platforms: list[str],
    ) -> dict:
        """Run BusinessAdvisorEngine when sales data is available.

        Returns a dict with sales KPIs, funnel analysis, and BI recommendations
        that are grounded in actual revenue/conversion numbers.
        """
        if not sales_rows:
            return {
                "available": False,
                "reason": "no_sales_data",
                "message": "لم يتم رفع بيانات مبيعات — يعتمد التحليل على أداء المحتوى فقط.",
            }

        try:
            snapshot = extract_metric_snapshot(sales_rows, social_rows)
            sales_kpis = build_sales_kpis(sales_rows, social_rows)

            business_id = (
                business_profile.get("business_id")
                or re.sub(r"\W+", "_", business_profile.get("business_name", "default")).lower()
            )

            bi_profile = BIBusinessProfile(
                business_id=business_id,
                name=business_profile.get("business_name", "البزنس"),
                industry=business_profile.get("industry", ""),
                audience_type=business_profile.get("target_audience", "العملاء"),
                goals=business_profile.get("goals", []) if isinstance(business_profile.get("goals"), list)
                      else [business_profile.get("goals", "")] if business_profile.get("goals") else [],
                channels=selected_platforms,
                value_proposition=business_profile.get("value_proposition", ""),
            )

            data_sources = [
                DataSourceStatus(
                    source_name="sales_upload",
                    source_type="sales",
                    status="connected",
                ),
                DataSourceStatus(
                    source_name="social_scrape",
                    source_type="marketing",
                    status="connected",
                ),
            ]

            advisor = BusinessAdvisorEngine(self._bi_memory)
            advisor_output = advisor.run(bi_profile, snapshot, data_sources)

            bi_insights = [
                {
                    "title": ins.title,
                    "summary": ins.summary,
                    "evidence": ins.evidence,
                    "impact": ins.impact,
                    "reasoning": ins.reasoning,
                }
                for ins in advisor_output.data_backed_insights
            ]

            bi_recommendations = [
                {
                    "strategy_key": rec.strategy_key,
                    "title": rec.title,
                    "action": rec.action,
                    "root_cause": rec.root_cause,
                    "why_this_matters": rec.why_this_matters,
                    "expected_impact": rec.expected_impact,
                    "expected_metric": rec.expected_metric,
                    "expected_value": rec.expected_value,
                    "confidence": rec.confidence,
                    "priority": rec.priority,
                    "strategy_status": rec.strategy_status,
                }
                for rec in advisor_output.recommendations
            ]

            trend_summary = advisor_output.state_summary.behavioral_profile.trend_summary

            return {
                "available": True,
                "sales_kpis": sales_kpis,
                "bi_insights": bi_insights,
                "bi_recommendations": bi_recommendations,
                "trend_summary": trend_summary,
                "funnel_stage": self._infer_funnel_label(trend_summary),
                "reasoning_summary": advisor_output.reasoning_summary,
            }

        except Exception as exc:
            print(f"[SalesBI] Error: {exc}")
            return {
                "available": False,
                "reason": "analysis_error",
                "message": f"تعذّر تشغيل تحليل المبيعات: {exc}",
                "sales_kpis": build_sales_kpis(sales_rows, social_rows),
            }

    def _infer_funnel_label(self, trend_summary: dict) -> str:
        if not trend_summary or trend_summary.get("status") == "baseline_only":
            return "baseline"
        revenue_trend = trend_summary.get("revenue", "stable")
        leads_trend = trend_summary.get("leads", "stable")
        conversion_trend = trend_summary.get("conversion_rate", "stable")
        if revenue_trend == "up" and leads_trend == "up":
            return "balanced_growth"
        if revenue_trend == "down" and conversion_trend == "stable":
            return "top_of_funnel"
        if conversion_trend == "down" and leads_trend == "stable":
            return "conversion"
        if revenue_trend == "up" and trend_summary.get("returning_customer_rate") == "up":
            return "retention"
        return "mixed"

    # ── Video normalization ──────────────────────────────────────────────────

    def _to_social_row(self, v: dict[str, Any]) -> dict[str, Any]:
        """Convert apify_service normalized video → SocialAnalysisEngine row format."""
        views = int(v.get("views") or v.get("playCount") or 0)
        likes = int(v.get("likes") or v.get("diggCount") or 0)
        comments = int(v.get("comments") or v.get("commentCount") or 0)
        shares = int(v.get("shares") or v.get("shareCount") or 0)
        engagement_rate = round((likes + comments + shares) / views, 4) if views > 0 else 0.0

        caption = str(v.get("caption") or v.get("text") or v.get("desc") or "")
        hashtags = re.findall(r"#\w+", caption)

        platform = str(v.get("platform") or "tiktok").lower()
        default_media = "text" if platform == "x" else "video"

        return {
            "platform": platform,
            "content_id": str(v.get("id") or ""),
            "content_url": str(v.get("url") or ""),
            "posted_at": str(v.get("posted_at") or ""),
            "caption": caption,
            "hashtags": hashtags,
            "views": views,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "engagement_rate": engagement_rate,
            "media_type": str(v.get("media_type") or default_media),
            "content_type": str(v.get("_type") or v.get("content_type") or ""),
            "topic":        v.get("topic") or v.get("spoken_topic"),
            "hook_type":    v.get("hook_type"),
            "cta":          v.get("cta") or v.get("spoken_cta"),
            "transcript":   v.get("transcript", ""),
            "spoken_hook":  v.get("spoken_hook", ""),
            "key_message":  v.get("key_message", ""),
            "author_username": str(v.get("author_username") or ""),
            "music_name":     v.get("music_name"),
            "location_name":  v.get("location_name"),
            "language":       v.get("language"),
            "duration":       int(v.get("duration") or 0),
            "quality_score":  self._compute_quality_score(views, likes, comments, shares),
        }

    @staticmethod
    def _compute_quality_score(views: int, likes: int, comments: int, shares: int) -> float:
        if views == 0:
            return 0.0
        return round((likes * 1 + comments * 3 + shares * 5) / views, 6)

    # ── Competitor analysis ───────────────────────────────────────────────────

    def _run_competitor_analysis(
        self,
        raw_videos: list[dict],
        competitor_accounts: list[dict],
        business_profile: dict,
    ) -> dict:
        """Fetch competitor posts, compare, generate narrative insights."""
        if not competitor_accounts:
            return {"available": False, "reason": "no_competitors_provided"}

        competitors_data = []
        for acc in competitor_accounts[:3]:
            platform = str(acc.get("platform") or "tiktok").lower()
            username = str(acc.get("username") or "").strip().lstrip("@")
            if not username:
                continue
            print(f"[Competitor] Fetching @{username} on {platform}")
            result = fetch_social_media_sync(platform, username, limit=25)
            if result.get("posts"):
                competitors_data.append(result)
                print(f"[Competitor] @{username} — {len(result['posts'])} posts")
            else:
                print(f"[Competitor] @{username} — no posts (skipped)")

        if not competitors_data:
            return {"available": False, "reason": "competitor_fetch_failed"}

        account_rows = [self._to_social_row(v) for v in raw_videos]
        comparison = compare_accounts(account_rows, competitors_data)

        # Gemini narrative insights on top of structured comparison
        narrative = self.gemini.generate_competitor_insights(comparison, business_profile)
        if narrative:
            comparison["narrative"] = narrative

        return comparison

    # ── Hashtag gap analysis ──────────────────────────────────────────────────

    def _run_hashtag_gap(
        self,
        raw_videos: list[dict],
        competitor_analysis: dict,
        business_profile: dict,
    ) -> dict:
        """Find hashtag gaps vs competitors + Gemini trending suggestions."""
        account_rows = [self._to_social_row(v) for v in raw_videos]

        # Build competitor data structure expected by hashtag gap analyzer
        competitor_data_for_hashtags = []
        if competitor_analysis.get("available"):
            for cs in competitor_analysis.get("competitor_stats", []):
                competitor_data_for_hashtags.append({
                    "username": cs.get("username", ""),
                    "posts": [],  # hashtags are already in competitor_stats top_hashtags
                })
            # Re-attach posts from competitor_analysis if available
            # We use top_hashtags from competitor_stats as a proxy
            pass

        # Extract account hashtags
        import re as _re
        account_hashtags = list({
            tag.lower()
            for v in raw_videos
            for tag in _re.findall(r"#\w+", str(v.get("caption") or ""))
        })

        competitor_hashtags = competitor_analysis.get("unused_competitor_hashtags", [])

        # Gemini suggests additional trending hashtags for the niche
        gemini_suggestions = self.gemini.suggest_trending_hashtags(
            business_profile, account_hashtags, competitor_hashtags
        )

        return find_hashtag_gaps(account_rows, competitor_data_for_hashtags, gemini_suggestions)

    # ── Product recognition & per-product strategy ───────────────────────────

    def _run_product_analysis(
        self,
        raw_videos: list[dict],
        sales_rows: list[dict],
        comment_voice: dict,
        business_profile: dict,
    ) -> dict:
        """
        1. Extract product list from sales data.
        2. Match each video to products it features (text matching on caption/transcript).
        3. Compute per-product engagement + revenue stats.
        4. Analyze comments per product (if real comments available).
        5. Generate per-product content strategy + seller improvement tips via Gemini.
        """
        products = extract_product_list(sales_rows)
        if not products:
            return {"available": False, "reason": "no_products_in_sales_data"}

        # Match videos → products (mutates raw_videos in-place adding 'featured_products')
        raw_videos = match_videos_to_products(raw_videos, products)

        # Need social_rows format for stats — convert quickly
        social_rows_for_products = [self._to_social_row(v) for v in raw_videos]
        # Re-attach featured_products (lost during conversion)
        for i, v in enumerate(raw_videos):
            social_rows_for_products[i]["featured_products"] = v.get("featured_products", [])
            social_rows_for_products[i]["visual_type"]       = v.get("visual_type", "")
            social_rows_for_products[i]["content_type"]      = v.get("content_type", "")

        product_stats = compute_product_video_stats(social_rows_for_products, sales_rows, products)

        # Product-level comment analysis (only when we have real comments)
        product_voices: list[dict] = []
        if comment_voice.get("source") == "real":
            raw_comments = comment_voice.get("_raw_comments", [])
            if raw_comments:
                product_voices = self.gemini.analyze_product_comments(
                    raw_comments, product_stats, business_profile
                )

        # Per-product content strategy + seller improvement tips
        strategies = self.gemini.generate_product_content_strategy(
            product_stats, business_profile, product_voices
        )

        # Merge strategies into product_stats
        strategy_map = {s["product_name"]: s for s in strategies}
        voice_map    = {v["product_name"]: v for v in product_voices}

        enriched_stats = []
        for p in product_stats:
            name = p["product_name"]
            entry = dict(p)
            if name in strategy_map:
                entry["content_strategy"] = strategy_map[name]
            if name in voice_map:
                entry["comment_voice"] = voice_map[name]
            enriched_stats.append(entry)

        featured_count = sum(1 for p in product_stats if p.get("featuring_video_count", 0) > 0)
        print(
            f"[ProductAnalysis] {len(products)} products | "
            f"{featured_count} featured in videos | "
            f"{len(strategies)} strategies generated"
        )

        return {
            "available": True,
            "product_count": len(products),
            "featured_count": featured_count,
            "products": enriched_stats,
        }

    # ── Auto comment fetching & analysis ────────────────────────────────────

    def _auto_fetch_and_analyze_comments(
        self,
        videos: list[dict],
        business_profile: dict,
        max_videos: int = 5,
    ) -> dict:
        """
        Fetch real comments from Apify for the top-performing videos,
        then run Gemini comment analysis. Falls back to caption-based estimation.
        Returns the comment_voice dict (questions, requests, suggestions, etc.)
        """
        # Detect platform from videos
        platforms = list({str(v.get("platform") or "tiktok").lower() for v in videos})
        platform = platforms[0] if platforms else "tiktok"

        # Only tiktok/instagram supported for comment fetching
        if platform not in ("tiktok", "instagram"):
            return {}

        # Get URLs of top videos sorted by views
        top_videos = sorted(
            [v for v in videos if v.get("url")],
            key=lambda v: int(v.get("views") or 0),
            reverse=True,
        )[:max_videos]

        urls = [v["url"] for v in top_videos if v.get("url")]

        if urls:
            print(f"[CommentFetch] Fetching comments for {len(urls)} top videos ({platform})")
            try:
                comments = fetch_comments_sync(platform, urls, max_per_video=40)
                print(f"[CommentFetch] Got {len(comments)} comments")
            except Exception as e:
                print(f"[CommentFetch] Failed: {e}")
                comments = []
        else:
            comments = []

        if comments:
            result = self.gemini.analyze_comments(comments, business_profile)
            if result:
                result["source"] = "real"
                result["comments_count"] = len(comments)
                result["_raw_comments"] = comments  # kept for product-level analysis
                return result

        # Fallback: estimate from captions
        captions = [str(v.get("caption") or "") for v in videos if v.get("caption")]
        if captions:
            print("[CommentFetch] Falling back to caption-based estimation")
            result = self.gemini.analyze_from_captions(captions, business_profile)
            if result:
                result["source"] = "estimated"
                return result

        return {}

    # ── Auto audio transcription ─────────────────────────────────────────────

    def _auto_transcribe_videos(self, videos: list[dict], max_videos: int = 5) -> list[dict]:
        """
        Download audio for the top-performing videos (by engagement) and transcribe.
        Skips videos that already have a transcript. Silently skips on any error.
        """
        # Pick top videos by engagement_rate that have a URL and no transcript yet
        candidates = sorted(
            [
                (i, v) for i, v in enumerate(videos)
                if v.get("url") and not v.get("transcript")
            ],
            key=lambda x: float(x[1].get("engagement_rate") or 0),
            reverse=True,
        )[:max_videos]

        if not candidates:
            return videos

        print(f"[AudioTranscription] Attempting {len(candidates)} videos")

        for i, v in candidates:
            url = v.get("url", "")
            try:
                result = download_audio(url)
                if not result:
                    continue
                audio_bytes, fname = result
                transcript = self.writer.transcribe_audio(audio_bytes, fname)
                if not transcript or not transcript.strip():
                    continue
                elements = self.writer.extract_spoken_elements(
                    transcript, caption=v.get("caption", "")
                )
                videos[i]["transcript"]   = transcript.strip()
                videos[i]["spoken_hook"]  = elements.get("hook", "")
                videos[i]["spoken_cta"]   = elements.get("cta")
                videos[i]["spoken_topic"] = elements.get("topic", "")
                videos[i]["key_message"]  = elements.get("key_message", "")
                print(f"[AudioTranscription] ✓ {url[:60]}")
            except Exception as e:
                print(f"[AudioTranscription] Skipped {url[:60]}: {e}")

        transcribed = sum(1 for v in videos if v.get("transcript"))
        print(f"[AudioTranscription] Done — {transcribed} videos with transcripts")
        return videos

    # ── Sales extraction ─────────────────────────────────────────────────────

    def _extract_sales_rows(self, sales_summary: Any) -> list:
        if not sales_summary:
            return []

        # Zid / Salla API format — list of raw order objects
        if isinstance(sales_summary, list):
            first = sales_summary[0] if sales_summary else {}
            # Detect Zid orders by presence of 'order_status' dict or 'order_total'
            if isinstance(first.get("order_status"), dict) or "order_total" in first:
                return normalize_zid_orders(sales_summary)
            # Detect Salla orders by presence of 'total.amount' structure
            if isinstance(first.get("total"), dict) and "amount" in first.get("total", {}):
                return normalize_salla_orders(sales_summary)
            # Plain rows (already normalized or from CSV upload preview)
            rows, _, _ = normalize_sales_rows(sales_summary)
            return rows

        if isinstance(sales_summary, dict):
            # CSV upload: "preview" contains actual row dicts
            preview = sales_summary.get("preview", [])
            if isinstance(preview, list) and preview:
                rows, _, _ = normalize_sales_rows(preview)
                return rows

        return []

    # ── Engine output builders ───────────────────────────────────────────────

    def _extract_insights(
        self,
        analysis: dict,
        sales_analysis: dict,
        sales_summary: dict | None = None,
        content_type_impact: dict | None = None,
        comment_voice: dict | None = None,
        product_insights: dict | None = None,
        competitor_analysis: dict | None = None,
        hook_scores: dict | None = None,
        hashtag_gap: dict | None = None,
        audience_personas: list | None = None,
        posting_time_impact: dict | None = None,
        duration_impact: dict | None = None,
        basket_analysis: dict | None = None,
        funnel_analysis: dict | None = None,
        caption_analysis: dict | None = None,
    ) -> list:
        insights = []
        perf = analysis.get("content_performance_summary", {})

        summary = perf.get("summary_text", "")
        if summary:
            insights.append({"type": "info", "title": "ملخص أداء المحتوى", "detail": summary})

        top_posts = perf.get("top_performing_posts", [])
        if top_posts:
            top = top_posts[0]
            caption_preview = (top.get("caption") or "")[:80]
            detail = f"{caption_preview} — نسبة التفاعل: {top.get('engagement_rate', 0):.4f}"
            # Enrich with visual info if available
            if top.get("visual_type"):
                detail += f" — نوع المشهد: {top['visual_type']}"
            insights.append({"type": "good", "title": "أفضل محتوى أداءً", "detail": detail})

        platform_cmp = analysis.get("platform_comparison", {})
        if platform_cmp.get("available") and platform_cmp.get("summary_text"):
            insights.append({
                "type": "info",
                "title": "مقارنة المنصات",
                "detail": platform_cmp["summary_text"],
            })

        # Content type × sales impact
        ct = content_type_impact or {}
        if ct.get("available"):
            summary_ar = ct.get("summary_ar", "")
            if summary_ar:
                insights.append({
                    "type": "content_type",
                    "title": "نوع المحتوى الأكثر تأثيراً على المبيعات",
                    "detail": summary_ar,
                    "top_type": ct.get("top_revenue_content_type"),
                    "top_visual_type": ct.get("top_revenue_visual_type"),
                    "breakdown": ct.get("content_type_impact", [])[:4],
                })
            cta_data = ct.get("cta_impact", {})
            if cta_data.get("summary_ar"):
                insights.append({
                    "type": "content_type",
                    "title": "أثر الـ CTA وذكر السعر",
                    "detail": cta_data["summary_ar"],
                })

        # Comment voice insights
        cv = comment_voice or {}
        if cv.get("frequent_questions"):
            questions_str = " | ".join(cv["frequent_questions"][:3])
            insights.append({
                "type": "audience_voice",
                "title": "أكثر الأسئلة من الجمهور",
                "detail": questions_str,
                "source": cv.get("source", "estimated"),
                "purchase_signals": cv.get("purchase_signals", []),
                "content_suggestions": cv.get("content_suggestions", []),
            })
        if cv.get("product_requests"):
            reqs_str = " | ".join(cv["product_requests"][:3])
            insights.append({
                "type": "audience_voice",
                "title": "أكثر طلبات الجمهور",
                "detail": reqs_str,
            })

        # Product insights — top products with content strategy
        pi = product_insights or {}
        if pi.get("available") and pi.get("products"):
            # Surface top 3 products by revenue that have a content strategy
            top_products = [
                p for p in pi["products"]
                if p.get("content_strategy")
            ][:3]
            for p in top_products:
                strat = p["content_strategy"]
                detail_parts = [
                    f"الإيراد: {p.get('revenue', 0):,.0f}",
                    f"الطلبات: {p.get('orders', 0)}",
                ]
                if p.get("featuring_video_count", 0) > 0:
                    detail_parts.append(f"يظهر في {p['featuring_video_count']} فيديو")
                if p.get("engagement_lift_pct") is not None:
                    sign = "+" if p["engagement_lift_pct"] >= 0 else ""
                    detail_parts.append(f"التفاعل عند ظهوره: {sign}{p['engagement_lift_pct']}٪")

                insights.append({
                    "type": "product",
                    "title": f"منتج: {p['product_name']}",
                    "detail": " | ".join(detail_parts),
                    "priority": strat.get("priority", "medium"),
                    "why_priority": strat.get("why_priority", ""),
                    "content_ideas": strat.get("content_ideas", []),
                    "best_content_type": strat.get("best_content_type", ""),
                    "hook_suggestion": strat.get("hook_suggestion", ""),
                    "seller_improvements": strat.get("seller_improvements", []),
                    "comment_voice": p.get("comment_voice", {}),
                })

            # Products with no content yet — flag as opportunity
            no_content = [
                p for p in pi["products"]
                if not p.get("has_content") and p.get("revenue", 0) > 0
            ][:2]
            for p in no_content:
                insights.append({
                    "type": "product_opportunity",
                    "title": f"منتج بدون محتوى: {p['product_name']}",
                    "detail": f"إيراد {p.get('revenue', 0):,.0f} لكن لم يظهر في أي فيديو — فرصة للمحتوى",
                    "revenue": p.get("revenue", 0),
                })

        # Hook performance scoring
        hs = hook_scores or {}
        if hs.get("available") and hs.get("best_hook_type"):
            insights.append({
                "type": "hook_score",
                "title": "أفضل نوع hook لحسابك",
                "detail": hs.get("summary_ar", ""),
                "best_hook_type": hs.get("best_hook_type"),
                "ranked_hooks": hs.get("ranked_hooks", []),
            })

        # Competitor analysis
        ca = competitor_analysis or {}
        if ca.get("available"):
            benchmark = ca.get("benchmark", {})
            narrative = ca.get("narrative", {})
            insights.append({
                "type": "competitor",
                "title": "مقارنة مع المنافسين",
                "detail": narrative.get("competitive_position", ""),
                "benchmark": benchmark,
                "gaps": ca.get("gaps", [])[:3],
                "top_lessons": narrative.get("top_competitor_lessons", []),
                "immediate_actions": narrative.get("immediate_actions", []),
            })

        # Hashtag gaps
        hg = hashtag_gap or {}
        if hg.get("available") and hg.get("gaps"):
            top_gaps = [g["hashtag"] for g in hg["gaps"][:8]]
            insights.append({
                "type": "hashtag_gap",
                "title": "هاشتاقات لم تستخدمها بعد",
                "detail": hg.get("summary_ar", ""),
                "unused_hashtags": top_gaps,
                "gap_count": hg.get("gap_count", 0),
            })

        # Audience personas
        ap = audience_personas or []
        if ap:
            insights.append({
                "type": "personas",
                "title": "شخصيات الجمهور",
                "detail": f"تم تحديد {len(ap)} شخصيات رئيسية في جمهورك",
                "personas": ap,
            })

        # Posting time heatmap
        pt = posting_time_impact or {}
        if pt.get("available") and pt.get("best_slot"):
            insights.append({
                "type":       "posting_time",
                "title":      "أفضل وقت للنشر",
                "detail":     pt.get("summary_ar", ""),
                "best_slot":  pt.get("best_slot", ""),
                "best_day":   pt.get("best_day", ""),
                "best_hour":  pt.get("best_hour", ""),
                "top_slots":  pt.get("top_slots", [])[:3],
            })

        # Duration sweet spot
        di = duration_impact or {}
        if di.get("available") and di.get("best_bucket"):
            insights.append({
                "type":         "duration",
                "title":        "أفضل طول للفيديو",
                "detail":       di.get("summary_ar", ""),
                "best_bucket":  di.get("best_bucket", ""),
                "duration_stats": di.get("duration_stats", []),
            })

        # Basket analysis
        ba = basket_analysis or {}
        if ba.get("available") and ba.get("bundles"):
            top_bundle = ba["bundles"][0]
            insights.append({
                "type":    "basket",
                "title":   "منتجات تُشترى معاً",
                "detail":  ba.get("summary_ar", ""),
                "bundles": ba.get("bundles", [])[:5],
                "multi_order_pct": ba.get("multi_order_pct", 0),
            })

        # Funnel gap
        fa = funnel_analysis or {}
        if fa.get("available"):
            insights.append({
                "type":      "funnel",
                "title":     "تشخيص مسار العميل",
                "detail":    fa.get("gap_diagnosis_ar", ""),
                "action":    fa.get("recommended_action_ar", ""),
                "gap_stage": fa.get("gap_stage", ""),
                "severity":  fa.get("severity", ""),
                "metrics": {
                    "total_views":          fa.get("total_views", 0),
                    "avg_engagement_rate":  fa.get("avg_engagement_rate", 0),
                    "total_orders":         fa.get("total_orders", 0),
                    "overall_conversion":   fa.get("overall_conversion_pct", 0),
                },
            })

        # Caption structure
        ca = caption_analysis or {}
        if ca.get("available") and ca.get("summary_ar"):
            insights.append({
                "type":          "caption",
                "title":         "أفضل بنية للكابشن",
                "detail":        ca.get("summary_ar", ""),
                "best_length":   ca.get("best_length", ""),
                "best_opening":  ca.get("best_opening", ""),
                "best_emoji":    ca.get("best_emoji", ""),
                "length_stats":  ca.get("length_stats", []),
                "opening_stats": ca.get("opening_stats", []),
            })

        # Sales-backed insights from BI advisor
        if sales_analysis.get("available"):
            kpis = sales_analysis.get("sales_kpis", {})
            if kpis.get("revenue"):
                roas_text = f" | ROAS: {kpis['roas']}" if kpis.get("roas") else ""
                insights.append({
                    "type": "sales",
                    "title": "ملخص المبيعات",
                    "detail": (
                        f"الإيراد الإجمالي: {kpis['revenue']:,.2f} | "
                        f"الطلبات: {kpis['total_orders']} | "
                        f"متوسط قيمة الطلب: {kpis['avg_order_value']:,.2f}"
                        f"{roas_text}"
                    ),
                })
            for bi_ins in sales_analysis.get("bi_insights", [])[:3]:
                insights.append({
                    "type": "sales",
                    "title": bi_ins.get("title", ""),
                    "detail": bi_ins.get("summary", ""),
                    "evidence": bi_ins.get("evidence", []),
                    "impact": bi_ins.get("impact", "medium"),
                })
        elif not sales_analysis.get("available"):
            csv_insights = (sales_summary or {}).get("csv_insights", "")
            if csv_insights:
                insights.append({
                    "type": "info",
                    "title": "تحليل ملف المبيعات",
                    "detail": csv_insights,
                })
            else:
                for limitation in analysis.get("data_quality_summary", {}).get("analysis_limitations", []):
                    insights.append({"type": "warning", "title": "تنبيه", "detail": limitation})

        return insights

    def _extract_root_cause(self, analysis: dict) -> dict:
        perf = analysis.get("content_performance_summary", {})
        dashboard = analysis.get("dashboard_metrics", {})
        patterns = analysis.get("content_patterns", {})
        return {
            "best_platform": perf.get("best_platform_by_engagement"),
            "best_media_type": dashboard.get("top_content_type"),
            "top_posting_time": dashboard.get("top_posting_time"),
            "avg_engagement": dashboard.get("avg_engagement_rate"),
            "total_posts": dashboard.get("total_posts"),
            "total_views": dashboard.get("total_views"),
            "high_performing_hooks": patterns.get("high_performing_hooks", [])[:2],
            "best_hashtags": patterns.get("best_hashtags", [])[:3],
            "best_topics": patterns.get("repeated_topics", [])[:2],
        }
