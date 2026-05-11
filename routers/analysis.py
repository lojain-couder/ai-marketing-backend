import logging
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from models.schemas import AnalysisRequest
from services.analysis_pipeline import AnalysisPipeline
from services.groq_writer import GroqWriter

_GROQ_ERRORS = {
    "groq_quota_exhausted": (429, "انتهى رصيد Groq API — يرجى إضافة رصيد على console.groq.com"),
    "groq_auth_error":      (401, "مفتاح Groq API غير صالح — تحقق من GROQ_API_KEY"),
}

def _handle_groq_error(e: Exception, fallback_msg: str) -> None:
    msg = str(e)
    if msg in _GROQ_ERRORS:
        status, detail = _GROQ_ERRORS[msg]
        raise HTTPException(status_code=status, detail=detail)
    if msg.startswith("groq_api_error_"):
        raise HTTPException(status_code=502, detail=f"خطأ في Groq API — {msg}")
    raise HTTPException(status_code=500, detail=fallback_msg)

logger = logging.getLogger(__name__)

router = APIRouter()
pipeline = AnalysisPipeline()
groq = GroqWriter()


class SalesInsightsRequest(BaseModel):
    sales_data: dict = {}
    social_metrics: dict = {}
    business_profile: dict = {}


class StarterPlanRequest(BaseModel):
    business_profile: dict


class RegenerateHookRequest(BaseModel):
    original: dict
    business_profile: dict
    feedback: str = ""
    dislike_reason: str = ""
    liked_examples: list[dict] = []


@router.post("/run")
async def run_analysis(request: AnalysisRequest):
    if not request.videos:
        raise HTTPException(status_code=400, detail="لا توجد فيديوهات للتحليل")

    try:
        normalized = {
            "business_profile": request.business_profile or {},
            "sales_summary":    request.sales_data,
            "videos":           request.videos,
            "transcripts":      request.transcripts or [],
        }
        result = await run_in_threadpool(pipeline.run, normalized)
        return {"success": True, **jsonable_encoder(result)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("run_analysis failed: %s", e, exc_info=True)
        _handle_groq_error(e, "حدث خطأ أثناء التحليل — حاولي مرة ثانية")


@router.post("/starter-plan")
async def starter_plan(req: StarterPlanRequest):
    if not req.business_profile:
        raise HTTPException(status_code=400, detail="يجب إدخال معلومات البزنس")
    try:
        result = await run_in_threadpool(groq.generate_starter_plan, req.business_profile)
        if not result:
            raise HTTPException(status_code=500, detail="تعذّر إنشاء الخطة — حاولي مرة ثانية")
        return {"success": True, **jsonable_encoder(result)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("starter_plan failed: %s", e, exc_info=True)
        _handle_groq_error(e, "تعذّر إنشاء الخطة — حاولي مرة ثانية")


@router.post("/regenerate-hook")
async def regenerate_hook(req: RegenerateHookRequest):
    if not req.original or not req.business_profile:
        raise HTTPException(status_code=400, detail="بيانات ناقصة")
    try:
        result = await run_in_threadpool(
            groq.regenerate_hook,
            req.original,
            req.business_profile,
            req.feedback,
            req.dislike_reason,
            req.liked_examples,
        )
        if not result:
            raise HTTPException(status_code=500, detail="تعذّر توليد بديل — حاولي مرة ثانية")
        return {"success": True, **jsonable_encoder(result)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("regenerate_hook failed: %s", e, exc_info=True)
        _handle_groq_error(e, "تعذّر توليد بديل — حاولي مرة ثانية")


@router.post("/sales-insights")
async def sales_insights(req: SalesInsightsRequest):
    if not req.sales_data and not req.social_metrics:
        raise HTTPException(status_code=400, detail="لا توجد بيانات لتحليلها")
    try:
        result = await run_in_threadpool(
            groq.analyze_sales_with_social,
            req.sales_data,
            req.social_metrics,
            req.business_profile,
        )
        return {"success": True, **jsonable_encoder(result)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("sales_insights failed: %s", e, exc_info=True)
        _handle_groq_error(e, "تعذّر تحليل المبيعات — حاولي مرة ثانية")
