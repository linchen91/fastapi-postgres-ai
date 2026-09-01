from multiprocessing import active_children
from fastapi import APIRouter, HTTPException
import os, httpx, datetime

router = APIRouter()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = os.getenv("OPENROUTER_URL")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")

def build_messages(stats: dict):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    system = (
        'You are a helpful assistant that summarizes text. '
        'You will receive a text input and your task is to provide a concise summary of the content. '
    )
    
    # based on the stats, we can customize the prompt further if needed
    device_count = stats.get("deviceCount", 0)
    active_count = stats.get("activeCount", 0)
    error_count = stats.get("errorCount", 0)
    offline_count = stats.get("offlineCount", 0)
    
    rec_updates = stats.get("RecUpdDevices", [])
    updates_str = "\n".join(
        [f"- {d['Name']} status {d['Status']} updated Date {d['UpdatedDate']}" for d in rec_updates]
        ) if rec_updates else "No devices require updates."

    user = (
        f"Today is {today}. Here are the device statistics:\n"
        f"- Total devices: {device_count}\n"
        f"- Active devices: {active_count}\n"
        f"- Devices with errors: {error_count}\n"
        f"- Offline devices: {offline_count}\n"
        f"Devices that require updates:\n{updates_str}\n\n"
        "Please provide a concise summary of the above information."
    )

    return [
        {"role": "system", "content": system},  
        {"role": "user", "content": user}
    ]
    
@router.post("/summary")
async def ai_summary(payload: dict):
    if not OPENROUTER_API_KEY or not OPENROUTER_URL or not OPENROUTER_MODEL:
        raise HTTPException(status_code=500, detail="OpenRouter API configuration is missing.")

    stats = payload.get('stats')
    if not stats:
        raise HTTPException(status_code=400, detail="Missing 'stats' in request payload.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",  # Example referrer, adjust as needed
        "X-Title": "AI Summary Request"  # Example title, adjust as needed
    }

    data = {
        'model': OPENROUTER_MODEL,
        'messages': build_messages(stats),
        'temperature': 0.2
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(OPENROUTER_URL, headers=headers, json=data)

        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Error from OpenRouter API.")

        j = r.json()
        content = j["choices"][0]["message"]["content"]

        return {"summary": content}
