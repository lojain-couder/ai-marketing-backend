from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os

load_dotenv()

from routers import tiktok, analysis, business, social, comments, assistant, transcription

app = FastAPI(
    title="AI Marketing Strategist API",
    description="Backend for AI-powered TikTok marketing analysis",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tiktok.router, prefix="/api/tiktok", tags=["TikTok"])
app.include_router(social.router, prefix="/api/social", tags=["Social"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"])
app.include_router(business.router, prefix="/api/business", tags=["Business"])
app.include_router(comments.router, prefix="/api/comments", tags=["Comments"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["Assistant"])
app.include_router(transcription.router, prefix="/api/transcription", tags=["Transcription"])

# Serve mudar-platform as the frontend (must come last)
frontend_dir = os.path.join(os.path.dirname(__file__), "mudar-platform")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
