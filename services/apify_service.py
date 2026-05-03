import os
import httpx
from typing import Optional

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
ACTOR_ID = "clockworks~free-tiktok-scraper"


async def fetch_tiktok_videos(
    hashtag: Optional[str] = None,
    username: Optional[str] = None,
    max_items: int = 20,
):
    url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"

    run_input: dict = {"maxItems": max_items}
    if hashtag:
        run_input["hashtags"] = [hashtag]
    if username:
        run_input["profiles"] = [username]

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            url,
            json=run_input,
            params={"token": APIFY_TOKEN},
        )
        response.raise_for_status()
        return response.json()
