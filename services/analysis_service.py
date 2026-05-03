import os
from groq import Groq
from typing import List, Dict, Any, Optional

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"

client = Groq(api_key=GROQ_API_KEY)


def analyze_tiktok_videos(
    videos: List[Dict[str, Any]],
    business_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    videos_summary = "\n".join(
        [
            f"- Description: {v.get('desc', 'N/A')} | Views: {v.get('playCount', 0)} "
            f"| Likes: {v.get('diggCount', 0)} | Comments: {v.get('commentCount', 0)} "
            f"| Shares: {v.get('shareCount', 0)}"
            for v in videos[:15]
        ]
    )

    business_context = ""
    if business_profile:
        business_context = f"""
Business Profile:
- Name: {business_profile.get('business_name', 'Unknown')}
- Industry: {business_profile.get('industry', 'Unknown')}
- Target Audience: {business_profile.get('target_audience', 'Unknown')}
- Goals: {business_profile.get('goals', 'Not specified')}
- Website: {business_profile.get('website', 'Not specified')}
"""

    prompt = f"""أنت خبير في التسويق الرقمي ومتخصص في تيك توك. حلل هذه البيانات وقدم تقرير استراتيجي شامل باللغة العربية.

{business_context}

بيانات الفيديوهات:
{videos_summary}

اكتب تقريراً استراتيجياً شاملاً يتضمن الأقسام التالية بالضبط:

**١. أبرز ثيمات المحتوى الناجح**
حلل الأنماط المشتركة في الفيديوهات ذات الأداء العالي واذكر ٣-٥ ثيمات رئيسية.

**٢. رؤى التفاعل**
ما الذي يحقق المشاهدات والإعجابات والتعليقات؟ اذكر السبب الجذري لأي ضعف في الأداء.

**٣. توصيات استراتيجية للمحتوى**
قدم ٣-٥ توصيات تفصيلية وقابلة للتطبيق فوراً.

**٤. توقيت ووتيرة النشر**
أفضل أوقات وأيام النشر مع عدد المقاطع الأسبوعية الموصى بها.

**٥. استراتيجية الهاشتاق**
اذكر ١٠-١٥ هاشتاق موصى بها مقسمة إلى: (هاشتاقات كبيرة، متوسطة، متخصصة).

**٦. ٥ أفكار محتوى مخصصة**
اذكر ٥ أفكار فيديو محددة ومفصلة، لكل فكرة: العنوان، الخطاف الأول، الفكرة الرئيسية، والهدف.

**٧. المؤشرات الرئيسية للمتابعة**
اذكر ٥-٧ KPIs مع الأهداف المقترحة لكل منها.

اكتب بأسلوب واضح ومهني باللغة العربية. كن محدداً وعملياً."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2500,
        temperature=0.7,
    )

    return {
        "analysis": response.choices[0].message.content,
        "videos_analyzed": len(videos),
        "model_used": MODEL,
        "tokens_used": response.usage.total_tokens if response.usage else None,
    }
