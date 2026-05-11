import logging
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from services.apify_service import fetch_comments
from services.groq_writer import GroqWriter

logger = logging.getLogger(__name__)
router = APIRouter()
groq = GroqWriter()


class CommentsRequest(BaseModel):
    platform: str
    video_urls: list[str]
    captions: list[str] = []
    business_profile: dict = {}
    max_per_video: int = 50


@router.post("/fetch")
async def fetch_and_analyze_comments(req: CommentsRequest):
    if not req.video_urls and not req.captions:
        raise HTTPException(status_code=400, detail="يجب تحديد روابط الفيديوهات أو الكابشن")

    # Try to fetch real comments from Apify
    comments = []
    if req.video_urls:
        try:
            comments = await fetch_comments(req.platform, req.video_urls, req.max_per_video)
            print(f"[Comments] Apify returned {len(comments)} real comments")
        except Exception as e:
            print(f"[Comments] Apify fetch failed: {e}")

    # Analyze real comments if available
    if comments:
        analysis = await run_in_threadpool(groq.analyze_real_comments, comments, req.business_profile)
        has_useful_data = analysis and (
            analysis.get("frequent_questions") or analysis.get("product_requests")
        )
        if has_useful_data:
            return {"success": True, "comments_count": len(comments), "source": "real", "analysis": analysis}
        logger.info("[Comments] %d comments — no useful text, falling back to captions", len(comments))

    captions = req.captions or []
    if not captions:
        raise HTTPException(status_code=404, detail="تعذّر جلب التعليقات — الفيديوهات محمية على TikTok")

    analysis = await run_in_threadpool(groq.analyze_audience_from_captions, captions, req.business_profile)
    if not analysis:
        raise HTTPException(status_code=500, detail="تعذّر التحليل — حاولي مرة ثانية")

    return {"success": True, "comments_count": 0, "source": "estimated", "analysis": analysis}
