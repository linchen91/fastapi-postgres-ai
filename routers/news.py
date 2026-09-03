import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

router = APIRouter()

TRAFFIC_JSON_URL = 'https://www.br.de/verkehrskarte/verkehrsdaten/verkehrsmeldungen.json'
CACHE = TTLCache(maxsize=1, ttl=120)  # Cache for 2 minutes

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}


class TrafficMessage(BaseModel):
    id: str
    category: str
    category_id: str
    headline: str
    description: str
    time: str
    visualization: str
    lat: float
    lon: float
    both_directions: bool


class TrafficResponse(BaseModel):
    summary: str
    timestamp: str
    total: int
    messages: list[TrafficMessage]


async def _fetch_traffic_data() -> dict:
    async with httpx.AsyncClient(
        headers=HEADERS,
        verify=False,
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        res = await client.get(TRAFFIC_JSON_URL)
        res.raise_for_status()
        return res.json()


def _parse_messages(data: dict) -> list[TrafficMessage]:
    messages: list[TrafficMessage] = []
    for category in data.get('bmtKategorien', []):
        cat_title = category.get('titel', '')
        cat_id = category.get('kategorieId', '')
        for msg in category.get('meldungen', []):
            messages.append(TrafficMessage(
                id=msg.get('metasMeldungsID', ''),
                category=cat_title,
                category_id=cat_id,
                headline=msg.get('headline', ''),
                description='\n'.join(msg.get('absatz', [])),
                time=msg.get('meldungsZeit', ''),
                visualization=msg.get('visualisierung', ''),
                lat=msg.get('lat', 0.0),
                lon=msg.get('lon', 0.0),
                both_directions=msg.get('beideRichtungen', False),
            ))
    return messages


async def preload_cache():
    """Pre-warm the traffic cache at startup so the first request is instant."""
    try:
        raw = await _fetch_traffic_data()
        messages = _parse_messages(raw)
        result = TrafficResponse(
            summary=raw.get('verkehrslageHinweis', ''),
            timestamp=raw.get('exportZeitstempel', ''),
            total=len(messages),
            messages=messages,
        )
        CACHE['data'] = result
        logger.info('Traffic cache pre-warmed: %d messages', len(messages))
    except Exception:
        logger.warning('Traffic cache pre-warm failed — first request will fetch live', exc_info=True)


@router.get('/')
async def get_traffic(force: bool = Query(default=False)):
    if not force and 'data' in CACHE:
        data = CACHE['data'].model_dump()
    else:
        try:
            raw = await _fetch_traffic_data()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f'Failed to fetch traffic data: {e}')

        messages = _parse_messages(raw)
        result = TrafficResponse(
            summary=raw.get('verkehrslageHinweis', ''),
            timestamp=raw.get('exportZeitstempel', ''),
            total=len(messages),
            messages=messages,
        )
        CACHE['data'] = result
        data = result.model_dump()

    return JSONResponse(
        content=data,
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        },
    )
