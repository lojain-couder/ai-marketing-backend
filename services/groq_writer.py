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
from groq import RateLimitError, APIStatusError, AuthenticationError

MODEL = "qwen/qwen3-32b"

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

        try:
            result["insights"] = self._rewrite_insights(
                engine_output.get("insights", []),
                brand_tone,
            )
        except RuntimeError as e:
            print(f"[GroqWriter.enrich] insights skipped: {e}")
            result["_groq_warning"] = str(e)

        try:
            result["strategies"] = self._rewrite_strategies(
                engine_output.get("strategies", []),
                brand_tone,
            )
        except RuntimeError as e:
            print(f"[GroqWriter.enrich] strategies skipped: {e}")
            result.setdefault("_groq_warning", str(e))

        try:
            result["weekly_plan"] = self._enrich_weekly_plan(
                engine_output.get("weekly_plan", []),
                business_profile,
            )
        except RuntimeError as e:
            print(f"[GroqWriter.enrich] weekly_plan skipped: {e}")
            result.setdefault("_groq_warning", str(e))

        try:
            result["root_cause_text"] = self._rewrite_root_cause(
                engine_output.get("root_cause", {}),
                brand_tone,
            )
        except RuntimeError as e:
            print(f"[GroqWriter.enrich] root_cause skipped: {e}")

        try:
            result["posting_schedule"] = self._generate_posting_schedule(business_profile)
        except RuntimeError as e:
            print(f"[GroqWriter.enrich] posting_schedule skipped: {e}")
            result["posting_schedule"] = {}

        try:
            result["conversion_playbook"] = self._generate_conversion_playbook(business_profile)
        except RuntimeError as e:
            print(f"[GroqWriter.enrich] conversion_playbook skipped: {e}")
            result["conversion_playbook"] = {}

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

        from bi_advisor.seasons import seasons_context_text

        product  = business_profile.get("products") or business_profile.get("product") or "المنتج"
        sector   = business_profile.get("industry") or business_profile.get("sector") or ""
        tone     = business_profile.get("brand_tone") or "ودود"
        if isinstance(tone, list):
            tone = ", ".join(tone)
        audience    = business_profile.get("target_audience") or ""
        age         = business_profile.get("age_groups") or ""
        biz_name    = business_profile.get("business_name") or business_profile.get("name") or "البزنس"
        full_audience = f"{audience} {age}".strip() or "الجمهور المستهدف"
        seasons_line  = seasons_context_text(lookahead_days=30)

        # Only keep structural metadata — let Groq create the creative content
        structure = [
            {
                "day":              d.get("day"),
                "platform":         d.get("platform"),
                "content_type":     d.get("content_type"),
                "goal":             d.get("goal"),
                "theme":            d.get("theme"),
                "best_posting_time":d.get("best_posting_time"),
                "hashtags":         d.get("hashtags", []),
                # Pass season context so Groq can write season-specific content
                **({"season": d["season"], "season_urgency": d["season_urgency"]}
                   if d.get("theme") == "seasonal" else {}),
            }
            for d in weekly_plan
        ]

        seasons_section = f"\n── المواسم القادمة ──\n{seasons_line}\n" if seasons_line else ""

        prompt = f"""أنتِ خبيرة تسويق محتوى متخصصة في السوشيال ميديا الخليجية. مهمتك كتابة محتوى حقيقي وقابل للتنفيذ فوراً.

── البزنس ──
الاسم: {biz_name} | المنتج: {product} | القطاع: {sector or '—'} | النبرة: {tone} | الجمهور: {full_audience}{seasons_section}

── هيكل الأيام (لا تغيريه) ──
{json.dumps(structure, ensure_ascii=False)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قواعد الـ hook — لازم تطبقيها
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ سؤال يلامس مشكلة حقيقية يعيشها {full_audience} مرتبطة بـ {product}
✅ رقم أو مفاجأة عن {product} أو {sector}
✅ تحدي مباشر أو FOMO يشعر به هذا الجمهور تحديداً
❌ ممنوع: "مرحبا" / "أهلا" / "اكتشفوا" / "أفضل [منتج]" / "كل ما تحتاجه عن"
❌ ممنوع: عناوين عامة مثل "فوائد X" أو "كيف تختار X" أو "دليل شامل عن X"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قواعد الـ content_idea
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
كل فكرة لازم تكون محددة جداً — مو عامة. بدل "محتوى تعليمي عن المنتج" اكتبي "اعرضي ثلاث طرق غريبة يستخدم فيها الناس {product} بشكل خاطئ وكيف يتجنبونها".
اربطي كل فكرة بلحظة حقيقية في حياة {full_audience} — وقت القهوة، قبل النوم، عند التسوق، مع الأهل.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قواعد الـ caption_or_script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
كابشن جاهز للنشر مباشرة بنبرة {tone} — مو وصف لفكرة. اكتبي الكلمات الفعلية.

للأيام الموسمية: اربطي {product} بروح الموسم ذكياً — لا تذكر الموسم وحده.

قواعد إضافية:
- كل يوم فكرة مختلفة تماماً — لا تكرار في الأسلوب أو الزاوية
- أضيفي content_goal لكل يوم: "تحويل" أو "وعي" أو "ثقة" أو "تفاعل"
- وزّعي "تحويل" بذكاء: يوم الأحد ويوم الخميس فقط (البقية توزيع مختلف)

أرجعي JSON بهذا الهيكل بالضبط:
{{"weekly_plan": [{{"day": "...", "platform": "...", "content_type": "...", "goal": "...", "content_goal": "تحويل", "theme": "...", "best_posting_time": "...", "hashtags": [...], "hook": "...", "content_idea": "...", "caption_or_script": "...", "cta": "..."}}]}}"""

        return self._call_groq_json(prompt, max_tokens=4000).get("weekly_plan", weekly_plan)

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

    # ── Posting schedule + conversion playbook for existing businesses ────────

    def _generate_posting_schedule(self, business_profile: dict) -> dict:
        product  = business_profile.get("products") or business_profile.get("product") or "المنتج"
        sector   = business_profile.get("industry") or business_profile.get("sector") or ""
        audience = business_profile.get("target_audience") or ""
        platforms = business_profile.get("preferred_platforms") or business_profile.get("platforms") or ["TikTok", "Instagram"]
        if isinstance(platforms, str):
            platforms = [platforms]
        platforms_str = "، ".join(platforms)

        prompt = f"""أنتِ خبيرة تسويق رقمي خليجية. حددي أفضل أوقات وأيام النشر لهذا البزنس.

البزنس: {sector} | المنتج: {product} | الجمهور: {audience} | المنصات: {platforms_str}

لكل منصة مختارة اذكري:
- best_days: أفضل 3 أيام في الأسبوع (بالعربية)
- best_times: فترتان زمنيتان محددتان (مثل "7:00م - 9:00م")
- frequency_per_week: عدد المنشورات الأسبوعية الموصى بها
- why: سبب واحد قصير مخصص لهذا الجمهور

أرجعي JSON فقط بمفاتيح هي أسماء المنصات:
{{
  "TikTok": {{"best_days": [...], "best_times": [...], "frequency_per_week": 4, "why": "..."}}
}}
JSON فقط بدون أي نص خارجه."""

        return self._call_groq_json(prompt)

    def _generate_conversion_playbook(self, business_profile: dict) -> dict:
        product  = business_profile.get("products") or business_profile.get("product") or "المنتج"
        sector   = business_profile.get("industry") or business_profile.get("sector") or ""
        audience = business_profile.get("target_audience") or ""

        prompt = f"""أنتِ خبيرة تحويل مبيعات. حللي ما الذي يدفع هذا الجمهور للشراء.

البزنس: {sector} | المنتج: {product} | الجمهور: {audience}

أرجعي JSON فقط:
{{
  "what_makes_them_buy": "جملة واحدة — ما يدفع هذا الجمهور تحديداً للدفع",
  "top_triggers": ["محفز 1 مخصص", "محفز 2", "محفز 3"],
  "money_content_types": ["نوع المحتوى الذي يحول متابع لعميل", "نوع 2", "نوع 3"],
  "weak_spots": "ما يمنع الشراء — اتجنبيه"
}}
JSON فقط بدون أي نص خارجه."""

        return self._call_groq_json(prompt)

    # ── Starter plan for new businesses ──────────────────────────────────────

    def generate_starter_plan(self, business_profile: dict) -> dict:
        """Generate a complete content strategy for a brand-new business with no social history."""
        name        = business_profile.get("business_name") or "البزنس"
        sector      = business_profile.get("sector") or business_profile.get("industry") or "غير محدد"
        products    = business_profile.get("products") or "غير محدد"
        audience    = business_profile.get("target_audience") or business_profile.get("target_gender") or "عام"
        age         = business_profile.get("age_groups") or ""
        tone        = business_profile.get("brand_tone") or "ودود وعفوي"
        goals       = business_profile.get("goals") or "زيادة المبيعات"
        value_prop  = business_profile.get("value_proposition") or ""

        platforms_pref = business_profile.get("preferred_platforms") or []
        full_audience  = f"{audience} {age}".strip()
        value_line     = f"ميزة تنافسية: {value_prop}" if value_prop else ""

        # Gender instruction for content
        aud_lower = full_audience.lower()
        _female = ["نساء","بنات","سيدات","نسائي","female","women","girl","امرأة"]
        _male   = ["رجال","شباب","أولاد","ذكور","male","men","boy","رجل"]
        if any(w in aud_lower for w in _female):
            gender_instruction = "الجمهور نسائي — خاطبيهم بصيغة مؤنث (اشتري، جربي، احفظي، تواصلي)"
        elif any(w in aud_lower for w in _male):
            gender_instruction = "الجمهور ذكوري — خاطبيهم بصيغة مذكر (اشتر، جرب، احفظ، تواصل)"
        else:
            gender_instruction = "الجمهور مختلط أو غير محدد — استخدمي صيغة محايدة أو اذكري الصيغتين (اشتر/ي، جرب/ي)"

        # Platform instructions — respect what the user chose
        if platforms_pref:
            platforms_chosen = "، ".join(platforms_pref)
            platform_instruction = f"""── المنصات المختارة من المستخدمة ──
{platforms_chosen} — يجب أن يكون كل المحتوى لهذه المنصات فقط. لا تقترحي منصات أخرى.
{"⚠️ X (تويتر) مختار: المحتوى نصي بالدرجة الأولى (تغريدات، سلاسل، استطلاعات). الـ visual_setup يكون صورة أو جرافيك مو فيديو. لا سكريبت للكاميرا." if "X" in platforms_pref else ""}"""
        else:
            platforms_chosen = "TikTok أو Instagram"
            platform_instruction = "── المنصة المقترحة ──\naختاري المنصة الأنسب للمنتج والجمهور"

        content_formulas = self._sector_content_formulas(sector, products)

        # X-specific content format
        x_format = ""
        if platforms_pref and "X" in platforms_pref:
            x_format = """
── تنسيق محتوى X (تويتر) ──
- content_type: "تغريدة" أو "سلسلة تغريدات" أو "استطلاع" أو "تغريدة + صورة"
- script: النص الكامل للتغريدة أو السلسلة (280 حرف للتغريدة الواحدة)
- visual_setup: وصف الصورة أو الجرافيك المرفق (مو فيديو)
- hook: أول جملة في التغريدة — تثير الفضول وتدفع للقراءة"""

        prompt = f"""أنتِ مديرة إنتاج محتوى محترفة للسوق الخليجي.

── البزنس ──
الاسم: {name} | القطاع: {sector} | المنتج: {products}
الجمهور: {full_audience} | النبرة: {tone} | الهدف: {goals}
{value_line}
{gender_instruction}

{platform_instruction}{x_format}

── أنماط المحتوى الناجحة في هذا القطاع ──
{content_formulas}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قواعد الـ HOOK:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ سؤال مشكلة | رقم + مفاجأة | تحدي | FOMO | إثبات
❌ مرحبا / أهلا / اكتشفوا / أفضل [منتج] / نقدم لكم

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قواعد الـ SCRIPT — كلمات تُقال فعلاً:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[0-3ث]: hook | [3-12ث]: القيمة | [12-15ث]: دعوة الفعل
اللهجة خليجية عفوية. {gender_instruction}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قواعد الـ VISUAL_SETUP — ماذا يُصوَّر بالضبط:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
اذكري: الموقع + الـ props + حركة الكاميرا
✅ "قفي أمام رف {products}، أمسكي قطعتين، وجّهي الكاميرا ببطء من الأسفل للأعلى"
❌ "اعرضي المنتج" أو "صوّري الفيديو"

أرجعي JSON بهذا الهيكل بالضبط:
{{
  "recommended_platform": {{
    "primary": "المنصة الأساسية من: {platforms_chosen}",
    "primary_reason": "سببان مرتبطان بـ {products} والجمهور {full_audience}",
    "secondary": "المنصة الثانية إن وُجدت من: {platforms_chosen}",
    "secondary_reason": "سبب مختصر",
    "platform_comparison": [
      {{"platform": "اسم منصة من المختارة", "fit_score": 85, "reason": "سبب مخصص للمنتج"}}
    ]
  }},
  "content_pillars": [
    {{
      "title": "اسم المحور مرتبط بـ {products}",
      "description": "وصف مخصص — مو عام",
      "example_idea": "فكرة ملموسة",
      "script_sample": "كلمتان تُقالان أمام الكاميرا",
      "frequency": "كم مرة/أسبوع"
    }}
  ],
  "monthly_plan": [
    {{
      "week": 1,
      "week_goal": "وعي",
      "theme": "موضوع مرتبط بـ {products} تحديداً — مو عنوان عام مثل 'بناء الثقة'",
      "focus": "وصف واضح لهدف الأسبوع مرتبط بـ {products} و{full_audience}",
      "days": [
        {{
          "day": "الأحد",
          "content_goal": "وعي",
          "content_type": "ريلز 15ث / فيديو 60ث / ستوري / كاروسيل / تغريدة",
          "hook": "الجملة الافتتاحية بالضبط — تطبق قواعد الـ hook",
          "script": "[0-3ث]: \\"...\\" | [3-12ث]: \\"...\\" | [12-15ث]: \\"...\\"",
          "visual_setup": "الموقع + الـ props + حركة الكاميرا بالتفصيل",
          "caption": "كابشن جاهز للنشر مع إيموجي — {gender_instruction}",
          "hashtags": ["#هاشتاق1", "#هاشتاق2", "#هاشتاق3"],
          "cta": "دعوة الفعل المناسبة للجمهور — {gender_instruction}",
          "platform": "منصة من المختارة: {platforms_chosen}"
        }}
      ]
    }}
  ],
  "instant_content": [
    {{
      "title": "عنوان الفكرة — جملة واحدة",
      "what_to_film": "افتحي الكاميرا الآن وصوّري: [تعليمات فورية محددة جداً]",
      "hook": "أول جملة تقوليها",
      "caption": "كابشن جاهز للنشر الفوري",
      "time_needed": "5 دقائق / 10 دقائق / 15 دقيقة",
      "platform": "منصة من المختارة: {platforms_chosen}",
      "conversion_goal": "تحويل / وعي / ثقة"
    }}
  ],
  "growth_strategy": {{
    "first_week": "خطوات يوم 1 في {platforms_chosen} لـ {products}: [خطوات محددة قابلة للتنفيذ فوراً]",
    "first_month": "هدف رقمي واقعي لـ {sector} في {platforms_chosen}: متابعين + تفاعل + طلبات",
    "three_months": "هدف رقمي بعد 3 أشهر مع خطة الوصول إليه",
    "key_habits": [
      "عادة يومية محددة لـ {platforms_chosen}",
      "عادة أسبوعية مرتبطة بـ {products}",
      "عادة لبناء جمهور {full_audience}"
    ],
    "avoid": [
      "خطأ شائع في {sector} على {platforms_chosen} تحديداً",
      "خطأ ثانٍ مرتبط بـ {products}",
      "خطأ ثالث يرتكبه البزنس الجديد في هذا القطاع"
    ]
  }},
  "posting_schedule": {{
    "PLATFORM_NAME": {{
      "best_days": ["الثلاثاء", "الأربعاء", "الجمعة"],
      "best_times": ["7:00م - 9:00م", "12:00م - 2:00م"],
      "frequency_per_week": 3,
      "why": "سبب مخصص لجمهور {full_audience} في {sector} — متى يكون نشطاً وليش هذه الأوقات تحديداً"
    }}
  }},
  "conversion_playbook": {{
    "what_makes_them_buy": "جملة واحدة: ما الذي يدفع {full_audience} تحديداً للدفع والشراء من {products}",
    "top_triggers": [
      "محفز الشراء الأول — مخصص لـ {products} وجمهوره",
      "محفز الشراء الثاني",
      "محفز الشراء الثالث"
    ],
    "money_content_types": [
      "نوع المحتوى الذي يحول المتابع لعميل فعلاً — مخصص لـ {sector}",
      "نوع ثانٍ مثبت في هذا القطاع",
      "نوع ثالث"
    ],
    "weak_spots": "ما يمنع {full_audience} من الشراء — اتجنبيه في كل محتوى"
  }},
  "hashtag_strategy": {{
    "primary": ["هاشتاقات رئيسية مرتبطة بـ {products}"],
    "niche": ["هاشتاقات ضيقة ومتخصصة"],
    "trending_tip": "نصيحة عن هاشتاقات الترند الخليجية لـ {sector}"
  }}
}}

monthly_plan: 4 أسابيع، 4-5 أيام/أسبوع.
- كل أسبوع يجب أن يحتوي على حقل week_goal واحد من: "وعي" | "ثقة" | "تحويل" | "تفاعل"
- كل يوم يجب أن يحتوي على حقل content_goal واحد من: "تحويل" | "وعي" | "ثقة" | "تفاعل"
- توزيع مقترح: الأسبوع 1 وعي، الأسبوع 2 ثقة، الأسبوع 3 تحويل، الأسبوع 4 تفاعل — مع أيام تحويل موزعة طوال الشهر
instant_content: 8 أفكار — كل فكرة تُصوَّر خلال 15 دقيقة بدون تحضير مسبق. أضيفي حقل conversion_goal لكل فكرة: "تحويل" | "وعي" | "ثقة"
content_pillars: 5 محاور.
posting_schedule: اجعلي المفتاح اسم المنصة الفعلية (مثل TikTok أو Instagram أو X) — ليس "PLATFORM_NAME".
JSON فقط بدون أي نص خارجه."""

        return self._call_groq_json(prompt, max_tokens=9000)

    def regenerate_hook(
        self,
        original: dict,
        business_profile: dict,
        feedback: str = "",
        dislike_reason: str = "",
        liked_examples: list[dict] | None = None,
    ) -> dict:
        """Regenerate a single hook+script based on user feedback and liked examples."""
        product  = business_profile.get("products") or "المنتج"
        sector   = business_profile.get("sector") or business_profile.get("industry") or ""
        audience = business_profile.get("target_audience") or ""
        tone     = business_profile.get("brand_tone") or "ودود عفوي"
        if isinstance(tone, list):
            tone = ", ".join(tone)

        reason_map = {
            "formal":    "رسمي جداً — تريد لهجة أكثر عفوية وخليجية",
            "irrelevant":"مو مرتبط بالمنتج — تريد hook أقرب لـ " + product,
            "hard":      "صعب التصوير — تريد visual_setup أبسط وأسهل تنفيذاً",
            "dialect":   "مو بلهجتها — تريد لهجة خليجية أكثر طبيعية",
            "generic":   "عام جداً — تريد hook أكثر تخصصاً لـ " + product,
        }
        reason_text = reason_map.get(dislike_reason, dislike_reason or "لم يناسبها")
        feedback_text = f"ملاحظة إضافية: {feedback}" if feedback.strip() else ""

        liked_section = ""
        if liked_examples:
            examples = "\n".join(
                f'- Hook: "{e.get("hook","")}" | Script: {e.get("script","")[:80]}'
                for e in liked_examples[:3]
            )
            liked_section = f"\n── ما أعجبها سابقاً (اقتربي من هذا الأسلوب) ──\n{examples}"

        # Detect instant_content item vs monthly-plan hook
        is_instant = bool(original.get("what_to_film"))

        if is_instant:
            liked_section_instant = ""
            if liked_examples:
                examples = "\n".join(
                    f'- فكرة: "{e.get("title","")}" | Hook: "{e.get("hook","")}"'
                    for e in liked_examples[:3]
                )
                liked_section_instant = f"\n── ما أعجبها سابقاً (اقتربي من هذا الأسلوب) ──\n{examples}"

            prompt = f"""أنتِ خبيرة محتوى. المستخدمة لم تعجبها هذه الفكرة الفورية:

الفكرة القديمة: "{original.get('title','')}"
ماذا تصوّر: {original.get('what_to_film','')[:100]}
Hook: "{original.get('hook','')}"
السبب: {reason_text}
{feedback_text}{liked_section_instant}

── معلومات البزنس ──
المنتج: {product} | القطاع: {sector} | الجمهور: {audience} | النبرة: {tone}

── قواعد الفكرة الجديدة ──
✅ فكرة قابلة للتنفيذ خلال 5-15 دقيقة فقط — بدون تحضير
✅ تصوير بالكاميرا الأمامية أو الخلفية — لا تجهيزات
✅ مرتبطة بـ {product} تحديداً
✅ لهجة خليجية عفوية
❌ لا تكرري نفس الفكرة أو نفس الـ hook

ولّدي فكرة جديدة مختلفة كلياً.
أرجعي JSON فقط:
{{
  "title": "عنوان الفكرة الجديدة — جملة واحدة",
  "what_to_film": "افتحي الكاميرا الآن وصوّري: [تعليمات فورية محددة]",
  "hook": "أول جملة تقوليها",
  "caption": "كابشن جاهز للنشر الفوري",
  "time_needed": "5 / 10 / 15 دقيقة",
  "platform": "{original.get('platform','')}"
}}"""
        else:
            prompt = f"""أنتِ خبيرة محتوى. المستخدمة لم تعجبها هذا الـ hook:

Hook قديم: "{original.get('hook','')}"
Script قديم: {original.get('script','')[:100]}
السبب: {reason_text}
{feedback_text}{liked_section}

── معلومات البزنس ──
المنتج: {product} | القطاع: {sector} | الجمهور: {audience} | النبرة: {tone}

── قواعد الـ Hook الجديد ──
✅ يبدأ بسؤال مشكلة / رقم مفاجئ / تحدي / FOMO / إثبات
✅ لهجة خليجية عفوية طبيعية — مو فصحى
✅ مرتبط بـ {product} تحديداً
❌ لا ترحيب / لا وصف / لا "اكتشفوا" / لا "أفضل [منتج]"
❌ لا تكرري نفس الـ hook القديم أو أسلوبه

ولّدي hook جديد مختلف كلياً مع script وvisual_setup.
أرجعي JSON فقط:
{{
  "hook": "الجملة الافتتاحية الجديدة",
  "why_it_works": "جملة: ليش هذا أفضل من السابق",
  "full_script": "[0-3ث]: \\"...\\" | [3-12ث]: \\"...\\" | [12-15ث]: \\"...\\"",
  "visual_setup": "أين + ماذا تمسكين + حركة الكاميرا"
}}"""

        return self._call_groq_json(prompt)

    def _sector_content_formulas(self, sector: str, products: str) -> str:
        """Return proven content formulas for the given sector."""
        sector_lower = (sector + " " + products).lower()

        if any(k in sector_lower for k in ["ملابس", "فاشن", "عباي", "عبايا", "fashion", "clothing", "موضة"]):
            return """- فيديو تنسيق الإطلالة (OOTD): اعرضي الطقم كاملاً مع وصف المناسبة
- before/after: قبل وبعد لبس القطعة على أجسام مختلفة
- تحدي الـ 3 طرق: نفس القطعة بـ 3 تنسيقات مختلفة
- unboxing + first impression: فتح الطلبية مع التعليق الصريح
- رأيك الصريح: قولي شيء واحد مايعجبك وشيء تحبينه في هذا الموديل"""

        if any(k in sector_lower for k in ["أكل", "مطعم", "طعام", "كافيه", "قهوة", "food", "coffee", "cafe", "مخبز"]):
            return """- taste test + رد فعل صادق: التجربة الأولى أمام الكاميرا
- behind the scenes: كيف يتحضر الطبق أو المنتج
- comparison: منتجنا vs منتج ثاني (من غير ذكر اسم)
- سؤال + إجابة: "ليش هذا المنتج يختلف؟" جاوبي بالأرقام
- رحلة العميل: قصة عميل حقيقي بالتفصيل"""

        if any(k in sector_lower for k in ["عناية", "بشرة", "جمال", "beauty", "skincare", "makeup", "مكياج", "عطر"]):
            return """- روتين قبل/بعد: خطوات واضحة مع نتائج حقيقية
- تجربة صادقة: ماذا حدث بعد أسبوع/شهر استخدام
- myth vs reality: افضحي خرافة شائعة في {products}
- صباح المتجر: روتين بسيط بمنتجاتنا فقط
- مقارنة مكونات: لماذا مكوناتنا مختلفة"""

        if any(k in sector_lower for k in ["لياقة", "جيم", "رياضة", "fitness", "gym", "sport", "تمرين"]):
            return """- تحويل في 30 ثانية: قبل وبعد مع الأرقام
- تمرين سريع: روتين 3 دقائق جاهز للتطبيق
- خطأ شائع: أكثر خطأ يرتكبه المبتدئون
- يوم في حياتنا: روتين حقيقي بدون تزوير
- "لو بدأت من الصفر كنت...": نصيحة خبرة حقيقية"""

        if any(k in sector_lower for k in ["خدمة", "استشارة", "تدريب", "service", "coaching", "consulting"]):
            return """- قصة تحول عميل: المشكلة → الحل → النتيجة بالأرقام
- reveal المشكلة: أكثر مشكلة يطلب فيها الناس مساعدة
- FAQ: أكثر 3 أسئلة وإجاباتها الصريحة
- behind the scenes: ماذا يحدث خلف الكواليس
- رأيك الصريح: شيء يحتاج ناس يسمعونه عن هذا المجال"""

        # Default for e-commerce / general
        return """- product demo: اعرض المنتج وهو يستخدم في الحياة الواقعية
- unboxing صادق: فتح المنتج مع تعليق حقيقي — الإيجابيات والسلبيات
- comparison: قبل وبعد استخدام المنتج
- customer story: قصة عميل حقيقي مع نتائج ملموسة
- سؤال مباشر: "بتشتري؟ هذا هو المنتج المناسب لك إذا..."
"""

    # ── Audio transcription ───────────────────────────────────────────────────

    def transcribe_audio(self, file_bytes: bytes, filename: str) -> str:
        response = self.client.audio.transcriptions.create(
            file=(filename, file_bytes),
            model="whisper-large-v3",
            response_format="text",
            prompt="فيديو سوشيال ميديا باللغة العربية",
        )
        return response if isinstance(response, str) else str(response)

    def extract_spoken_elements(self, transcript: str, caption: str = "") -> dict:
        context = f"الكابشن المكتوب: {caption[:200]}\n\n" if caption else ""
        prompt = f"""{context}هذا نص فيديو سوشيال ميديا منطوق. استخرج منه:
- hook: أول جملة أو سؤال يقوله المتحدث (أول 3-5 ثوان) — الجملة التي تجذب الانتباه
- cta: دعوة الفعل إن وجدت ("اشتر الآن"، "تابعوني"، "علّق"، إلخ) — null إن لم توجد
- topic: الموضوع الرئيسي (2-3 كلمات)
- key_message: الرسالة الأساسية للفيديو (جملة واحدة)

النص المنطوق:
{transcript[:2000]}

أرجع JSON فقط:
{{"hook": "...", "cta": "...", "topic": "...", "key_message": "..."}}"""

        result = self._call_groq_json(prompt)
        return {
            "hook":        result.get("hook", ""),
            "cta":         result.get("cta"),
            "topic":       result.get("topic", ""),
            "key_message": result.get("key_message", ""),
        }

    # ── CSV sales analysis ────────────────────────────────────────────────────

    def map_csv_columns(
        self,
        columns: list[str],
        sample_rows: list[dict],
    ) -> dict[str, str]:
        """Use LLM to map any column names to standard BI fields regardless of language/naming."""
        import json as _json
        prompt = f"""لديكِ ملف مبيعات بالأعمدة التالية. حددي أي عمود يقابل أي حقل قياسي.

الأعمدة: {_json.dumps(columns, ensure_ascii=False)}

عينة البيانات:
{_json.dumps(sample_rows[:3], ensure_ascii=False, default=str)}

الحقول القياسية المطلوبة (ضعي null إذا لا يوجد عمود مقابل):
- revenue: المبلغ الكلي للبيع أو الإيراد
- order_date: تاريخ الطلب أو البيع
- product_name: اسم المنتج أو الصنف
- customer_id: معرف العميل أو اسمه
- quantity: الكمية
- ad_spend: الإنفاق الإعلاني
- channel: قناة البيع أو المصدر
- customer_type: نوع العميل (جديد/قديم)

أرجعي JSON فقط — مفاتيحه الحقول القياسية وقيمها أسماء الأعمدة الأصلية:
{{"revenue": "...", "order_date": "...", "product_name": "...", "customer_id": null, ...}}"""
        result = self._call_groq_json(prompt)
        return {k: v for k, v in result.items() if v and isinstance(v, str)}

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

        has_manual_kpis = any([revenue, orders, ad_spend, conv_rate])

        if has_manual_kpis:
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
        elif csv_insights:
            kpi_lines = "بيانات المبيعات مرفوعة من ملف CSV — راجع تحليل البيانات أدناه"
        else:
            kpi_lines = "لا توجد بيانات مبيعات مدخلة"

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
- لا تقولي "كمساعدة ذكاء اصطناعي..." — فقط أجيبي مباشرة

── حدود صارمة لا تتجاوزيها ──
- أنتِ مساعدة تسويقية فقط — لا تجيبي على أي سؤال خارج التسويق والمحتوى والسوشيال ميديا
- إذا سألوا عن برمجة، كود، APIs، أو تقنيات — قولي: "أنا هنا فقط للمساعدة في التسويق والمحتوى، هذا السؤال خارج نطاق اختصاصي"
- إذا سألوا عن مُدار كمنصة أو كيف تعمل تقنياً — نفس الرد
- إذا سألوا عن صاحبة/مطورة المنصة أو أي معلومات شخصية — قولي: "لا أملك هذه المعلومات، أنا هنا لمساعدتك في تسويق بزنسك"
- لا تذكري اسم أي شخص أو تتكلمي عن الفريق أو المطورين"""
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
            if not sales:
                sales_line = "لا توجد بيانات مبيعات"
            elif sales.get("monthly_revenue"):
                sales_line = f"إيرادات شهرية: {sales['monthly_revenue']}"
            elif sales.get("csv_insights"):
                sales_line = f"بيانات مبيعات مرفوعة من CSV ({sales.get('rows','')} سجل)"
            else:
                sales_line = "لا توجد بيانات مبيعات"

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
- لا تقولي "كمساعدة ذكاء اصطناعي..." — فقط أجيبي مباشرة

── حدود صارمة لا تتجاوزيها ──
- أنتِ مساعدة تسويقية فقط — لا تجيبي على أي سؤال خارج التسويق والمحتوى والسوشيال ميديا
- إذا سألوا عن برمجة، كود، APIs، أو تقنيات — قولي: "أنا هنا فقط للمساعدة في التسويق والمحتوى، هذا السؤال خارج نطاق اختصاصي"
- إذا سألوا عن مُدار كمنصة أو كيف تعمل تقنياً — نفس الرد
- إذا سألوا عن صاحبة/مطورة المنصة أو أي معلومات شخصية — قولي: "لا أملك هذه المعلومات، أنا هنا لمساعدتك في تسويق بزنسك"
- لا تذكري اسم أي شخص أو تتكلمي عن الفريق أو المطورين"""

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

    def _call_groq_json(self, prompt: str, max_tokens: int = 3000) -> dict[str, Any]:
        try:
            res = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"/no_think\n{prompt}"},
                ],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            text = res.choices[0].message.content.strip()
            if "```" in text:
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except RateLimitError as e:
            print(f"[GroqWriter] QUOTA EXHAUSTED: {e}")
            raise RuntimeError("groq_quota_exhausted")
        except AuthenticationError as e:
            print(f"[GroqWriter] AUTH ERROR — invalid API key: {e}")
            raise RuntimeError("groq_auth_error")
        except APIStatusError as e:
            print(f"[GroqWriter] API error {e.status_code}: {e.message}")
            raise RuntimeError(f"groq_api_error_{e.status_code}")
        except json.JSONDecodeError as e:
            print(f"[GroqWriter] JSON parse error: {e}")
            return {}
        except Exception as e:
            print(f"[GroqWriter error] {e}")
            return {}
