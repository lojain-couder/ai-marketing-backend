from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routers import tiktok, analysis, business

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
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"])
app.include_router(business.router, prefix="/api/business", tags=["Business"])


@app.get("/")
def root():
    return {"message": "AI Marketing Strategist API is running", "docs": "/docs"}
