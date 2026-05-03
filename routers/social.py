from fastapi import APIRouter, HTTPException
from models.schemas import SocialFetchRequest
from services.apify_service import fetch_social_media

router = APIRouter()

SUPPORTED_PLATFORMS = ("tiktok", "instagram", "x")


@router.post("/fetch")
async def fetch_social(request: SocialFetchRequest):
    platform = request.platform.lower().strip()

    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"منصة غير مدعومة: '{platform}'. الخيارات: {', '.join(SUPPORTED_PLATFORMS)}",
        )

    if not request.username.strip():
        raise HTTPException(status_code=400, detail="اسم الحساب مطلوب")

    try:
        result = await fetch_social_media(platform, request.username, request.limit)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ غير متوقع: {str(e)}")
