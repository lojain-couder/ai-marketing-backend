from __future__ import annotations

from collections import defaultdict
from typing import Any


# 7-day content framework — each day has a different purpose and hook style
_DAY_THEMES = [
    {
        "purpose": "educational",
        "goal": "تثقيف الجمهور وبناء الثقة",
        "hook_style": "question",
        "cta_default": "احفظ المنشور للرجوع إليه",
    },
    {
        "purpose": "social_proof",
        "goal": "بناء الثقة وإثبات النتائج",
        "hook_style": "story",
        "cta_default": "شاركنا تجربتك",
    },
    {
        "purpose": "promotional",
        "goal": "زيادة المبيعات المباشرة",
        "hook_style": "product",
        "cta_default": "اطلب الآن",
    },
    {
        "purpose": "entertainment",
        "goal": "توسيع الوصول والانتشار",
        "hook_style": "trend",
        "cta_default": "شاركه مع أصدقائك",
    },
    {
        "purpose": "problem_solution",
        "goal": "استقطاب عملاء جدد",
        "hook_style": "shock",
        "cta_default": "احصل على الحل الآن",
    },
    {
        "purpose": "engagement",
        "goal": "تعزيز التفاعل المجتمعي",
        "hook_style": "question",
        "cta_default": "قولنا رأيك في التعليقات",
    },
    {
        "purpose": "value",
        "goal": "تقديم قيمة وتحفيز الشراء",
        "hook_style": "tip",
        "cta_default": "جرب هذا اليوم",
    },
]

_HOOK_TEMPLATES = {
    "question": [
        "هل تعرف سبب {problem}؟",
        "ليش {audience} يعانون من {problem}؟",
        "ما السر وراء {topic}؟",
        "سؤال سريع: كيف تتعامل مع {topic}؟",
    ],
    "story": [
        "عميلتنا كانت تعاني من {problem} — شوفي ماذا حدث بعدين",
        "قبل وبعد: كيف تغير {topic} لدى عملائنا",
        "قصة حقيقية عن {topic} تستحق المشاركة",
    ],
    "shock": [
        "خطأ شائع يرتكبه ٩٠٪ في {topic}!",
        "توقف! هذا ما تفعله خطأ في {topic}",
        "الحقيقة التي لا يقولها أحد عن {topic}",
    ],
    "tip": [
        "نصيحة سريعة تغير نتيجتك في {topic}",
        "٣ خطوات فقط لتحسين {topic}",
        "الطريقة الأذكى للتعامل مع {topic}",
    ],
    "product": [
        "هذا هو الفرق الذي يصنعه {product}",
        "لماذا {product} هو الخيار الأول في {topic}؟",
        "شوفي كيف يحل {product} مشكلة {problem}",
    ],
    "trend": [
        "الكل يتحدث عن {topic} — وهذا السبب",
        "ترند {topic} وصل — أنتِ جاهزة؟",
        "لماذا أصبح {topic} موضة الموسم؟",
    ],
}


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
        best_time_by_platform = self._best_time_by_platform(social_rows)
        content_patterns = analysis.get("content_patterns", {})

        # Extract varied topics from data (up to 7)
        topics = self._extract_topics(social_rows, content_patterns, business_profile)
        # Extract real hashtag groups from data
        hashtag_groups = self._extract_hashtag_groups(content_patterns)

        audience = (
            business_profile.get("target_audience")
            or business_profile.get("audience_type")
            or "جمهورك"
        )
        business_name = (
            business_profile.get("business_name")
            or business_profile.get("name")
            or "العلامة"
        )
        product = business_profile.get("products") or business_profile.get("product") or "منتجك"

        plan: list[dict[str, Any]] = []
        for index, theme in enumerate(_DAY_THEMES):
            platform = strongest_platforms[index % len(strongest_platforms)]
            topic = topics[index % len(topics)]
            hashtags = hashtag_groups[index % len(hashtag_groups)] if hashtag_groups else []
            posting_time = best_time_by_platform.get(platform) or "19:00"

            hook = self._build_hook(theme, topic, audience, product)
            idea = self._build_idea(theme, topic, business_name, product)
            caption = self._build_caption(theme, platform, topic, business_name, audience, product, theme["cta_default"])

            plan.append({
                "day": f"اليوم {index + 1}",
                "platform": platform,
                "content_type": self._content_type_for_purpose(theme["purpose"], platform),
                "hook": hook,
                "content_idea": idea,
                "caption_or_script": caption,
                "goal": theme["goal"],
                "cta": theme["cta_default"],
                "best_posting_time": posting_time,
                "hashtags": hashtags,
                "theme": theme["purpose"],
            })

        return plan

    # ── Data extraction ───────────────────────────────────────────────────────

    # Platform and generic words to skip as topics
    _SKIP_TOPICS = {
        "tiktok", "تيك_توك", "تيك توك", "tiktoker",
        "instagram", "انستقرام", "انستا",
        "youtube", "يوتيوب",
        "fyp", "foryou", "foryoupage",
        "viral", "trending", "explore",
        "ترند", "اكسبلور", "اكسبلر",
    }

    def _extract_topics(
        self,
        social_rows: list[dict[str, Any]],
        content_patterns: dict[str, Any],
        business_profile: dict[str, Any],
    ) -> list[str]:
        topics: list[str] = []

        def is_valid(label: str) -> bool:
            clean = label.lstrip("#").lower().replace("_", " ").strip()
            if len(clean) < 3:
                return False
            return clean not in self._SKIP_TOPICS

        # 1. Topics from Gemini enrichment (semantic, best quality)
        repeated = content_patterns.get("repeated_topics", [])
        for t in repeated[:5]:
            label = t.get("label") or t.get("topic") or ""
            if label and is_valid(label) and label not in topics:
                topics.append(label)

        # 2. Meaningful hashtags as topic proxies (filtered)
        for h in content_patterns.get("best_hashtags", [])[:8]:
            label = (h.get("label") or "").lstrip("#").replace("_", " ").strip()
            if label and is_valid(label) and label not in topics:
                topics.append(label)

        # 3. Topics from business profile (sector, products)
        if len(topics) < 3:
            for field in ("products", "industry", "sector"):
                value = (business_profile.get(field) or "").split("،")[0].strip()
                if value and value not in topics:
                    topics.append(value)

        # 4. Last resort generic topics matching the sector
        if not topics:
            topics = ["نصيحة يومية", "وراء الكواليس", "عرض خاص", "قصة نجاح", "روتين سريع"]

        # Pad to 7 by cycling
        base = topics[:]
        while len(topics) < 7:
            topics.append(base[len(topics) % len(base)])

        return topics[:7]

    def _extract_hashtag_groups(self, content_patterns: dict[str, Any]) -> list[list[str]]:
        all_hashtags = [
            h.get("label") or h.get("tag") or ""
            for h in content_patterns.get("best_hashtags", [])
            if h.get("label") or h.get("tag")
        ]
        if not all_hashtags:
            return []
        # Group into sets of 3-5 per day, rotating
        groups = []
        for i in range(7):
            group = []
            for j in range(4):
                idx = (i + j) % len(all_hashtags)
                tag = all_hashtags[idx]
                if tag and tag not in group:
                    group.append(tag)
            groups.append(group)
        return groups

    # ── Content builders ──────────────────────────────────────────────────────

    def _build_hook(
        self,
        theme: dict[str, Any],
        topic: str,
        audience: str,
        product: str,
    ) -> str:
        style = theme["hook_style"]
        templates = _HOOK_TEMPLATES.get(style, _HOOK_TEMPLATES["question"])
        # Pick template based on topic length for variety
        tpl = templates[len(topic) % len(templates)]
        problem = topic  # topic often describes a pain point
        return tpl.format(topic=topic, audience=audience, product=product, problem=problem)

    def _build_idea(
        self,
        theme: dict[str, Any],
        topic: str,
        business_name: str,
        product: str,
    ) -> str:
        purpose = theme["purpose"]
        base = {
            "educational": f"فيديو تعليمي يشرح {topic} بطريقة بسيطة خطوة بخطوة.",
            "social_proof": f"قصة عميل حقيقي يتحدث عن تجربته مع {product} في موضوع {topic}.",
            "promotional": f"عرض {product} وكيف يحل مشكلة {topic} بشكل مباشر.",
            "entertainment": f"محتوى خفيف وممتع يربط بين {topic} وحياة {business_name} اليومية.",
            "problem_solution": f"اعرض المشكلة الشائعة في {topic} ثم قدم الحل الذي يوفره {product}.",
            "engagement": f"سؤال مفتوح أو استطلاع رأي حول {topic} يحفز الجمهور على التعليق.",
            "value": f"نصيحة سريعة وقابلة للتطبيق حول {topic} تُظهر خبرة {business_name}.",
        }
        return base.get(purpose, f"محتوى حول {topic}.")

    def _build_caption(
        self,
        theme: dict[str, Any],
        platform: str,
        topic: str,
        business_name: str,
        audience: str,
        product: str,
        cta: str,
    ) -> str:
        purpose = theme["purpose"]
        captions = {
            "educational": (
                f"كل ما تحتاج معرفته عن {topic} في ثوانٍ 👇\n\n"
                f"في {business_name} نؤمن أن المعرفة تصنع الفرق.\n\n{cta} ⬇️"
            ),
            "social_proof": (
                f"رأي عملائنا هو أفضل ما يمكن أن نقوله عن {topic} ❤️\n\n"
                f"انضم لآلاف {audience} الذين اختاروا {business_name}.\n\n{cta}"
            ),
            "promotional": (
                f"✨ {product} — الحل الأمثل لـ {topic}\n\n"
                f"خصص لنفسك التجربة التي تستحقها.\n\n👇 {cta}"
            ),
            "entertainment": (
                f"لأن {topic} يستاهل لحظة من الفرح 😄\n\n"
                f"{business_name} دايماً جنبك.\n\n{cta} ❤️"
            ),
            "problem_solution": (
                f"إذا كنت تعاني من {topic}، هذا المنشور لك 👇\n\n"
                f"{product} صُمِّم خصيصاً لحل هذه المشكلة.\n\n{cta}"
            ),
            "engagement": (
                f"سؤال لـ {audience}: ما رأيك في {topic}؟ 🤔\n\n"
                f"شاركنا تجربتك في التعليقات — {business_name} يقرأ كل تعليق.\n\n{cta}"
            ),
            "value": (
                f"نصيحة من {business_name} لتحسين {topic} 💡\n\n"
                f"طبّقها اليوم وأخبرنا بالنتيجة!\n\n{cta}"
            ),
        }
        return captions.get(purpose, f"محتوى حول {topic} من {business_name}. {cta}")

    def _content_type_for_purpose(self, purpose: str, platform: str) -> str:
        mapping = {
            "educational": "تعليمي",
            "social_proof": "قصة نجاح",
            "promotional": "إعلان",
            "entertainment": "ترفيهي",
            "problem_solution": "تعليمي",
            "engagement": "تفاعلي",
            "value": "تعليمي",
        }
        return mapping.get(purpose, "فيديو")

    # ── Platform utilities ────────────────────────────────────────────────────

    def _prioritized_platforms(
        self,
        selected_platforms: list[str],
        analysis: dict[str, Any],
    ) -> list[str]:
        comparison = analysis.get("platform_comparison", {})
        if comparison.get("available"):
            return [row["platform"] for row in comparison.get("platforms", [])]
        best_platform = analysis.get("content_performance_summary", {}).get(
            "best_platform_by_engagement"
        )
        if best_platform:
            return [best_platform] + [p for p in selected_platforms if p != best_platform]
        return selected_platforms

    def _best_time_by_platform(self, social_rows: list[dict[str, Any]]) -> dict[str, str]:
        platform_hours: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
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
