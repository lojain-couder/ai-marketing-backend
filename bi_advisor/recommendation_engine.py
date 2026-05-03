from __future__ import annotations

from statistics import mean
from typing import Any


class MarketingRecommendationEngine:
    def generate(
        self,
        analysis: dict[str, Any],
        social_rows: list[dict[str, Any]],
        sales_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        performance = analysis["content_performance_summary"]
        comparison = analysis["platform_comparison"]
        patterns = analysis["content_patterns"]
        sales_impact = analysis["sales_impact_analysis"]

        best_platform = performance.get("best_platform_by_engagement")
        avg_by_platform = performance.get("average_engagement_rate_by_platform", {})
        if best_platform and avg_by_platform:
            recommendations.append(
                {
                    "title": f"مضاعفة الاستثمار في {best_platform}",
                    "root_cause_or_pattern": (
                        f"متوسط التفاعل في {best_platform} هو {avg_by_platform.get(best_platform, 0.0):.4f}، "
                        "وهو الأعلى بين المنصات المتاحة."
                    ),
                    "why_this_matters": "تشير البيانات إلى أن هذه المنصة تمنح أفضل استجابة حالياً، لذلك هي الأقرب لرفع الوصول والتفاعل بسرعة.",
                    "recommended_action": (
                        f"زيادة وتيرة النشر على {best_platform} خلال الأسبوع القادم مع إعادة استخدام أفضل صيغة محتوى "
                        "وأفضل وقت نشر ظهر في البيانات."
                    ),
                    "priority": "high",
                    "confidence": "high" if len(social_rows) >= 10 else "medium",
                    "evidence": [
                        f"أفضل منصة بالتفاعل: {best_platform}",
                        f"متوسط التفاعل: {avg_by_platform.get(best_platform, 0.0):.4f}",
                    ],
                }
            )

        best_media = performance.get("best_media_types", [])
        if best_media:
            media = best_media[0]
            recommendations.append(
                {
                    "title": f"تركيز الخطة القادمة على صيغة {media['media_type']}",
                    "root_cause_or_pattern": (
                        f"صيغة {media['media_type']} حققت متوسط تفاعل {media['avg_engagement_rate']:.4f} "
                        f"عبر {media['posts']} منشورات."
                    ),
                    "why_this_matters": "يبدو أن هذه الصيغة تحقق استجابة أعلى من باقي الصيغ، ما يجعلها أفضل نقطة انطلاق للخطة الأسبوعية.",
                    "recommended_action": (
                        f"رفع نسبة المحتوى من نوع {media['media_type']} في الأيام القادمة، مع الحفاظ على نفس أسلوب الخطاف والموضوع الأقوى."
                    ),
                    "priority": "high" if media["posts"] >= 2 else "medium",
                    "confidence": "medium",
                    "evidence": [
                        f"أفضل صيغة محتوى: {media['media_type']}",
                        f"متوسط التفاعل: {media['avg_engagement_rate']:.4f}",
                    ],
                }
            )

        best_hashtags = patterns.get("best_hashtags", [])
        if best_hashtags:
            hashtag = best_hashtags[0]
            recommendations.append(
                {
                    "title": f"إعادة استخدام الهاشتاق {hashtag['label']}",
                    "root_cause_or_pattern": (
                        f"الهاشتاق {hashtag['label']} ظهر في {hashtag['posts']} منشورات "
                        f"ومتوسط التفاعل المرتبط به {hashtag['avg_engagement_rate']:.4f}."
                    ),
                    "why_this_matters": "تشير البيانات إلى وجود نمط واضح في الهاشتاقات المرتبطة بالمحتوى الأعلى أداءً.",
                    "recommended_action": (
                        f"اختبار هذا الهاشتاق مع نفس الموضوع أو نفس نوع الخطاف في 2 إلى 3 منشورات جديدة بدل توزيعه بشكل عشوائي."
                    ),
                    "priority": "medium",
                    "confidence": "medium" if hashtag["posts"] >= 2 else "low",
                    "evidence": [
                        f"أفضل هاشتاق: {hashtag['label']}",
                        f"عدد المنشورات: {hashtag['posts']}",
                    ],
                }
            )

        if comparison.get("available") and len(recommendations) < 3:
            platforms = comparison.get("platforms", [])
            if len(platforms) >= 2:
                strongest = platforms[0]
                weakest = platforms[-1]
                recommendations.append(
                    {
                        "title": "إعادة توزيع الجهد بين المنصات",
                        "root_cause_or_pattern": (
                            f"{strongest['platform']} يتفوق بمتوسط تفاعل {strongest['avg_engagement_rate']:.4f} "
                            f"مقابل {weakest['avg_engagement_rate']:.4f} في {weakest['platform']}."
                        ),
                        "why_this_matters": "المقارنة بين المنصات تشير إلى أن توزيع الجهد الحالي لا يستفيد بالكامل من المنصة الأقوى.",
                        "recommended_action": (
                            f"زيادة عدد المنشورات أو الاختبارات على {strongest['platform']}، وتقليل التجارب غير المؤكدة على {weakest['platform']} "
                            "إلى أن تظهر صيغة أفضل."
                        ),
                        "priority": "medium",
                        "confidence": "medium",
                        "evidence": [
                            f"أفضل منصة: {strongest['platform']}",
                            f"أضعف منصة: {weakest['platform']}",
                        ],
                    }
                )

        if sales_rows and sales_impact.get("top_correlated_content") and len(recommendations) < 3:
            top_link = sales_impact["top_correlated_content"][0]
            recommendations.append(
                {
                    "title": "تكرار النمط المرتبط بالمبيعات بحذر",
                    "root_cause_or_pattern": (
                        f"أعلى محتوى مرتبط زمنياً أظهر قيمة {top_link['revenue_windows'].get('7d', 0.0):.2f} "
                        "خلال نافذة 7 أيام بعد النشر."
                    ),
                    "why_this_matters": "يبدو أن هذا النمط قد يساهم في دعم الإيراد، لكن البيانات لا تكفي للجزم بنسبة مباشرة بدون إشارة أقوى.",
                    "recommended_action": (
                        "إعادة إنتاج الفكرة أو الحملة نفسها مع استخدام اسم حملة موحد أو مصدر تتبع واضح لرفع جودة الربط بالمبيعات في الدورة القادمة."
                    ),
                    "priority": "medium",
                    "confidence": "medium",
                    "evidence": top_link.get("evidence", []),
                }
            )

        return recommendations[:3]
