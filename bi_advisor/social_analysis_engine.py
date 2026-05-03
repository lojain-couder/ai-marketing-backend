from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from typing import Any

from .content_sales_linker import analyze_content_sales_links


class SocialAnalysisEngine:
    def analyze(
        self,
        business_profile: dict[str, Any],
        selected_platforms: list[str],
        social_rows: list[dict[str, Any]],
        sales_rows: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        sales_missing_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        sales_rows = sales_rows or []
        warnings = warnings or []
        sales_missing_fields = sales_missing_fields or []

        analyzed_platforms = sorted({row["platform"] for row in social_rows})
        posts_by_platform = {
            platform: len([row for row in social_rows if row["platform"] == platform])
            for platform in analyzed_platforms
        }

        data_quality_summary = self._build_data_quality_summary(
            selected_platforms=selected_platforms,
            analyzed_platforms=analyzed_platforms,
            social_rows=social_rows,
            posts_by_platform=posts_by_platform,
            sales_rows=sales_rows,
            warnings=warnings,
            sales_missing_fields=sales_missing_fields,
        )
        content_performance_summary = self._build_content_performance_summary(social_rows)
        platform_comparison = self._build_platform_comparison(social_rows, analyzed_platforms)
        content_patterns = self._build_content_patterns(social_rows)
        sales_impact_analysis = analyze_content_sales_links(social_rows, sales_rows)
        dashboard_metrics = self._build_dashboard_metrics(
            social_rows=social_rows,
            sales_rows=sales_rows,
            content_performance_summary=content_performance_summary,
            platform_comparison=platform_comparison,
            sales_impact_analysis=sales_impact_analysis,
            selected_platforms=selected_platforms,
            analyzed_platforms=analyzed_platforms,
        )

        return {
            "data_quality_summary": data_quality_summary,
            "content_performance_summary": content_performance_summary,
            "platform_comparison": platform_comparison,
            "content_patterns": content_patterns,
            "sales_impact_analysis": sales_impact_analysis,
            "dashboard_metrics": dashboard_metrics,
        }

    def _build_data_quality_summary(
        self,
        selected_platforms: list[str],
        analyzed_platforms: list[str],
        social_rows: list[dict[str, Any]],
        posts_by_platform: dict[str, int],
        sales_rows: list[dict[str, Any]],
        warnings: list[str],
        sales_missing_fields: list[str],
    ) -> dict[str, Any]:
        limitations: list[str] = []
        if not sales_rows:
            limitations.append("لم يتم رفع بيانات مبيعات، لذلك يقتصر التحليل على أداء المحتوى.")
        elif sales_missing_fields:
            limitations.append(
                "تحليل الربط بالمبيعات محدود بسبب نقص بعض الحقول المهمة: "
                + ", ".join(sales_missing_fields)
            )

        if len(analyzed_platforms) == 1:
            limitations.append("لا يمكن إجراء مقارنة بين المنصات لأن البيانات المتاحة تخص منصة واحدة فقط.")

        summary_text = (
            f"تم تحليل بيانات {self._platforms_arabic(analyzed_platforms)}."
            if analyzed_platforms
            else "لم يتم العثور على بيانات محتوى قابلة للتحليل."
        )
        if not sales_rows:
            summary_text += " لم يتم رفع بيانات مبيعات، لذلك يعتمد التحليل على أداء المحتوى فقط."
        elif sales_missing_fields:
            summary_text += " توجد بيانات مبيعات، لكن تحليل الأثر على المبيعات محدود بسبب نقص بعض الحقول."
        else:
            summary_text += " تم تضمين بيانات المبيعات في التحليل بقدر ما تسمح به الحقول المتاحة."

        return {
            "selected_platforms": selected_platforms,
            "analyzed_platforms": analyzed_platforms,
            "posts_analyzed_per_platform": posts_by_platform,
            "sales_included": bool(sales_rows),
            "sales_rows_analyzed": len(sales_rows),
            "missing_important_columns": {
                "social": self._missing_social_columns(social_rows, analyzed_platforms),
                "sales": sales_missing_fields,
            },
            "warnings": warnings,
            "analysis_limitations": limitations,
            "summary_text": summary_text,
        }

    def _build_content_performance_summary(self, social_rows: list[dict[str, Any]]) -> dict[str, Any]:
        rows_by_platform = self._group_by(social_rows, "platform")
        avg_engagement = {
            platform: round(mean([row["engagement_rate"] for row in rows]), 4)
            for platform, rows in rows_by_platform.items()
        }
        total_views = {
            platform: sum(int(row.get("views") or 0) for row in rows)
            for platform, rows in rows_by_platform.items()
        }
        best_platform_by_engagement = max(avg_engagement, key=avg_engagement.get) if avg_engagement else None
        best_platform_by_views = max(total_views, key=total_views.get) if total_views else None
        top_posts = sorted(
            social_rows,
            key=lambda row: (row.get("engagement_rate", 0.0), row.get("views", 0), row.get("likes", 0)),
            reverse=True,
        )[:5]

        media_stats = defaultdict(list)
        posting_hour_stats = defaultdict(list)
        for row in social_rows:
            media_stats[row.get("media_type") or "unknown"].append(row.get("engagement_rate", 0.0))
            posted_at = self._parse_iso(row.get("posted_at"))
            if posted_at is not None:
                posting_hour_stats[f"{posted_at.hour:02d}:00"].append(row.get("engagement_rate", 0.0))

        best_media_types = [
            {
                "media_type": media_type,
                "avg_engagement_rate": round(mean(values), 4),
                "posts": len(values),
            }
            for media_type, values in sorted(
                media_stats.items(),
                key=lambda item: mean(item[1]),
                reverse=True,
            )[:5]
        ]
        best_posting_times = [
            {
                "time": hour,
                "avg_engagement_rate": round(mean(values), 4),
                "posts": len(values),
            }
            for hour, values in sorted(
                posting_hour_stats.items(),
                key=lambda item: mean(item[1]),
                reverse=True,
            )[:5]
            if len(values) >= 1
        ]

        return {
            "top_performing_posts": [
                {
                    "platform": row.get("platform"),
                    "content_id": row.get("content_id"),
                    "content_url": row.get("content_url"),
                    "caption": row.get("caption"),
                    "media_type": row.get("media_type"),
                    "views": row.get("views"),
                    "engagement_rate": row.get("engagement_rate"),
                }
                for row in top_posts
            ],
            "average_engagement_rate_by_platform": avg_engagement,
            "best_platform_by_engagement": best_platform_by_engagement,
            "best_platform_by_reach": best_platform_by_views,
            "best_media_types": best_media_types,
            "best_posting_times": best_posting_times,
            "summary_text": self._content_summary_text(
                avg_engagement,
                total_views,
                best_platform_by_engagement,
                best_platform_by_views,
            ),
        }

    def _build_platform_comparison(
        self,
        social_rows: list[dict[str, Any]],
        analyzed_platforms: list[str],
    ) -> dict[str, Any]:
        if len(analyzed_platforms) < 2:
            return {
                "available": False,
                "message": "Platform comparison is not available because only one platform was provided.",
            }

        rows_by_platform = self._group_by(social_rows, "platform")
        comparison_rows = []
        for platform, rows in rows_by_platform.items():
            comparison_rows.append(
                {
                    "platform": platform,
                    "total_views": sum(int(row.get("views") or 0) for row in rows),
                    "avg_engagement_rate": round(mean([row.get("engagement_rate", 0.0) for row in rows]), 4),
                    "likes": sum(int(row.get("likes") or 0) for row in rows),
                    "comments": sum(int(row.get("comments") or 0) for row in rows),
                    "shares": sum(int(row.get("shares") or 0) for row in rows),
                    "posting_frequency": len(rows),
                    "best_post": max(rows, key=lambda row: row.get("engagement_rate", 0.0)),
                }
            )

        comparison_rows.sort(key=lambda item: item["avg_engagement_rate"], reverse=True)
        return {
            "available": True,
            "platforms": comparison_rows,
            "summary_text": (
                f"الأداء الأعلى من حيث التفاعل كان في {comparison_rows[0]['platform']}، "
                f"بينما الأعلى من حيث الوصول كان في "
                f"{max(comparison_rows, key=lambda item: item['total_views'])['platform']}."
            ),
        }

    def _build_content_patterns(self, social_rows: list[dict[str, Any]]) -> dict[str, Any]:
        hashtag_stats: dict[str, list[float]] = defaultdict(list)
        topic_stats: dict[str, list[float]] = defaultdict(list)
        hook_stats: dict[str, list[float]] = defaultdict(list)
        media_type_stats: dict[str, list[float]] = defaultdict(list)
        music_stats: dict[str, list[float]] = defaultdict(list)
        location_stats: dict[str, list[float]] = defaultdict(list)
        language_stats: dict[str, list[float]] = defaultdict(list)
        text_length_stats: dict[str, list[float]] = defaultdict(list)

        for row in social_rows:
            engagement = row.get("engagement_rate", 0.0)
            for hashtag in row.get("hashtags", []):
                hashtag_stats[hashtag.lower()].append(engagement)
            if row.get("topic"):
                topic_stats[str(row["topic"]).lower()].append(engagement)
            if row.get("hook_type"):
                hook_stats[str(row["hook_type"]).lower()].append(engagement)
            media_type_stats[str(row.get("media_type") or "unknown").lower()].append(engagement)
            if row.get("music_name"):
                music_stats[str(row["music_name"]).lower()].append(engagement)
            if row.get("location_name"):
                location_stats[str(row["location_name"]).lower()].append(engagement)
            if row.get("language"):
                language_stats[str(row["language"]).lower()].append(engagement)
            text_length_stats[self._length_bucket(row.get("caption", ""))].append(engagement)

        top_posts = sorted(
            social_rows,
            key=lambda row: row.get("engagement_rate", 0.0),
            reverse=True,
        )[:5]

        return {
            "best_hashtags": self._top_patterns(hashtag_stats),
            "repeated_topics": self._top_patterns(topic_stats),
            "high_performing_hooks": self._top_patterns(hook_stats),
            "media_type_performance": self._top_patterns(media_type_stats),
            "text_length_performance": self._top_patterns(text_length_stats),
            "music_name_performance": self._top_patterns(music_stats),
            "location_name_performance": self._top_patterns(location_stats),
            "language_performance": self._top_patterns(language_stats),
            "high_performing_captions": [
                {
                    "platform": row.get("platform"),
                    "caption_preview": (row.get("caption") or "")[:160],
                    "engagement_rate": row.get("engagement_rate"),
                }
                for row in top_posts
            ],
        }

    def _build_dashboard_metrics(
        self,
        social_rows: list[dict[str, Any]],
        sales_rows: list[dict[str, Any]],
        content_performance_summary: dict[str, Any],
        platform_comparison: dict[str, Any],
        sales_impact_analysis: dict[str, Any],
        selected_platforms: list[str],
        analyzed_platforms: list[str],
    ) -> dict[str, Any]:
        total_views = sum(int(row.get("views") or 0) for row in social_rows)
        avg_engagement_rate = round(
            mean([row.get("engagement_rate", 0.0) for row in social_rows]),
            4,
        ) if social_rows else 0.0
        revenue_analyzed = round(sum(float(row.get("revenue") or 0.0) for row in sales_rows), 2)
        best_media = content_performance_summary.get("best_media_types", [])
        top_times = content_performance_summary.get("best_posting_times", [])

        if platform_comparison.get("available"):
            best_platform = platform_comparison["platforms"][0]["platform"]
        else:
            best_platform = content_performance_summary.get("best_platform_by_engagement")

        return {
            "total_posts": len(social_rows),
            "total_views": total_views,
            "avg_engagement_rate": avg_engagement_rate,
            "best_platform": best_platform,
            "top_content_type": best_media[0]["media_type"] if best_media else None,
            "top_posting_time": top_times[0]["time"] if top_times else None,
            "sales_included": bool(sales_rows),
            "revenue_analyzed": revenue_analyzed,
            "top_correlated_content": sales_impact_analysis.get("top_correlated_content", [])[:1],
            "selected_platforms": selected_platforms,
            "analyzed_platforms": analyzed_platforms,
        }

    def _missing_social_columns(
        self,
        social_rows: list[dict[str, Any]],
        analyzed_platforms: list[str],
    ) -> dict[str, list[str]]:
        missing: dict[str, list[str]] = {}
        required_fields = [
            "content_id",
            "content_url",
            "posted_at",
            "caption",
            "views",
            "likes",
            "comments",
            "shares",
            "engagement_rate",
            "author_username",
        ]

        for platform in analyzed_platforms:
            platform_rows = [row for row in social_rows if row["platform"] == platform]
            missing[platform] = [
                field
                for field in required_fields
                if not any(row.get(field) not in (None, "", []) for row in platform_rows)
            ]
        return missing

    def _top_patterns(self, stats: dict[str, list[float]]) -> list[dict[str, Any]]:
        ranked = []
        for key, values in stats.items():
            if not values:
                continue
            ranked.append(
                {
                    "label": key,
                    "avg_engagement_rate": round(mean(values), 4),
                    "posts": len(values),
                }
            )
        ranked.sort(key=lambda item: (item["avg_engagement_rate"], item["posts"]), reverse=True)
        return ranked[:5]

    def _content_summary_text(
        self,
        avg_engagement: dict[str, float],
        total_views: dict[str, int],
        best_platform_by_engagement: str | None,
        best_platform_by_views: str | None,
    ) -> str:
        if not avg_engagement:
            return "لا توجد بيانات محتوى كافية لبناء ملخص أداء."
        return (
            f"تشير البيانات إلى أن أعلى متوسط تفاعل كان في {best_platform_by_engagement} "
            f"بمتوسط {avg_engagement.get(best_platform_by_engagement, 0.0):.4f}، "
            f"بينما الأعلى من حيث المشاهدات كان في {best_platform_by_views} "
            f"بعدد {total_views.get(best_platform_by_views, 0)} مشاهدة."
        )

    def _group_by(
        self,
        rows: list[dict[str, Any]],
        key: str,
    ) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get(key))].append(row)
        return dict(grouped)

    def _length_bucket(self, caption: str) -> str:
        length = len((caption or "").strip())
        if length < 80:
            return "short"
        if length < 180:
            return "medium"
        return "long"

    def _parse_iso(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _platforms_arabic(self, platforms: list[str]) -> str:
        mapping = {
            "tiktok": "TikTok",
            "instagram": "Instagram",
            "x": "X",
        }
        labels = [mapping.get(platform, platform) for platform in platforms]
        if not labels:
            return "بدون منصات"
        if len(labels) == 1:
            return labels[0]
        return " و".join([", ".join(labels[:-1]), labels[-1]]) if len(labels) > 2 else " و".join(labels)
