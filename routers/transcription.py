import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from typing import List
from services.groq_writer import GroqWriter

logger = logging.getLogger(__name__)
router = APIRouter()
groq = GroqWriter()

MAX_FILE_SIZE = 24 * 1024 * 1024  # 24 MB — Groq Whisper limit is 25 MB

SUPPORTED_EXTENSIONS = {
    ".mp4", ".mp3", ".m4a", ".wav", ".webm",
    ".ogg", ".flac", ".mpeg", ".mpga",
}


def _transcribe_file(file_bytes: bytes, filename: str) -> dict:
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(f"الملف '{filename}' أكبر من 24MB — قصّري الفيديو أو اضغطيه")

    transcript = groq.transcribe_audio(file_bytes, filename)
    if not transcript or not transcript.strip():
        raise ValueError(f"تعذّر استخراج الصوت من '{filename}'")

    elements = groq.extract_spoken_elements(transcript)
    return {
        "filename": filename,
        "transcript": transcript.strip(),
        **elements,
    }


@router.post("/upload")
async def transcribe_videos(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="لم يتم رفع أي ملفات")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="الحد الأقصى 10 ملفات في المرة الواحدة")

    results = []
    errors = []

    for f in files:
        fname = f.filename or "video"
        ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in SUPPORTED_EXTENSIONS:
            errors.append({"filename": fname, "error": f"نوع الملف غير مدعوم — استخدمي mp4، mp3، m4a، wav"})
            continue
        try:
            file_bytes = await f.read()
            result = await run_in_threadpool(_transcribe_file, file_bytes, fname)
            results.append(result)
        except ValueError as e:
            errors.append({"filename": fname, "error": str(e)})
        except Exception as e:
            logger.error("transcribe_videos failed for %s: %s", fname, e, exc_info=True)
            errors.append({"filename": fname, "error": f"تعذّر معالجة '{fname}' — حاولي مرة ثانية"})

    if not results and errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    return {
        "success": True,
        "count": len(results),
        "transcriptions": results,
        "errors": errors,
    }
