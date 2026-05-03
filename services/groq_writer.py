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
