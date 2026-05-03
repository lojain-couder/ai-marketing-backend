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

    prompt = f"""You are an expert AI Marketing Strategist specializing in TikTok growth and social media marketing.

{business_context}

TikTok Videos Performance Data:
{videos_summary}

Provide a comprehensive strategic marketing analysis with these sections:

1. **Top Performing Content Themes** — identify patterns in high-engagement videos
2. **Engagement Insights** — what drives views, likes, comments, and shares
3. **Content Strategy Recommendations** — specific actionable tactics
4. **Posting Frequency & Timing** — optimal schedule based on the data
5. **Hashtag Strategy** — which hashtag types and volumes to use
6. **5 Tailored Content Ideas** — specific video concepts for this business
7. **Key Metrics to Track** — KPIs and benchmarks to monitor progress

Be specific, data-driven, and actionable. Format as a structured marketing report."""

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
