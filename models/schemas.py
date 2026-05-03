from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class TikTokFetchRequest(BaseModel):
    hashtag: Optional[str] = None
    username: Optional[str] = None
    max_items: int = 50


class SocialFetchRequest(BaseModel):
    platform: str  # tiktok | instagram | x
    username: str
    limit: int = 50


class AnalysisRequest(BaseModel):
    videos: List[Dict[str, Any]]
    business_profile: Optional[Dict[str, Any]] = None


class BusinessProfile(BaseModel):
    business_name: str
    industry: str
    target_audience: str
    goals: Optional[str] = None
    website: Optional[str] = None
