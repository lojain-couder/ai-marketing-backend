"""
Groq Writing Layer — language enrichment ONLY.
Groq must NOT invent metrics, claims, or recommendations.
Groq must NOT override engine decisions.
Groq only rewrites, expands, and adapts tone.
"""

import json
import os
from typing import Any

from groq import Groq

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """
أنت كاتب محتوى تسويقي محترف. مهمتك الوحيدة هي إعادة صياغة البيانات المحددة المعطاة لك بالعربية الفصحى البسيطة.

قواعد صارمة:
1. لا تخترع أرقاماً أو إحصاءات جديدة — استخدم فقط ما في البيانات
2. لا تضف توصيات جديدة — اكتب فقط ما طلب منك
3. لا تغير الأولويات أو الترتيب — الترتيب محدد مسبقاً
4. اكتب بنبرة البزنس المحددة في البيانات
5. اجعل النص واضحاً وقابلاً للتنفيذ
6. أجب فقط بـ JSON بدون أي نص خارجه
"""


class GroqWriter:

    def __init__(self):
        self._client: Groq | None = None

    @property
    def client(self) -> Groq:
        if self._client is None:
            self._client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        return self._client

    def enrich(self, engine_output: dict, business_profile: dict) -> dict:
        brand_tone = business_profile.get("brand_tone", "ودود وقريب")
        if isinstance(brand_tone, list):
            brand_tone = ", ".join(brand_tone)

        result = {**engine_output}

        result["insights"] = self._rewrite_insights(
            engine_output.get("insights", []),
            brand_tone,
        )

        result["strategies"] = self._rewrite_strategies(
            engine_output.get("strategies", []),
            brand_tone,
        )

        result["weekly_plan"] = self._enrich_weekly_plan(
            engine_output.get("weekly_plan", []),
            business_profile,
        )

        result["root_cause_text"] = self._rewrite_root_cause(
            engine_output.get("root_cause", {}),
            brand_tone,
        )

        return result

    def _rewrite_insights(self, insights: list, brand_tone: str) -> list:
        if not insights:
            return insights

        prompt = f"""
أعد صياغة هذه الملاحظات التحليلية بالعربية البسيطة بنبرة: {brand_tone}
لا تغير الأرقام أو المعنى — فقط اجعلها أوضح وأكثر قابلية للقراءة.

البيانات:
{json.dumps(insights, ensure_ascii=False)}

أرجع JSON بنفس الهيكل تماماً مع تحديث حقل "detail" فقط (لا تغير "type" أو "title"):
{{"insights": [...]}}
"""
        return self._call_groq_json(prompt).get("insights", insights)

    def _rewrite_strategies(self, strategies: list, brand_tone: str) -> list:
        if not strategies:
            return strategies

        prompt = f"""
أعد صياغة هذه القرارات الاستراتيجية بالعربية بنبرة: {brand_tone}
لا تغير الأولويات أو تضف قرارات جديدة — فقط اجعل الصياغة أوضح وأكثر تحفيزاً.

البيانات:
{json.dumps(strategies, ensure_ascii=False)}

أرجع JSON بنفس الهيكل مع تحديث حقول "title" و"root_cause_or_pattern" و"why_this_matters" و"recommended_action" فقط:
{{"strategies": [...]}}
"""
        return self._call_groq_json(prompt).get("strategies", strategies)

    def _enrich_weekly_plan(self, weekly_plan: list, business_profile: dict) -> list:
        if not weekly_plan:
            return weekly_plan

        product = business_profile.get("products", business_profile.get("product", "المنتج"))
        tone = business_profile.get("brand_tone", "ودود")
        if isinstance(tone, list):
            tone = ", ".join(tone)
        audience = business_profile.get("target_audience", "")
        age = business_profile.get("age_groups", "")
        full_audience = f"{audience} {age}".strip() or "الجمهور المستهدف"

        prompt = f"""
لديك خطة محتوى أسبوعية جاهزة الهيكل. مهمتك فقط:
1. كتابة hook قوي لكل يوم (مختلف عن الموجود)
2. كتابة سكريبت قصير جاهز للنشر
3. اقتراح caption مع hashtags مناسبة

معلومات البزنس:
- المنتج: {product}
- النبرة: {tone}
- الجمهور: {full_audience}

الخطة:
{json.dumps(weekly_plan, ensure_ascii=False)}

قواعد صارمة:
- لا تغير platform أو content_type أو goal أو best_posting_time — هذه محددة من المحرك
- فقط أضف أو حسّن: hook وcaption_or_script وأضف حقل script وcaption وhashtags لكل يوم
- اجعل كل hook يبدأ بمشكلة أو مفاجأة أو سؤال مباشر
- الـ script يجب أن يكون جاهزاً للقراءة أمام الكاميرا (15-30 ثانية)

أرجع JSON بنفس الهيكل مع تحسين hook وcaption_or_script وإضافة حقل hashtags:
{{"weekly_plan": [...]}}
"""
        return self._call_groq_json(prompt).get("weekly_plan", weekly_plan)

    def _rewrite_root_cause(self, root_cause: dict, brand_tone: str) -> str:
        if not root_cause:
            return ""

        prompt = f"""
اشرح هذه البيانات التحليلية بالعربية البسيطة في ٢-٣ جمل بنبرة: {brand_tone}
لا تضف أرقاماً جديدة — فقط اشرح المعنى بوضوح وقل ما يعنيه للبزنس.

البيانات:
{json.dumps(root_cause, ensure_ascii=False)}

أرجع JSON:
{{"text": "الشرح هنا"}}
"""
        return self._call_groq_json(prompt).get("text", "")

    # ── Audience voice analysis (caption-based) ───────────────────────────────

    def _normalize_sentiment(self, result: dict) -> dict:
        s = result.get("sentiment_breakdown", {})
        if not s:
            return result
        total = sum(s.values())
        if total > 0 and total != 100:
            result["sentiment_breakdown"] = {
                k: round(v / total * 100) for k, v in s.items()
            }
        return result

    def analyze_audience_from_captions(self, captions: list[str], business_profile: dict) -> dict:
        """Estimate likely audience questions/requests from video captions using Groq."""
        sample = [c[:200] for c in captions if c.strip()][:20]
        if not sample:
            return {}

        product = business_profile.get("products") or "المنتج"
        sector  = business_profile.get("sector") or business_profile.get("industry") or "النشاط"

        prompt = f"""بناءً على كابشن الفيديوهات التالية لمتجر {sector} ({product})، توقّعي ماذا يسأل الجمهور ويطلب.

كابشن الفيديوهات:
{json.dumps(sample, ensure_ascii=False)}

أرجعي JSON بهذا الهيكل بالضبط:
{{
  "frequent_questions": ["سؤال 1", "سؤال 2", "سؤال 3", "سؤال 4", "سؤال 5"],
  "product_requests": ["طلب 1", "طلب 2", "طلب 3", "طلب 4", "طلب 5"],
  "complaints": [],
  "content_suggestions": ["فكرة 1", "فكرة 2", "فكرة 3", "فكرة 4", "فكرة 5"],
  "sentiment_breakdown": {{"positive": 75, "neutral": 20, "negative": 5}},
  "top_comments": []
}}

JSON فقط بدون أي نص خارجه."""

        result = self._call_groq_json(prompt)
        if result:
            result = self._normalize_sentiment(result)
            result["is_estimated"] = True
        return result

    def analyze_real_comments(self, comments: list[dict], business_profile: dict) -> dict:
        """Analyze real comment texts using Groq."""
        texts = [c.get("text", "") for c in comments if len(c.get("text", "").strip()) > 3]
        if not texts:
            return {}

        sample = texts[:80]
        product = business_profile.get("products") or "المنتج"
        sector  = business_profile.get("sector") or business_profile.get("industry") or "النشاط"

        prompt = f"""حللي هذه التعليقات من جمهور متجر {sector} ({product}).

التعليقات:
{json.dumps(sample, ensure_ascii=False)}

أرجعي JSON بهذا الهيكل (النسب المئوية يجب أن تجمع 100):
{{
  "frequent_questions": ["أكثر 5 أسئلة نصية فعلية من التعليقات — مثل كيف أطلب، كم السعر، هل في توصيل"],
  "product_requests": ["أكثر 5 طلبات أو اقتراحات — مثل أريد بلون بيج، أريد مقاس كبير"],
  "complaints": ["أبرز الشكاوى إن وجدت — وإلا قائمة فارغة []"],
  "content_suggestions": ["5 أفكار محتوى مباشرة تجيب على هذه التعليقات"],
  "sentiment_breakdown": {{"positive": 70, "neutral": 20, "negative": 10}},
  "top_comments": ["أبرز 3 تعليقات نصية كاملة من القائمة"]
}}

JSON فقط بدون أي نص خارجه."""

        result = self._call_groq_json(prompt)
        if result:
            result = self._normalize_sentiment(result)
        return result

    # ── Starter plan for new businesses ──────────────────────────────────────

    def generate_starter_plan(self, business_profile: dict) -> dict:
        """Generate a complete content strategy for a brand-new business with no social history."""
        name       = business_profile.get("business_name") or "البزنس"
        sector     = business_profile.get("sector") or business_profile.get("industry") or "غير محدد"
        products   = business_profile.get("products") or "غير محدد"
        audience   = business_profile.get("target_audience") or business_profile.get("target_gender") or "عام"
        age        = business_profile.get("age_groups") or ""
        tone       = business_profile.get("brand_tone") or "ودود"
        goals      = business_profile.get("goals") or "زيادة المبيعات"
        budget     = business_profile.get("monthly_budget") or "غير محدد"
        competitors = business_profile.get("competitors") or "غير محدد"
        platforms_pref = business_profile.get("preferred_platforms") or []

        full_audience = f"{audience} {age}".strip()
        platforms_line = (
            f"منصات مفضلة: {', '.join(platforms_pref)}"
            if platforms_pref else ""
        )

        prompt = f"""أنتِ استراتيجية تسويق رقمي خبيرة في السوق الخليجي. بزنس جديد يريد البدء من الصفر.

معلومات البزنس:
- الاسم: {name}
- القطاع: {sector}
- المنتجات/الخدمات: {products}
- الجمهور: {full_audience}
- الهدف: {goals}
- النبرة: {tone}
- الميزانية الشهرية: {budget}
- منافسون للاستلهام: {competitors}
{platforms_line}

أرجعي JSON بهذا الهيكل بالضبط:
{{
  "recommended_platform": {{
    "primary": "tiktok أو instagram أو snapchat",
    "primary_reason": "سبب مرتبط بالمنتج والجمهور (جملتان)",
    "secondary": "المنصة الثانية",
    "secondary_reason": "السبب (جملة)",
    "platform_comparison": [
      {{"platform": "TikTok", "fit_score": 85, "reason": "سبب قصير"}},
      {{"platform": "Instagram", "fit_score": 70, "reason": "سبب قصير"}},
      {{"platform": "Snapchat", "fit_score": 55, "reason": "سبب قصير"}}
    ]
  }},
  "content_pillars": [
    {{"title": "اسم المحور", "description": "وصف المحور", "example_idea": "مثال محتوى", "frequency": "مرتان/أسبوع"}}
  ],
  "monthly_plan": [
    {{
      "week": 1,
      "theme": "موضوع الأسبوع",
      "days": [
        {{"day": "الأحد", "content_type": "فيديو تعليمي", "idea": "فكرة المحتوى", "hook": "جملة الافتتاح الجذابة", "platform": "TikTok"}}
      ]
    }}
  ],
  "ready_hooks": [
    {{"hook": "نص الـ hook جاهز للقراءة أمام الكاميرا", "content_type": "educational", "platform": "TikTok"}}
  ],
  "growth_strategy": {{
    "first_week": "ماذا تفعل في الأسبوع الأول تحديداً",
    "first_month": "هدف رقمي واقعي للشهر الأول",
    "three_months": "هدف رقمي واقعي بعد 3 أشهر",
    "key_habits": ["عادة يومية 1", "عادة يومية 2", "عادة يومية 3"],
    "avoid": ["خطأ شائع 1", "خطأ شائع 2", "خطأ شائع 3"]
  }},
  "hashtag_strategy": {{
    "primary": ["هاشتاق1", "هاشتاق2", "هاشتاق3", "هاشتاق4", "هاشتاق5"],
    "niche": ["هاشتاق1", "هاشتاق2", "هاشتاق3", "هاشتاق4", "هاشتاق5"],
    "trending_tip": "نصيحة عن نوع الهاشتاقات الترند المناسبة"
  }}
}}

قواعد: المحتوى يجب أن يكون خليجياً ومحلياً. الـ monthly_plan يشمل 4 أسابيع، كل أسبوع 4-5 أيام. الـ ready_hooks تكون 8 hooks مختلفة. JSON فقط."""

        return self._call_groq_json(prompt)

    # ── CSV sales analysis ────────────────────────────────────────────────────

    def analyze_csv_sales(
        self,
        columns: list[str],
        sample_rows: list[dict],
        numeric_summary: dict,
    ) -> str:
        """Extract business insights from a sales CSV and return a concise Arabic summary string."""
        import json as _json
        prompt = f"""حللي بيانات المبيعات التالية واستخرجي أبرز الأنماط.

الأعمدة: {', '.join(columns)}

عينة السجلات (أول 20):
{_json.dumps(sample_rows, ensure_ascii=False, default=str)}

ملخص الأرقام:
{_json.dumps(numeric_summary, ensure_ascii=False)}

أرجعي JSON بهذا الهيكل:
{{
  "top_products": ["أعلى 3 منتجات مبيعاً إن وُجدت"],
  "revenue_trend": "وصف مختصر لاتجاه الإيرادات",
  "best_period": "أفضل فترة مبيعات إن ظهرت",
  "key_finding": "أهم ملاحظة واحدة من البيانات"
}}

JSON فقط."""
        result = self._call_groq_json(prompt)
        if not result:
            return ""
        parts = []
        if result.get("key_finding"):
            parts.append(result["key_finding"])
        if result.get("revenue_trend"):
            parts.append(result["revenue_trend"])
        if result.get("top_products"):
            parts.append("أبرز المنتجات: " + "، ".join(result["top_products"]))
        return " | ".join(parts)

    # ── Sales + Social correlation ────────────────────────────────────────────

    def analyze_sales_with_social(
        self,
        sales_data: dict,
        social_metrics: dict,
        business_profile: dict,
    ) -> dict:
        """Correlate sales KPIs with social media performance and produce insights."""
        revenue   = sales_data.get("monthly_revenue")
        orders    = sales_data.get("orders")
        ad_spend  = sales_data.get("ad_spend")
        conv_rate = sales_data.get("conversion_rate")
        csv_insights = sales_data.get("csv_insights", "")

        avg_eng    = social_metrics.get("avg_engagement") or social_metrics.get("avg_engagement_rate") or 0
        total_views = social_metrics.get("total_views") or 0
        best_platform = social_metrics.get("best_platform") or "—"
        best_topics   = social_metrics.get("best_topics") or []

        # Compute derived KPIs
        derived: dict = {}
        try:
            if revenue and ad_spend and float(ad_spend) > 0:
                derived["roas"] = round(float(revenue) / float(ad_spend), 2)
        except Exception:
            pass
        try:
            if revenue and orders and float(orders) > 0:
                derived["avg_order_value"] = round(float(revenue) / float(orders))
        except Exception:
            pass
        try:
            if ad_spend and orders and float(orders) > 0:
                derived["cost_per_order"] = round(float(ad_spend) / float(orders))
        except Exception:
            pass

        kpi_lines = "\n".join([
            f"- الإيرادات الشهرية: {revenue or '—'} ريال",
            f"- عدد الطلبات الشهرية: {orders or '—'}",
            f"- الإنفاق الإعلاني: {ad_spend or '—'} ريال",
            f"- نسبة التحويل: {conv_rate or '—'}%",
            *(
                [f"- ROAS (عائد الإنفاق): {derived['roas']}x"]
                if "roas" in derived else []
            ),
            *(
                [f"- متوسط قيمة الطلب: {derived['avg_order_value']} ريال"]
                if "avg_order_value" in derived else []
            ),
            *(
                [f"- تكلفة الطلب الواحد: {derived['cost_per_order']} ريال"]
                if "cost_per_order" in derived else []
            ),
        ])

        social_lines = "\n".join([
            f"- متوسط التفاعل: {round(float(avg_eng) * 100, 1)}%",
            f"- إجمالي المشاهدات: {total_views}",
            f"- أفضل منصة: {best_platform}",
            f"- أفضل مواضيع: {', '.join(str(t) for t in best_topics[:3]) or '—'}",
        ])

        product = business_profile.get("products") or "المنتج"
        sector  = business_profile.get("sector") or business_profile.get("industry") or "النشاط"

        csv_section = f"\nبيانات CSV:\n{csv_insights}" if csv_insights else ""

        prompt = f"""أنتِ محللة أعمال متخصصة في ربط أداء السوشيال ميديا بالمبيعات لمتجر {sector} ({product}).

بيانات المبيعات:
{kpi_lines}

أداء السوشيال ميديا:
{social_lines}{csv_section}

قدمي تحليلاً واقعياً مبنياً على الأرقام فقط.
إذا كان رقم غير متاح، لا تفترضي — قولي "غير محدد".

أرجعي JSON بهذا الهيكل:
{{
  "correlation_insight": "جملتان تربطان الأرقام: مثل 'تفاعل X% مع إيرادات Y ريال يعني...'",
  "what_is_working": "ما الذي يعمل جيداً بناءً على الأرقام",
  "main_gap": "أهم فجوة بين أداء المحتوى والمبيعات",
  "top_action": "الإجراء الأكثر أثراً هذا الشهر بناءً على الأرقام",
  "kpi_ratings": {{
    "engagement": "ممتاز/مقبول/يحتاج تحسين",
    "roas": "ممتاز/مقبول/يحتاج تحسين/غير محدد",
    "conversion": "ممتاز/مقبول/يحتاج تحسين/غير محدد"
  }}
}}

JSON فقط."""

        result = self._call_groq_json(prompt)
        result["derived_kpis"] = derived
        return result

    # ── Conversational assistant ──────────────────────────────────────────────

    def chat(
        self,
        message: str,
        context: dict,
        history: list[dict],
    ) -> str:
        """Answer a user question using full analysis context. Returns Arabic text."""

        biz = context.get("business_profile", {})
        sp  = context.get("starter_plan", {})       # new-business mode
        ar  = context.get("analysis_result", {})
        rc  = ar.get("root_cause", {})
        dm  = ar.get("dashboard_metrics", {})
        cp  = ar.get("content_patterns", {})

        # Detect mode
        is_starter = bool(sp and sp.get("recommended_platform"))

        if is_starter:
            rp = sp.get("recommended_platform", {})
            gs = sp.get("growth_strategy", {})
            pillars_summary = "\n".join(
                f"  - {p.get('title','')}: {p.get('description','')[:60]}"
                for p in (sp.get("content_pillars") or [])[:5]
            )
            system = f"""أنتِ "مُدار AI" — مساعدة تسويقية لبزنس يبدأ من الصفر على السوشيال ميديا.

── معلومات البزنس ──
الاسم: {biz.get('business_name','—')}
القطاع: {biz.get('sector') or biz.get('industry','—')}
المنتجات: {biz.get('products','—')}
الجمهور: {biz.get('target_audience','—')}
الهدف: {biz.get('goals','—')}

── الخطة المُعدّة ──
المنصة الأساسية: {rp.get('primary','—')} — {rp.get('primary_reason','')[:80]}
المنصة الثانية: {rp.get('secondary','—')}
محاور المحتوى:
{pillars_summary or '—'}
هدف الشهر الأول: {gs.get('first_month','—')}
هدف 3 أشهر: {gs.get('three_months','—')}

── طريقة تواصلك ──
- تحدثي بالعربي الخليجي الواضح
- ركّزي على التطبيق العملي — اذكري خطوات قابلة للتنفيذ
- إذا سألوا عن تعديل، اقترحي البديل مباشرة
- ردودك مختصرة — لا إطالة
- لا تقولي "كمساعدة ذكاء اصطناعي..." — فقط أجيبي مباشرة"""
        else:
            top_topics = ", ".join(
                (t.get("topic") or t.get("label") or str(t)) if isinstance(t, dict) else str(t)
                for t in (cp.get("repeated_topics") or rc.get("best_topics", []))[:4]
            )
            top_tags = ", ".join(
                (h.get("label") or h.get("tag") or str(h)) if isinstance(h, dict) else str(h)
                for h in (cp.get("best_hashtags") or rc.get("best_hashtags", []))[:4]
            )
            strategies_summary = "\n".join(
                f"  - {s.get('title','')}: {(s.get('recommended_action') or '')[:80]}"
                for s in (ar.get("strategies") or [])[:3]
            )
            plan_summary = "\n".join(
                f"  - {d.get('day','')}: {d.get('content_type','')} — {(d.get('hook') or d.get('content_idea',''))[:60]}"
                for d in (ar.get("weekly_plan") or context.get("weekly_plan") or [])[:7]
            )
            sales = context.get("sales_summary") or {}
            sales_line = f"إيرادات شهرية: {sales.get('monthly_revenue','—')}" if sales else "لا توجد بيانات مبيعات"

            system = f"""أنتِ "مُدار AI" — مساعدة تسويقية ذكية. تعرفين نتائج تحليل النشاط التجاري التالي وتساعدين في فهمها واتخاذ القرارات.

── معلومات النشاط ──
الاسم: {biz.get('business_name') or biz.get('name','—')}
القطاع: {biz.get('sector') or biz.get('industry','—')}
المنتجات: {biz.get('products','—')}
الجمهور: {biz.get('target_audience') or biz.get('target_gender','—')}
النبرة: {biz.get('brand_tone') or biz.get('tone','—')}

── نتائج التحليل ──
أفضل منصة: {rc.get('best_platform') or dm.get('best_platform','—')}
متوسط التفاعل: {round((rc.get('avg_engagement') or dm.get('avg_engagement_rate') or 0)*100,1)}%
إجمالي الفيديوهات: {rc.get('total_posts') or dm.get('total_posts','—')}
إجمالي المشاهدات: {rc.get('total_views') or dm.get('total_views','—')}
أفضل مواضيع: {top_topics or '—'}
أفضل هاشتاقات: {top_tags or '—'}
{sales_line}

── القرارات الاستراتيجية ──
{strategies_summary or '—'}

── خطة المحتوى الأسبوعي ──
{plan_summary or '—'}

── طريقة تواصلك ──
- تحدثي بالعربي الخليجي الواضح والمباشر
- كوني عملية: اذكري أرقاماً حقيقية من البيانات عند الشرح
- إذا طلبوا تعديلاً، اقترحي النص المعدّل مباشرة
- ردودك مختصرة ومفيدة — لا إطالة بدون فائدة
- لا تقولي "كمساعدة ذكاء اصطناعي..." — فقط أجيبي مباشرة"""

        messages: list[dict] = [{"role": "system", "content": system}]
        for h in history[-8:]:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": message})

        try:
            res = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=600,
                temperature=0.5,
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            print(f"[GroqWriter.chat error] {e}")
            return "عذراً، صار خطأ مؤقت. جربي مرة ثانية."

    def _call_groq_json(self, prompt: str) -> dict[str, Any]:
        try:
            res = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=3000,
                temperature=0.3,
            )
            text = res.choices[0].message.content.strip()
            if "```" in text:
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            print(f"[GroqWriter error] {e}")
            return {}
