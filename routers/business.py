import io
import logging
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from models.schemas import BusinessProfile
from services.groq_writer import GroqWriter

logger = logging.getLogger(__name__)
_groq  = GroqWriter()
router = APIRouter()

_ALLOWED_EXT   = (".csv", ".xlsx", ".xls")
_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1256", "latin-1")


# ── Profile endpoint (stateless — client owns the state) ─────────────────────

@router.post("/profile")
async def save_business_profile(profile: BusinessProfile):
    """Validate and echo the profile back. State lives on the client."""
    try:
        return {"success": True, "message": "تم حفظ البروفايل", "profile": profile.model_dump()}
    except Exception as e:
        logger.error("save_business_profile failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="تعذّر حفظ البروفايل")


# ── CSV / Excel helpers ───────────────────────────────────────────────────────

def _read_dataframe(contents: bytes, filename: str) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(contents))
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(io.StringIO(contents.decode(enc)))
        except (UnicodeDecodeError, Exception):
            continue
    raise ValueError("تعذّر قراءة الملف — تأكد أنه CSV أو Excel صحيح")


def _apply_column_mapping(df: pd.DataFrame, col_map: dict[str, str]) -> pd.DataFrame:
    rename = {orig: std for std, orig in col_map.items() if orig in df.columns}
    return df.rename(columns=rename) if rename else df


def _detect_outliers(df: pd.DataFrame, col_map: dict[str, str]) -> list[dict]:
    rev_col  = col_map.get("revenue")
    date_col = col_map.get("order_date")
    if not rev_col or rev_col not in df.columns:
        return []
    try:
        values = pd.to_numeric(df[rev_col], errors="coerce").dropna()
    except Exception:
        return []
    if len(values) < 5:
        return []
    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return []
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = []
    for idx, row in df.iterrows():
        val = pd.to_numeric(row.get(rev_col), errors="coerce")
        if pd.isna(val):
            continue
        if val > upper or val < lower:
            date      = str(row.get(date_col, "")) if date_col else ""
            direction = "ارتفاع مفاجئ" if val > upper else "انخفاض مفاجئ"
            pct       = round(abs(val - float(values.mean())) / float(values.mean()) * 100)
            outliers.append({
                "date":      date,
                "value":     round(float(val), 2),
                "mean":      round(float(values.mean()), 2),
                "direction": direction,
                "pct_diff":  pct,
                "question": (
                    f"{direction} في المبيعات بتاريخ {date or 'غير محدد'} "
                    f"({pct}% {'أعلى' if val > upper else 'أقل'} من المعدل) — "
                    "هل كان هناك حدث خاص أو عرض أو كامبين في هذا الوقت؟"
                ),
            })
            if len(outliers) >= 5:
                break
    return outliers


def _process_upload(contents: bytes, fname: str) -> dict:
    """CPU-bound work extracted so it can run in a threadpool."""
    df = _read_dataframe(contents, fname)
    sample_rows = df.head(20).to_dict(orient="records")

    col_map  = _groq.map_csv_columns(columns=list(df.columns), sample_rows=sample_rows[:3])
    df_norm  = _apply_column_mapping(df, col_map)
    rows_normalized = df_norm.head(20).to_dict(orient="records")

    numeric_summary: dict = {}
    for col in df_norm.select_dtypes(include="number").columns:
        numeric_summary[col] = {
            "sum":  round(float(df_norm[col].sum()), 2),
            "mean": round(float(df_norm[col].mean()), 2),
            "max":  round(float(df_norm[col].max()), 2),
        }

    outliers       = _detect_outliers(df, {"revenue": col_map.get("revenue"), "order_date": col_map.get("order_date")})
    csv_insights   = _groq.analyze_csv_sales(columns=list(df.columns), sample_rows=sample_rows, numeric_summary=numeric_summary)
    monthly_revenue = numeric_summary.get("revenue", {}).get("sum")

    return {
        "filename":        fname,
        "rows":            len(df),
        "columns":         list(df.columns),
        "col_map":         col_map,
        "preview":         rows_normalized,
        "csv_insights":    csv_insights,
        "outliers":        outliers,
        "monthly_revenue": monthly_revenue,
        "orders":          len(df) if monthly_revenue else None,
    }


# ── Upload endpoint ───────────────────────────────────────────────────────────

@router.post("/upload-sales")
async def upload_sales_csv(file: UploadFile = File(...)):
    fname = file.filename or ""
    if not any(fname.lower().endswith(ext) for ext in _ALLOWED_EXT):
        raise HTTPException(status_code=400, detail="الملف غير مدعوم — ارفع ملف CSV أو Excel (xlsx)")
    try:
        contents = await file.read()
        summary  = await run_in_threadpool(_process_upload, contents, fname)
        return {"success": True, "message": "تم رفع الملف بنجاح", "summary": jsonable_encoder(summary)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("upload_sales_csv failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="تعذّر معالجة الملف — تأكد من صحة البيانات")
