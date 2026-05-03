import io
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from models.schemas import BusinessProfile

router = APIRouter()

business_profiles: dict = {}


@router.post("/profile")
async def save_business_profile(profile: BusinessProfile):
    try:
        business_profiles[profile.business_name] = profile.model_dump()
        return {
            "success": True,
            "message": "Business profile saved",
            "profile": profile.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-sales")
async def upload_sales_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")
    try:
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode("utf-8")))
        summary = {
            "filename": file.filename,
            "rows": len(df),
            "columns": list(df.columns),
            "preview": df.head(5).to_dict(orient="records"),
        }
        return {"success": True, "message": "Sales data uploaded successfully", "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
