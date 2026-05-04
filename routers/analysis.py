import json
from fastapi import APIRouter, HTTPException
from models.schemas import AnalysisRequest
from services.analysis_pipeline import AnalysisPipeline

router = APIRouter()
pipeline = AnalysisPipeline()


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
