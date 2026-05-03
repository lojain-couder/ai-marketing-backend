"""
Analysis Pipeline — connects rule-based Playground engines with Groq writing layer.
The engines make all analytical decisions.
Groq only rewrites outputs in polished Arabic.
"""

import re
from typing import Any

from bi_advisor.social_analysis_engine import SocialAnalysisEngine
from bi_advisor.recommendation_engine import MarketingRecommendationEngine
from bi_advisor.weekly_plan_generator import WeeklyMarketingPlanGenerator
from services.groq_writer import GroqWriter
from services.gemini_analyzer import GeminiAnalyzer


class AnalysisPipeline:

    def __init__(self):
        self.social_engine = SocialAnalysisEngine()
        self.rec_engine = MarketingRecommendationEngine()
        self.plan_generator = WeeklyMarketingPlanGenerator()
        self.writer = GroqWriter()
        self.gemini = GeminiAnalyzer()

    def run(self, normalized_data: dict) -> dict:
        raw_videos = normalized_data.get("videos", [])
        business_profile = normalized_data.get("business_profile", {})
        sales_rows = self._extract_sales_rows(normalized_data.get("sales_summary"))

        # Phase 0: Gemini enriches video content metadata (type, topic, hook, sentiment)
        raw_videos = self.gemini.enrich_videos(raw_videos)

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

        engine_output = {
            "insights": self._extract_insights(analysis),
            "strategies": strategies,
            "weekly_plan": weekly_plan,
            "root_cause": self._extract_root_cause(analysis),
            "dashboard_metrics": analysis.get("dashboard_metrics", {}),
            "content_patterns": analysis.get("content_patterns", {}),
            "data_quality": analysis.get("data_quality_summary", {}),
            "platform_comparison": analysis.get("platform_comparison", {}),
        }

        print("[Engine Output] insights:", len(engine_output["insights"]),
              "| strategies:", len(engine_output["strategies"]),
              "| weekly_plan:", len(engine_output["weekly_plan"]))

        # Step 4: Groq enriches language only — does NOT change analytical decisions
        enriched_output = self.writer.enrich(engine_output, business_profile)

        print("[Enriched Output] keys:", list(enriched_output.keys()))

        # Step 5: Gemini adds deep strategic marketing insights
        gemini_insights = self.gemini.generate_deep_insights(engine_output, business_profile)
        if gemini_insights:
            enriched_output["gemini_insights"] = gemini_insights

        return enriched_output

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
            "topic": v.get("topic"),
            "hook_type": v.get("hook_type"),
            "cta": v.get("cta"),
            "author_username": str(v.get("author_username") or ""),
            "music_name": v.get("music_name"),
            "location_name": v.get("location_name"),
            "language": v.get("language"),
        }

    # ── Sales extraction ─────────────────────────────────────────────────────

    def _extract_sales_rows(self, sales_summary: Any) -> list:
        if not sales_summary:
            return []
        if isinstance(sales_summary, list):
            return sales_summary
        if isinstance(sales_summary, dict):
            return sales_summary.get("rows", [])
        return []

    # ── Engine output builders ───────────────────────────────────────────────

    def _extract_insights(self, analysis: dict) -> list:
        insights = []
        perf = analysis.get("content_performance_summary", {})

        summary = perf.get("summary_text", "")
        if summary:
            insights.append({"type": "info", "title": "ملخص أداء المحتوى", "detail": summary})

        top_posts = perf.get("top_performing_posts", [])
        if top_posts:
            top = top_posts[0]
            caption_preview = (top.get("caption") or "")[:80]
            insights.append({
                "type": "good",
                "title": "أفضل محتوى أداءً",
                "detail": f"{caption_preview} — نسبة التفاعل: {top.get('engagement_rate', 0):.4f}",
            })

        platform_cmp = analysis.get("platform_comparison", {})
        if platform_cmp.get("available") and platform_cmp.get("summary_text"):
            insights.append({
                "type": "info",
                "title": "مقارنة المنصات",
                "detail": platform_cmp["summary_text"],
            })

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
