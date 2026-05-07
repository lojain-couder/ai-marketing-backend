from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.groq_writer import GroqWriter

router = APIRouter()
writer = GroqWriter()


class ChatRequest(BaseModel):
    message: str
    context: dict = {}
    history: list[dict] = []


@router.post("/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="الرسالة فارغة")
    try:
        reply = writer.chat(req.message, req.context, req.history)
        return {"success": True, "reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
