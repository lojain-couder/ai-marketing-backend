from __future__ import annotations

from collections import defaultdict
from typing import Any


class WeeklyMarketingPlanGenerator:
    def generate(
        self,
        business_profile: dict[str, Any],
        selected_platforms: list[str],
        social_rows: list[dict[str, Any]],
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not social_rows:
            return []

        strongest_platforms = self._prioritized_platforms(selected_platforms, analysis)
        best_media_by_platform = self._best_media_by_platform(social_rows)
        best_time_by_platform = self._best_time_by_platform(social_rows)
        top_topic_by_platform = self._best_topic_by_platform(social_rows)
        top_cta_by_platform = self._best_cta_by_platform(social_rows)
        audience = business_profile.get("audience_type") or business_profile.get("target_audience") or "الجمهور المستهدف"
        business_name = business_profile.get("name") or "العلامة"

        day_labels = [
            "اليوم 1",
            "اليوم 2",
            "اليوم 3",
            "اليوم 4",
            "اليوم 5",
            "اليوم 6",
            "اليوم 7",
        ]

        plan: list[dict[str, Any]] = []
        for index, day_label in enumerate(day_labels):
            platform = strongest_platforms[index % len(strongest_platforms)]
            media_type = best_media_by_platform.get(platform, "video" if platform != "x" else "text")
            topic = top_topic_by_platform.get(platform) or "مشكلة متكررة لدى العميل"
            cta = top_cta_by_platform.get(platform) or "اطلب الآن"
            posting_time = best_time_by_platform.get(platform) or "19:00"
            hook = self._build_hook(platform, topic, audience)
            idea = self._build_idea(platform, topic, business_name)

            plan.append(
                {
                    "day": day_label,
                    "platform": platform,
                    "content_type": media_type,
                    "hook": hook,
                    "content_idea": idea,
                    "caption_or_script": self._build_caption(platform, topic, business_name, audience, cta),
                    "goal": self._goal_for_platform(platform),
                    "cta": cta,
                    "best_posting_time": posting_time,
                }
            )
        return plan

    def _prioritized_platforms(
        self,
        selected_platforms: list[str],
        analysis: dict[str, Any],
    ) -> list[str]:
        comparison = analysis.get("platform_comparison", {})
        if comparison.get("available"):
            return [row["platform"] for row in comparison.get("platforms", [])]

        best_platform = analysis.get("content_performance_summary", {}).get("best_platform_by_engagement")
        if best_platform:
            ordered = [best_platform] + [platform for platform in selected_platforms if platform != best_platform]
            return ordered
        return selected_platforms

    def _best_media_by_platform(self, social_rows: list[dict[str, Any]]) -> dict[str, str]:
        platform_media: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in social_rows:
            platform_media[row["platform"]][row.get("media_type") or "unknown"].append(row.get("engagement_rate", 0.0))
        result: dict[str, str] = {}
        for platform, media_map in platform_media.items():
            result[platform] = max(
                media_map.items(),
                key=lambda item: sum(item[1]) / len(item[1]),
            )[0]
        return result

    def _best_time_by_platform(self, social_rows: list[dict[str, Any]]) -> dict[str, str]:
        platform_hours: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in social_rows:
            posted_at = row.get("posted_at")
            if not posted_at:
                continue
            hour = str(posted_at)[11:16] if len(str(posted_at)) >= 16 else None
            if not hour:
                continue
            platform_hours[row["platform"]][hour].append(row.get("engagement_rate", 0.0))
        result: dict[str, str] = {}
        for platform, hour_map in platform_hours.items():
            result[platform] = max(
                hour_map.items(),
                key=lambda item: sum(item[1]) / len(item[1]),
            )[0]
        return result

    def _best_topic_by_platform(self, social_rows: list[dict[str, Any]]) -> dict[str, str]:
        platform_topics: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in social_rows:
            topic = row.get("topic")
            if topic:
                platform_topics[row["platform"]][str(topic)].append(row.get("engagement_rate", 0.0))
        result: dict[str, str] = {}
        for platform, topic_map in platform_topics.items():
            result[platform] = max(
                topic_map.items(),
                key=lambda item: sum(item[1]) / len(item[1]),
            )[0]
        return result

    def _best_cta_by_platform(self, social_rows: list[dict[str, Any]]) -> dict[str, str]:
        platform_ctas: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in social_rows:
            cta = row.get("cta")
            if cta:
                platform_ctas[row["platform"]][str(cta)].append(row.get("engagement_rate", 0.0))
        result: dict[str, str] = {}
        for platform, cta_map in platform_ctas.items():
            result[platform] = max(
                cta_map.items(),
                key=lambda item: sum(item[1]) / len(item[1]),
            )[0]
        return result

    def _build_hook(self, platform: str, topic: str, audience: str) -> str:
        if platform == "x":
            return f"ملاحظة سريعة: لماذا يهتم {audience} بموضوع {topic} الآن؟"
        return f"إذا كنت تستهدف {audience}، فهذه أسرع زاوية لفتح موضوع {topic}."

    def _build_idea(self, platform: str, topic: str, business_name: str) -> str:
        if platform == "instagram":
            return f"منشور مرئي يشرح كيف يتعامل {business_name} مع موضوع {topic} بشكل عملي."
        if platform == "tiktok":
            return f"فيديو قصير يبدأ بخطاف مباشر ثم يوضح مثالاً سريعاً حول {topic}."
        return f"سلسلة تغريدة قصيرة تطرح فكرة واضحة حول {topic} وتربطها بقيمة {business_name}."

    def _build_caption(
        self,
        platform: str,
        topic: str,
        business_name: str,
        audience: str,
        cta: str,
    ) -> str:
        if platform == "x":
            return (
                f"يبدو أن {topic} من أكثر المواضيع التي تهم {audience}. "
                f"في {business_name} نرى أن أفضل نتيجة تبدأ بخطوة واضحة وبسيطة. {cta}"
            )
        return (
            f"تشير البيانات إلى أن موضوع {topic} يحقق استجابة جيدة. "
            f"لهذا سنقدمه اليوم بطريقة مباشرة تناسب {audience} وتوضح كيف يساعد {business_name}. {cta}"
        )

    def _goal_for_platform(self, platform: str) -> str:
        if platform == "x":
            return "رفع التفاعل وبناء محادثة"
        return "رفع التفاعل والوصول"
