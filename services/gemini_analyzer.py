"""
Gemini Analysis Layer — deep marketing and content analysis.
Runs in two phases:
  1. enrich_videos()      — before rule-based engine: classifies each video's content
  2. generate_deep_insights() — after rule-based engine: produces strategic marketing analysis
"""

import os
import json
import re
from typing import Any

from google import genai


class GeminiAnalyzer:

    def __init__(self):
        self._client = None

    @property
    def model(self):
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY غير موجود في ملف .env")
            self._client = genai.Client(api_key=api_key)
        return self._client

    # ── Phase 1: Video content enrichment ────────────────────────────────────

    def enrich_videos(self, videos: list[dict]) -> list[dict]:
        """Classify each video's caption and add content metadata fields."""
        if not videos:
            return videos

        captions = [
            {"index": i, "caption": str(v.get("caption") or v.get("text") or "")[:300]}
            for i, v in enumerate(videos)
        ]

        prompt = f"""أنتِ محللة محتوى تسويقي رقمي. حللي الكابشن التالية لفيديوهات سوشيال ميديا وصنّفيها.

البيانات:
{json.dumps(captions, ensure_ascii=False)}

لكل فيديو (حسب index)، حددي:
- content_type: نوع المحتوى — اختاري من: educational / promotional / entertainment / lifestyle / challenge / product_review / trending / behind_scenes
- topic: الموضوع الرئيسي بالعربي (مثل: "وصفات صحية"، "عناية بالبشرة"، "رياضة")
- hook_type: نوع الافتتاحية — اختاري من: question / story / shock / tip / product / trend
- sentiment: المشاعر العامة — اختاري من: positive / neutral / negative

أجيبي بـ JSON فقط بدون أي نص إضافي أو markdown:
{{"results": [{{"index": 0, "content_type": "...", "topic": "...", "hook_type": "...", "sentiment": "..."}}]}}"""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            data = self._parse_json(response.text)
            results_map = {r["index"]: r for r in data.get("results", [])}

            enriched = []
            for i, v in enumerate(videos):
                ev = dict(v)
                if i in results_map:
                    r = results_map[i]
                    ev["content_type"] = r.get("content_type", ev.get("content_type", ""))
                    ev["topic"] = r.get("topic", ev.get("topic"))
                    ev["hook_type"] = r.get("hook_type", ev.get("hook_type"))
                    ev["_sentiment"] = r.get("sentiment", "")
                enriched.append(ev)

            print(f"[Gemini] Enriched {len(enriched)} videos")
            return enriched

        except Exception as e:
            print(f"[Gemini] enrich_videos failed — skipping: {e}")
            return videos

    # ── Phase 2: Deep marketing insights ─────────────────────────────────────

    def generate_deep_insights(self, engine_output: dict, business_profile: dict) -> dict:
        """Produce strategic marketing insights based on engine analysis results."""

        try:
            root = engine_output.get("root_cause", {})
            insights_summary = "\n".join(
                f"- {ins.get('title', '')}: {ins.get('detail', '')}"
                for ins in engine_output.get("insights", [])
            )

            profile_lines = "\n".join([
                f"اسم النشاط: {business_profile.get('business_name', 'غير محدد')}",
                f"القطاع: {business_profile.get('sector') or business_profile.get('industry', 'غير محدد')}",
                f"المنتجات: {business_profile.get('products', 'غير محدد')}",
                f"الجمهور المستهدف: {business_profile.get('target_gender') or business_profile.get('target_audience', '')} / {business_profile.get('target_goal') or business_profile.get('goals', '')}",
                f"الأسلوب: {business_profile.get('tone') or business_profile.get('brand_tone', 'غير محدد')}",
            ])

            prompt = f"""أنتِ استراتيجية تسويق رقمي خبيرة متخصصة في السوق العربي.
بناءً على البيانات التالية، قدمي تحليلاً استراتيجياً عميقاً باللغة العربية.

── معلومات النشاط ──
{profile_lines}

── نتائج التحليل ──
{insights_summary}

أفضل منصة: {root.get('best_platform', 'غير محدد')}
متوسط التفاعل: {root.get('avg_engagement', 0)}
أفضل هاشتاقات: {', '.join(str(h) for h in root.get('best_hashtags', []))}
أفضل مواضيع: {', '.join(str(t) for t in root.get('best_topics', []))}
إجمالي المشاهدات: {root.get('total_views', 0)}
إجمالي المنشورات: {root.get('total_posts', 0)}

قدمي JSON يشمل:
- market_opportunities: قائمة بـ 3 فرص تسويقية غير مستغلة (نصوص قصيرة واضحة)
- content_gaps: قائمة بـ 3 ثغرات في المحتوى الحالي
- recommended_themes: قائمة بـ 5 مواضيع محتوى مقترحة للشهر القادم
- growth_strategy: استراتيجية نمو مختصرة (جملتان فقط)
- quick_wins: قائمة بـ 3 إجراءات سريعة قابلة للتطبيق هذا الأسبوع
- audience_insight: رؤية عن الجمهور المستهدف (جملة واحدة)

أجيبي بـ JSON فقط بدون markdown أو نص إضافي."""
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            result = self._parse_json(response.text)
            print("[Gemini] Deep insights generated successfully")
            return result
        except Exception as e:
            print(f"[Gemini] generate_deep_insights failed — skipping: {e}")
            return {}

    # ── JSON parser ───────────────────────────────────────────────────────────

    def _parse_json(self, text: str) -> dict | list:
        text = text.strip()
        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text.strip())
