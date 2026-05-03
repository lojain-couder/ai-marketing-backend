from fastapi import APIRouter, HTTPException
from models.schemas import TikTokFetchRequest
from services.apify_service import fetch_tiktok_videos

router = APIRouter()


@router.post("/fetch")
async def fetch_tiktok(request: TikTokFetchRequest):
    if not request.hashtag and not request.username:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: hashtag or username",
        )
    try:
        videos = await fetch_tiktok_videos(
            hashtag=request.hashtag,
            username=request.username,
            max_items=request.max_items,
        )
        return {"success": True, "videos": videos, "count": len(videos)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ غير متوقع: {str(e)}")
