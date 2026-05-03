from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class TikTokFetchRequest(BaseModel):
    hashtag: Optional[str] = None
    username: Optional[str] = None
    max_items: int = 20


class AnalysisRequest(BaseModel):
    videos: List[Dict[str, Any]]
    business_profile: Optional[Dict[str, Any]] = None


class BusinessProfile(BaseModel):
    business_name: str
    industry: str
    target_audience: str
    goals: Optional[str] = None
    website: Optional[str] = None
