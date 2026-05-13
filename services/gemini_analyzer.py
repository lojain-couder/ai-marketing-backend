"""
Gemini Analysis Layer — deep marketing and content analysis.
Runs in multiple phases:
  1. enrich_videos()         — text classification (caption + transcript)
  2. _enrich_with_vision()   — visual analysis of top video thumbnails (Gemini Vision)
  3. generate_deep_insights() — strategic marketing analysis post-engine
  4. analyze_comments()       — comment voice analysis
  5. analyze_from_captions()  — estimated audience voice when no real comments
"""

import os
import json
import re

from google import genai
from google.genai import types as genai_types


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

    # ── Phase 1: Text-based video content enrichment ─────────────────────────

    def enrich_videos(self, videos: list[dict]) -> list[dict]:
        """
        Classify each video using caption + transcript (text),
        then enrich top videos further with Gemini Vision.
        """
        if not videos:
            return videos

        # Step 1: text classification
        videos = self._enrich_with_text(videos)
        # Step 2: visual classification for top 8 videos
        videos = self._enrich_with_vision(videos, max_videos=8)
        return videos

    def _enrich_with_text(self, videos: list[dict]) -> list[dict]:
        """Use caption + transcript to classify content_type, topic, hook_type, sentiment."""
        captions = []
        for i, v in enumerate(videos):
            caption_text = str(v.get("caption") or v.get("text") or "")[:300]
            entry: dict = {"index": i, "caption": caption_text}
            transcript = str(v.get("transcript", "")).strip()
            if transcript:
                entry["transcript"] = transcript[:400]
            captions.append(entry)

        prompt = f"""أنتِ محللة محتوى تسويقي رقمي. حللي البيانات التالية لفيديوهات سوشيال ميديا.
إذا توفّر النص المنطوق (transcript) استخدميه مع الكابشن لتحليل أدق.

البيانات:
{json.dumps(captions, ensure_ascii=False)}

لكل فيديو (حسب index)، حددي:
- content_type: نوع المحتوى — اختاري من: educational / promotional / entertainment / lifestyle / challenge / product_review / trending / behind_scenes / tutorial / unboxing
- topic: الموضوع الرئيسي بالعربي (مثل: "وصفات صحية"، "عناية بالبشرة"، "رياضة")
- hook_type: نوع الافتتاحية — اختاري من: question / story / shock / tip / product / trend
- sentiment: المشاعر العامة — اختاري من: positive / neutral / negative
- has_cta: هل يوجد دعوة للشراء أو التواصل في الكابشن أو النص؟ (true/false)
- mentions_price: هل يذكر سعراً أو عرضاً أو خصماً؟ (true/false)

أجيبي بـ JSON فقط بدون أي نص إضافي أو markdown:
{{"results": [{{"index": 0, "content_type": "...", "topic": "...", "hook_type": "...", "sentiment": "...", "has_cta": false, "mentions_price": false}}]}}"""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            data = self._parse_json(response.text)
            results_map = {r["index"]: r for r in data.get("results", [])}

            enriched = []
            for i, v in enumerate(videos):
                ev = dict(v)
                if i in results_map:
                    r = results_map[i]
                    ev["content_type"]   = r.get("content_type", ev.get("content_type", ""))
                    ev["topic"]          = r.get("topic", ev.get("topic"))
                    ev["hook_type"]      = r.get("hook_type", ev.get("hook_type"))
                    ev["_sentiment"]     = r.get("sentiment", "")
                    ev["has_cta"]        = r.get("has_cta", False)
                    ev["mentions_price"] = r.get("mentions_price", False)
                enriched.append(ev)

            print(f"[Gemini] Text enrichment done — {len(enriched)} videos")
            return enriched

        except Exception as e:
            print(f"[Gemini] _enrich_with_text failed — skipping: {e}")
            return videos

    # ── Phase 1b: Vision enrichment (Gemini Vision) ───────────────────────────

    def _enrich_with_vision(self, videos: list[dict], max_videos: int = 8) -> list[dict]:
        """
        Download thumbnails for the top-performing videos and classify them visually.
        Adds: visual_type, has_product, has_face, visual_emotion, scene, hook_visual.
        Falls back gracefully — if thumbnail download fails, the video is unchanged.
        """
        from services.thumbnail_downloader import download_thumbnail

        candidates = sorted(
            [(i, v) for i, v in enumerate(videos) if v.get("url")],
            key=lambda x: float(x[1].get("engagement_rate") or 0),
            reverse=True,
        )[:max_videos]

        if not candidates:
            return videos

        print(f"[GeminiVision] Analyzing thumbnails for {len(candidates)} videos")

        for i, v in candidates:
            url = v.get("url", "")
            try:
                result = download_thumbnail(url)
                if not result:
                    continue
                image_bytes, _ = result

                caption_hint = str(v.get("caption", ""))[:200]
                transcript_hint = str(v.get("transcript", ""))[:150]

                context = f"الكابشن: {caption_hint}"
                if transcript_hint:
                    context += f"\nالنص المنطوق: {transcript_hint}"

                response = self.model.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        f"""أنتِ محللة محتوى بصري متخصصة في سوشيال ميديا.
حللي صورة الفيديو (ثامبنيل) هذه لحساب تجاري.

{context}

أجيبي بـ JSON فقط — لا نص إضافي:
{{
  "visual_type": "أحد: talking_head / product_demo / lifestyle / text_overlay / unboxing / tutorial / behind_scenes / aesthetic / food / fitness",
  "has_product": true_أو_false,
  "has_face": true_أو_false,
  "visual_emotion": "أحد: energetic / calm / professional / fun / emotional / aspirational",
  "scene": "وصف قصير للمشهد بالعربي — جملة واحدة",
  "hook_visual": "ما الذي يجذب النظر أولاً في الصورة؟ — جملة قصيرة"
}}"""
                    ],
                )

                vis = self._parse_json(response.text)
                if isinstance(vis, dict):
                    videos[i]["visual_type"]    = vis.get("visual_type", "")
                    videos[i]["has_product"]     = vis.get("has_product", False)
                    videos[i]["has_face"]        = vis.get("has_face", False)
                    videos[i]["visual_emotion"]  = vis.get("visual_emotion", "")
                    videos[i]["scene"]           = vis.get("scene", "")
                    videos[i]["hook_visual"]     = vis.get("hook_visual", "")
                    print(f"[GeminiVision] ✓ {url[:55]} → {vis.get('visual_type')}")

            except Exception as e:
                print(f"[GeminiVision] Skipped {url[:55]}: {e}")

        vision_count = sum(1 for v in videos if v.get("visual_type"))
        print(f"[GeminiVision] Done — {vision_count} videos with visual data")
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

            # Include content type sales data if available
            ct_impact = engine_output.get("content_type_impact", {})
            ct_lines = ""
            if ct_impact.get("available"):
                top_types = ct_impact.get("content_type_impact", [])[:3]
                ct_lines = "\n── أنواع المحتوى حسب الأثر على المبيعات ──\n"
                for ct in top_types:
                    ct_lines += f"- {ct['content_type']}: متوسط إيراد 7 أيام = {ct['avg_revenue_7d']}, تفاعل = {ct['avg_engagement']}\n"

            # Include comment voice if available
            comment_voice = engine_output.get("comment_voice", {})
            comment_lines = ""
            if comment_voice.get("frequent_questions"):
                qs = comment_voice["frequent_questions"][:3]
                comment_lines = f"\n── أكثر الأسئلة من الجمهور ──\n" + "\n".join(f"- {q}" for q in qs)

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
{ct_lines}{comment_lines}

قدمي JSON يشمل:
- market_opportunities: قائمة بـ 3 فرص تسويقية غير مستغلة (نصوص قصيرة واضحة)
- content_gaps: قائمة بـ 3 ثغرات في المحتوى الحالي
- recommended_themes: قائمة بـ 5 مواضيع محتوى مقترحة للشهر القادم
- growth_strategy: استراتيجية نمو مختصرة (جملتان فقط)
- quick_wins: قائمة بـ 3 إجراءات سريعة قابلة للتطبيق هذا الأسبوع
- audience_insight: رؤية عن الجمهور المستهدف (جملة واحدة)
- top_sales_content_type: نوع المحتوى الأنسب للمبيعات بناءً على البيانات (جملة)

أجيبي بـ JSON فقط بدون markdown أو نص إضافي."""

            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            result = self._parse_json(response.text)
            print("[Gemini] Deep insights generated successfully")
            return result
        except Exception as e:
            print(f"[Gemini] generate_deep_insights failed — skipping: {e}")
            return {}

    # ── Phase 3: Comment voice analysis ──────────────────────────────────────

    def analyze_comments(self, comments: list[dict], business_profile: dict) -> dict:
        """Extract audience voice: questions, product requests, complaints, content ideas."""
        texts = [c.get("text", "") for c in comments if c.get("text", "").strip()]
        if not texts:
            return {}

        sample = texts[:120]
        product = business_profile.get("products") or business_profile.get("product") or "المنتج"
        sector  = business_profile.get("sector") or business_profile.get("industry") or "النشاط التجاري"

        prompt = f"""أنتِ محللة تسويقية متخصصة في السوق العربي. حللي هذه التعليقات من جمهور متجر {sector} ({product}).

التعليقات ({len(sample)} تعليق):
{json.dumps(sample, ensure_ascii=False, indent=None)}

استخرجي بالضبط:
- frequent_questions: أكثر 5 أسئلة يطرحها الجمهور (مثل "كيف أطلب؟", "هل في توصيل؟")
- product_requests: أكثر 5 طلبات أو اقتراحات لمنتجات/ألوان/مقاسات
- complaints: أكثر 3 شكاوى أو ملاحظات سلبية (إن وجدت)
- purchase_signals: 3 تعليقات تدل على نية شراء (مثل "كم السعر؟"، "أبي أطلب")
- content_suggestions: 5 أفكار محتوى مباشرة تجيب على هذه الأسئلة والطلبات (جملة كاملة لكل فكرة)
- sentiment_breakdown: نسب المشاعر كأرقام مئوية {{"positive": N, "neutral": N, "negative": N}}
- top_comments: أفضل 3 تعليقات تعبر عن صوت الجمهور (نصوص كاملة)

أجيبي بـ JSON فقط بدون markdown أو نص إضافي."""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            result = self._parse_json(response.text)
            print(f"[Gemini] Comment analysis done — {len(texts)} comments")
            return result
        except Exception as e:
            print(f"[Gemini] analyze_comments failed: {e}")
            return {}

    # ── Phase 3b: Product-aware comment analysis ─────────────────────────────

    def analyze_product_comments(
        self,
        comments: list[dict],
        products: list[dict],
        business_profile: dict,
    ) -> list[dict]:
        """
        For each product in the list, extract what the audience is saying about it
        from the comments. Returns per-product voice data with improvement tips.
        """
        texts = [c.get("text", "") for c in comments if c.get("text", "").strip()]
        if not texts or not products:
            return []

        product_names = [p["product_name"] for p in products[:10]]
        sample = texts[:150]
        sector  = business_profile.get("sector") or business_profile.get("industry") or "التجارة"
        tone    = business_profile.get("tone") or business_profile.get("brand_tone") or "احترافي"

        prompt = f"""أنتِ محللة تسويقية متخصصة في السوق العربي، تعملين في قطاع {sector} بأسلوب {tone}.
لديكِ قائمة منتجات وتعليقات من جمهور حساب تجاري. حللي ما يقوله الجمهور عن كل منتج.

المنتجات: {', '.join(product_names)}

التعليقات ({len(sample)} تعليق):
{json.dumps(sample, ensure_ascii=False, indent=None)}

لكل منتج مذكور في التعليقات، أخرجي:
- product_name: اسم المنتج
- mention_count: عدد التعليقات التي تذكره (تقريباً)
- questions: أكثر 3 أسئلة يطرحها الجمهور عن هذا المنتج تحديداً
- complaints: أكثر 2 شكوى أو ملاحظة سلبية عن هذا المنتج
- purchase_signals: تعليقات تدل على نية الشراء (مثل "أبي أطلب"، "كم السعر؟")
- praises: أكثر شيء يمدحونه في هذا المنتج
- seller_tip: نصيحة واحدة عملية للبائع بناءً على هذه التعليقات (جملتان)

أجيبي بـ JSON فقط:
{{"product_voices": [{{"product_name": "...", "mention_count": 0, "questions": [], "complaints": [], "purchase_signals": [], "praises": [], "seller_tip": "..."}}]}}"""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            data = self._parse_json(response.text)
            voices = data.get("product_voices", [])
            print(f"[Gemini] Product comment analysis — {len(voices)} products found in comments")
            return voices
        except Exception as e:
            print(f"[Gemini] analyze_product_comments failed: {e}")
            return []

    # ── Phase 3c: Per-product content strategy ────────────────────────────────

    def generate_product_content_strategy(
        self,
        product_stats: list[dict],
        business_profile: dict,
        product_voices: list[dict] | None = None,
    ) -> list[dict]:
        """
        For each product (top 6 by revenue), generate:
        - content ideas to drive sales for this specific product
        - actionable seller improvement tips
        - recommended content formats and hooks
        """
        if not product_stats:
            return []

        top_products = product_stats[:6]
        voice_map = {v["product_name"]: v for v in (product_voices or [])}

        sector = business_profile.get("sector") or business_profile.get("industry") or "التجارة"
        tone   = business_profile.get("tone") or business_profile.get("brand_tone") or "احترافي"

        products_data = []
        for p in top_products:
            name = p["product_name"]
            entry = {
                "name": name,
                "revenue": p.get("revenue", 0),
                "orders": p.get("orders", 0),
                "avg_order_value": p.get("avg_order_value", 0),
                "featuring_videos": p.get("featuring_video_count", 0),
                "engagement_lift": p.get("engagement_lift_pct"),
                "has_content_already": p.get("has_content", False),
            }
            if name in voice_map:
                v = voice_map[name]
                entry["audience_questions"]    = v.get("questions", [])[:2]
                entry["audience_complaints"]   = v.get("complaints", [])[:2]
                entry["purchase_signals_count"] = len(v.get("purchase_signals", []))
                entry["praises"]               = v.get("praises", [])[:2]
            products_data.append(entry)

        prompt = f"""أنتِ استراتيجية محتوى تسويقي خبيرة في السوق الخليجي.
لديكِ بيانات دقيقة عن منتجات متجر {sector} بأسلوب {tone}.

البيانات:
{json.dumps(products_data, ensure_ascii=False, indent=2)}

لكل منتج، قدمي:
- product_name: اسم المنتج
- content_ideas: قائمة بـ 3 أفكار محتوى جاهزة للتصوير (جمل واضحة وقابلة للتنفيذ مباشرة)
- best_content_type: نوع المحتوى الأنسب لهذا المنتج (مثل: tutorial / unboxing / before_after / قصة عميل)
- hook_suggestion: جملة افتتاحية قوية لفيديو عن هذا المنتج (بالعربي، نبرة طبيعية)
- seller_improvements: قائمة بـ 3 نصائح عملية للبائع لتحسين مبيعات هذا المنتج (بناءً على البيانات)
- priority: أولوية التركيز — اختاري: high / medium / low (بناءً على الإيراد ووجود إشارات الشراء)
- why_priority: سبب الأولوية بجملة واحدة

أجيبي بـ JSON فقط — لا نص خارج الـ JSON:
{{"product_strategies": [{{"product_name": "...", "content_ideas": [], "best_content_type": "...", "hook_suggestion": "...", "seller_improvements": [], "priority": "high", "why_priority": "..."}}]}}"""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            data = self._parse_json(response.text)
            strategies = data.get("product_strategies", [])
            print(f"[Gemini] Product strategies generated — {len(strategies)} products")
            return strategies
        except Exception as e:
            print(f"[Gemini] generate_product_content_strategy failed: {e}")
            return []

    # ── Phase 5: Competitor narrative insights ────────────────────────────────

    def generate_competitor_insights(
        self,
        comparison: dict,
        business_profile: dict,
    ) -> dict:
        """
        Takes the structured comparison from competitor_analyzer and produces
        Arabic narrative insights + specific action recommendations.
        """
        if not comparison.get("available"):
            return {}

        benchmark = comparison.get("benchmark", {})
        gaps = comparison.get("gaps", [])[:5]
        unused_hashtags = comparison.get("unused_competitor_hashtags", [])[:8]
        comp_stats = comparison.get("competitor_stats", [])

        sector = business_profile.get("sector") or business_profile.get("industry") or "التجارة"
        tone   = business_profile.get("tone") or "احترافي"

        comp_summary = "\n".join(
            f"- @{c['username']}: تفاعل متوسط {c['avg_engagement']:.4f}, "
            f"أنواع المحتوى الرئيسية: {list(c.get('content_type_dist', {}).keys())[:3]}"
            for c in comp_stats
        )

        gaps_text = "\n".join(
            f"- {g.get('description', '')}: {g.get('action', '')}"
            for g in gaps
        )

        prompt = f"""أنتِ استراتيجية تسويق رقمي خبيرة في {sector}.
حللي مقارنة أداء الحساب مع المنافسين وأعطي توصيات استراتيجية باللغة العربية.

── بيانات المقارنة ──
تفاعلك: {benchmark.get('your_avg_engagement', 0):.4f}
متوسط المنافسين: {benchmark.get('competitor_avg_engagement', 0):.4f}
أفضل منافس: @{benchmark.get('best_competitor_username', '?')} بتفاعل {benchmark.get('best_competitor_engagement', 0):.4f}

── أداء المنافسين ──
{comp_summary}

── الفجوات الرئيسية ──
{gaps_text}

── هاشتاقات لم تستخدمها بعد ──
{', '.join(unused_hashtags)}

أجيبي بـ JSON:
{{
  "competitive_position": "تقييم موقعك التنافسي الآن — جملتان",
  "top_competitor_lessons": ["درس 1 من المنافسين", "درس 2", "درس 3"],
  "immediate_actions": ["إجراء فوري 1", "إجراء فوري 2", "إجراء فوري 3"],
  "hashtag_strategy": "استراتيجية الهاشتاقات المقترحة — جملتان",
  "content_type_advice": "نصيحة عن نوع المحتوى بناءً على فجوات المنافسين — جملتان"
}}

أجيبي بـ JSON فقط."""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            result = self._parse_json(response.text)
            print("[Gemini] Competitor insights generated")
            return result
        except Exception as e:
            print(f"[Gemini] generate_competitor_insights failed: {e}")
            return {}

    # ── Phase 6: Audience persona clustering ─────────────────────────────────

    def cluster_audience_personas(
        self,
        comments: list[dict],
        business_profile: dict,
    ) -> list[dict]:
        """
        Clusters the audience into 2-3 distinct personas based on comment patterns.
        Each persona includes: name, %, what they care about, how to target them.
        """
        texts = [c.get("text", "") for c in comments if c.get("text", "").strip()]
        if len(texts) < 10:
            return []

        sample = texts[:150]
        sector  = business_profile.get("sector") or business_profile.get("industry") or "التجارة"
        product = business_profile.get("products") or "المنتج"

        prompt = f"""أنتِ خبيرة تسويق في السوق الخليجي. لديكِ تعليقات من جمهور متجر {sector} ({product}).
حللي التعليقات وصنّفي الجمهور في 2-3 شخصيات (personas) مختلفة.

التعليقات:
{json.dumps(sample, ensure_ascii=False, indent=None)}

لكل شخصية، حددي:
- persona_name: اسم وصفي للشخصية (مثل: "المقارنة بالسعر"، "طالب الجودة"، "مشتري الهدايا")
- percentage: نسبة تقريبية من الجمهور (الإجمالي 100)
- description: وصف قصير لهذه الشخصية (جملتان)
- what_they_want: أهم 3 أشياء يبحث عنها هذا الشخص
- how_to_target: كيف تستهدف هذه الشخصية بالمحتوى — جملتان عملية
- example_comment: مثال على تعليق نموذجي لهذه الشخصية

أجيبي بـ JSON فقط:
{{"personas": [{{"persona_name": "...", "percentage": 40, "description": "...", "what_they_want": [], "how_to_target": "...", "example_comment": "..."}}]}}"""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            data = self._parse_json(response.text)
            personas = data.get("personas", [])
            print(f"[Gemini] Persona clustering — {len(personas)} personas identified")
            return personas
        except Exception as e:
            print(f"[Gemini] cluster_audience_personas failed: {e}")
            return []

    # ── Phase 7: Trending hashtag suggestions ────────────────────────────────

    def suggest_trending_hashtags(
        self,
        business_profile: dict,
        account_hashtags: list[str],
        competitor_hashtags: list[str],
    ) -> list[str]:
        """
        Suggests trending hashtags for the niche that the account isn't using.
        Uses Gemini's knowledge of the Arabic/Gulf social media landscape.
        """
        sector  = business_profile.get("sector") or business_profile.get("industry") or "التجارة"
        product = business_profile.get("products") or "المنتج"
        country = business_profile.get("country") or business_profile.get("target_market") or "السعودية والخليج"

        used_sample = account_hashtags[:15]
        competitor_sample = competitor_hashtags[:15]

        prompt = f"""أنتِ خبيرة سوشيال ميديا في السوق الخليجي.
اقترحي هاشتاقات رائجة ومناسبة لـ {sector} ({product}) في {country}.

الهاشتاقات المستخدمة حالياً:
{json.dumps(used_sample, ensure_ascii=False)}

هاشتاقات المنافسين (للاستلهام):
{json.dumps(competitor_sample, ensure_ascii=False)}

اقترحي 15 هاشتاق:
- متنوعة: بعضها عام (حجم كبير) وبعضها متخصص (niche)
- مناسبة للسوق الخليجي والعربي
- لم تُستخدم بالفعل في القائمة المعطاة
- مزيج من العربية والإنجليزية

أجيبي بـ JSON فقط:
{{"suggested_hashtags": ["#هاشتاق1", "#hashtag2", ...]}}"""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            data = self._parse_json(response.text)
            tags = data.get("suggested_hashtags", [])
            print(f"[Gemini] Hashtag suggestions — {len(tags)} tags")
            return tags
        except Exception as e:
            print(f"[Gemini] suggest_trending_hashtags failed: {e}")
            return []

    # ── Phase 4: Caption-based audience estimation (fallback) ────────────────

    def analyze_from_captions(self, captions: list[str], business_profile: dict) -> dict:
        """Estimate likely audience questions/requests from video captions when real comments unavailable."""
        sample = [c[:200] for c in captions if c.strip()][:20]
        if not sample:
            return {}

        product = business_profile.get("products") or business_profile.get("product") or "المنتج"
        sector  = business_profile.get("sector") or business_profile.get("industry") or "النشاط التجاري"

        prompt = f"""أنتِ خبيرة تسويق رقمي. بناءً على كابشن الفيديوهات التالية لمتجر {sector} ({product})، توقّعي:
- ماذا يسأل الجمهور في التعليقات؟
- ماذا يطلبون من المنتجات؟
- ما المشاعر الغالبة؟

كابشن الفيديوهات:
{json.dumps(sample, ensure_ascii=False)}

أجيبي بـ JSON بنفس الهيكل:
- frequent_questions: 5 أسئلة متوقعة من الجمهور
- product_requests: 5 طلبات/اقتراحات متوقعة
- complaints: قائمة فارغة []
- purchase_signals: []
- content_suggestions: 5 أفكار محتوى بناءً على ما يحتاجه هذا الجمهور
- sentiment_breakdown: {{"positive": 75, "neutral": 20, "negative": 5}}
- top_comments: []
- is_estimated: true

أجيبي بـ JSON فقط."""

        try:
            response = self.model.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            result = self._parse_json(response.text)
            result["is_estimated"] = True
            print("[Gemini] Caption-based audience estimation done")
            return result
        except Exception as e:
            print(f"[Gemini] analyze_from_captions failed: {e}")
            return {}

    # ── JSON parser ───────────────────────────────────────────────────────────

    def _parse_json(self, text: str) -> dict | list:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text.strip())
