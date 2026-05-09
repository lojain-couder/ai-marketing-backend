import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from models.schemas import AnalysisRequest
from services.analysis_pipeline import AnalysisPipeline
from services.groq_writer import GroqWriter

router = APIRouter()
pipeline = AnalysisPipeline()
groq = GroqWriter()


class SalesInsightsRequest(BaseModel):
    sales_data: dict = {}
    social_metrics: dict = {}
    business_profile: dict = {}


class StarterPlanRequest(BaseModel):
    business_profile: dict


@router.post("/run")
async def run_analysis(request: AnalysisRequest):
    """
    Pipeline:
    1. Convert frontend video format → SocialAnalysisEngine format
    2. Rule-based engines produce structured insights, strategies, weekly plan
    3. Groq writing layer enriches language only — does NOT change decisions
    4. Return final output
    """
    if not request.videos:
        raise HTTPException(status_code=400, detail="لا توجد فيديوهات للتحليل")

    try:
        normalized = {
            "business_profile": request.business_profile or {},
            "sales_summary": None,
            "videos": request.videos,
        }
        result = pipeline.run(normalized)
        safe = json.loads(json.dumps(result, default=str))
        return {"success": True, **safe}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/starter-plan")
async def starter_plan(req: StarterPlanRequest):
    if not req.business_profile:
        raise HTTPException(status_code=400, detail="يجب إدخال معلومات البزنس")
    try:
        result = groq.generate_starter_plan(req.business_profile)
        if not result:
            raise HTTPException(status_code=500, detail="تعذّر إنشاء الخطة — حاولي مرة ثانية")
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sales-insights")
async def sales_insights(req: SalesInsightsRequest):
    if not req.sales_data and not req.social_metrics:
        raise HTTPException(status_code=400, detail="لا توجد بيانات لتحليلها")
    try:
        result = groq.analyze_sales_with_social(
            req.sales_data,
            req.social_metrics,
            req.business_profile,
        )
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
