import os, time, datetime, logging
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, f'{datetime.date.today().isoformat()}.log')

logger = logging.getLogger('api-io')
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
    logger.addHandler(fh)

def _is_textual(ct: str) -> bool:
    ct = (ct or '').lower()
    return ('application/json' in ct) or ct.startswith('text/') or ct.endswith('+json')

class ApiIOMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        skip_paths: Optional[set[str]] = None,
        skip_html: bool = True
    ):
        super().__init__(app)
        self.skip_paths = skip_paths or {
            '/docs',
            '/redoc',
            '/openapi.json',
            '/docs/oauth2-redirect',
            '/favicon.ico'
        }
        self.skip_html = skip_html

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.skip_paths or request.method == 'OPTIONS':
            return await call_next(request)

        t0 = time.perf_counter()
        req_ct = request.headers.get('content-type', '')
        raw_req = await request.body()
        if _is_textual(req_ct):
            req_log = raw_req.decode('utf-8', errors='replace')
        else:
            req_log = f'<{len(raw_req)} bytes binary>'

        async def _receive():
            return {'type': 'http.request', 'body': raw_req, 'more_body': False}
        request._receive = _receive

        response: Response = await call_next(request)
        raw_resp =b''
        async for chunk in response.body_iterator:
            raw_resp += chunk

        resp_ct = (response.headers.get('content-type') or response.media_type or '').lower()
        if self.skip_html and 'text/html' in resp_ct:
            return Response(
                content=raw_resp,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        if _is_textual(resp_ct):
            resp_log = raw_resp.decode('utf-8', errors='replace')
        else:
            resp_log = f'<{len(raw_resp)} bytes binary>'

        dt_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            '%s %s - %d (%d ms) | reqCT=%s | respCT=%s | req=%s | resp=%s',
            request.method, request.url.path, response.status_code, dt_ms,
            req_ct, resp_ct, req_log, resp_log
        )

        return Response(
            content=raw_resp,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )