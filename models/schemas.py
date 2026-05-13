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
    sales_data: Optional[Any] = None
    transcripts: Optional[List[Dict[str, Any]]] = None
    competitor_accounts: Optional[List[Dict[str, Any]]] = None  # [{platform, username}]


class BusinessProfile(BaseModel):
    business_name: str
    industry: str
    target_audience: str
    goals: Optional[str] = None
    website: Optional[str] = None
