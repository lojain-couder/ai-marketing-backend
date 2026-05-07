import io
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from models.schemas import BusinessProfile
from services.groq_writer import GroqWriter

_groq = GroqWriter()

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
        rows_preview = df.head(20).to_dict(orient="records")

        # Derive quick numeric summary for Groq
        numeric_summary: dict = {}
        for col in df.select_dtypes(include="number").columns:
            numeric_summary[col] = {
                "sum": round(float(df[col].sum()), 2),
                "mean": round(float(df[col].mean()), 2),
                "max": round(float(df[col].max()), 2),
            }

        csv_insights = _groq.analyze_csv_sales(
            columns=list(df.columns),
            sample_rows=rows_preview,
            numeric_summary=numeric_summary,
        )

        summary = {
            "filename": file.filename,
            "rows": len(df),
            "columns": list(df.columns),
            "preview": rows_preview[:5],
            "csv_insights": csv_insights,
        }
        return {"success": True, "message": "Sales data uploaded successfully", "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
