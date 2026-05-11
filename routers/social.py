import io
import logging
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from models.schemas import SocialFetchRequest
from services.apify_service import fetch_social_media

logger = logging.getLogger(__name__)
router = APIRouter()

SUPPORTED_PLATFORMS = ("tiktok", "instagram", "x")

# ── Column aliases for TikTok Creator Studio exports (Arabic + English) ───────
_VIEW_KEYS     = {"views","video views","videoviews","play count","playcount",
                  "مشاهدات","مشاهدة","بث"}
_LIKE_KEYS     = {"likes","like count","likecount","digg count","diggcount",
                  "إعجابات","لايكات","اعجابات"}
_COMMENT_KEYS  = {"comments","comment count","commentcount","تعليقات"}
_SHARE_KEYS    = {"shares","share count","sharecount","مشاركات","مشاركة"}
_CAPTION_KEYS  = {"caption","description","video description","title",
                  "video title","text","content","الوصف","العنوان","الكابشن",
                  "وصف الفيديو","محتوى"}
_DATE_KEYS     = {"date","posted","date posted","created","date created",
                  "publish date","التاريخ","تاريخ النشر"}


def _find_col(cols_lower: dict, aliases: set) -> str | None:
    """Return the original column name whose lowercase form matches any alias."""
    for orig, low in cols_lower.items():
        if low in aliases:
            return orig
    return None


def _safe_int(val) -> int:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0
    try:
        return int(str(val).replace(",", "").replace("،", "").strip())
    except Exception:
        return 0


def _parse_tiktok_df(df: pd.DataFrame) -> list[dict]:
    cols_lower = {c: c.strip().lower() for c in df.columns}

    c_views    = _find_col(cols_lower, _VIEW_KEYS)
    c_likes    = _find_col(cols_lower, _LIKE_KEYS)
    c_comments = _find_col(cols_lower, _COMMENT_KEYS)
    c_shares   = _find_col(cols_lower, _SHARE_KEYS)
    c_caption  = _find_col(cols_lower, _CAPTION_KEYS)
    c_date     = _find_col(cols_lower, _DATE_KEYS)

    posts = []
    for i, row in df.iterrows():
        views = _safe_int(row[c_views])    if c_views    else 0
        likes = _safe_int(row[c_likes])    if c_likes    else 0
        coms  = _safe_int(row[c_comments]) if c_comments else 0
        shs   = _safe_int(row[c_shares])   if c_shares   else 0
        cap   = str(row[c_caption]).strip() if c_caption else ""
        date  = str(row[c_date]).strip()    if c_date    else ""
        if cap in ("nan", "None", ""):
            cap = f"فيديو {i + 1}"
        posts.append({
            "id":        str(i),
            "url":       "",
            "views":     views,
            "likes":     likes,
            "comments":  coms,
            "shares":    shs,
            "caption":   cap,
            "posted_at": date,
            "duration":  0,
        })
    return posts


_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1256", "latin-1")


def _read_df(contents: bytes, filename: str) -> pd.DataFrame:
    low = filename.lower()
    if low.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(contents))
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(io.StringIO(contents.decode(enc)))
        except (UnicodeDecodeError, Exception):
            continue
    raise ValueError("تعذّر قراءة الملف")


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
        msg = str(e)
        if "not-enough-usage" in msg or "paid-actor" in msg or "exceed" in msg.lower():
            raise HTTPException(
                status_code=402,
                detail="رصيد Apify غير كافٍ لجلب البيانات تلقائياً — أضف رصيداً على apify.com/billing أو ارفع بياناتك يدوياً من TikTok Studio"
            )
        raise HTTPException(status_code=502, detail=msg)
    except Exception as e:
        logger.error("fetch_social failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ غير متوقع — حاولي مرة ثانية")


@router.post("/parse-csv")
async def parse_social_csv(file: UploadFile = File(...)):
    """Parse a TikTok Creator Studio CSV/Excel export into the standard posts schema."""
    fname = file.filename or "data.csv"
    if not any(fname.lower().endswith(ext) for ext in (".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="ارفع ملف CSV أو Excel من TikTok Studio")

    try:
        contents = await file.read()
        df = _read_df(contents, fname)

        if df.empty:
            raise HTTPException(status_code=400, detail="الملف فارغ")

        posts = _parse_tiktok_df(df)
        if not posts:
            raise HTTPException(status_code=400, detail="لم يتم العثور على بيانات في الملف")

        for p in posts:
            p["platform"] = "tiktok"

        return {
            "success":  True,
            "platform": "tiktok",
            "username": "",
            "posts":    posts,
            "count":    len(posts),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("parse_social_csv failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="تعذّر قراءة الملف — تأكد من صحة الملف")
