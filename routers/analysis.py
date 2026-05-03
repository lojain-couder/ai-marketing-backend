from fastapi import APIRouter, HTTPException
from models.schemas import AnalysisRequest
from services.analysis_service import analyze_tiktok_videos

router = APIRouter()


@router.post("/run")
async def run_analysis(request: AnalysisRequest):
    if not request.videos:
        raise HTTPException(status_code=400, detail="No videos provided for analysis")
    try:
        result = analyze_tiktok_videos(
            videos=request.videos,
            business_profile=request.business_profile,
        )
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
