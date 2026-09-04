import os, time, datetime, logging
from typing import Optional

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

class ApiIOMiddleware:
    """Raw ASGI middleware — does NOT consume or recreate the response,
    so it cannot interfere with CORSMiddleware or any other middleware."""

    def __init__(
        self,
        app,
        *,
        skip_paths: Optional[set[str]] = None,
        skip_html: bool = True
    ):
        self.app = app
        self.skip_paths = skip_paths or {
            '/docs',
            '/redoc',
            '/openapi.json',
            '/docs/oauth2-redirect',
            '/favicon.ico'
        }
        self.skip_html = skip_html

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        if path in self.skip_paths or method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        t0 = time.perf_counter()

        # --- read full request body --------------------------------
        raw_req = b""
        while True:
            msg = await receive()
            raw_req += msg.get("body", b"")
            if not msg.get("more_body", False):
                break

        req_ct = scope.get("headers", [])
        req_ct_val = ""
        for k, v in req_ct:
            if k == b"content-type":
                req_ct_val = v.decode("utf-8", errors="replace")
                break

        if _is_textual(req_ct_val):
            req_log = raw_req.decode("utf-8", errors="replace")
        else:
            req_log = f"<{len(raw_req)} bytes binary>"

        # Re-yield request body so the downstream app can read it
        async def receive_body():
            return {"type": "http.request", "body": raw_req, "more_body": False}

        # --- wrap send() to capture response headers + body ----------
        resp_status = 200
        resp_headers_raw: list[tuple[bytes, bytes]] = []
        resp_body = b""

        original_send = send

        async def logging_send(message):
            nonlocal resp_status, resp_headers_raw, resp_body
            if message["type"] == "http.response.start":
                resp_status = message["status"]
                resp_headers_raw = message.get("headers", [])
                await original_send(message)
            elif message["type"] == "http.response.body":
                resp_body += message.get("body", b"")
                await original_send(message)
            else:
                await original_send(message)

        # --- call downstream app (headers are NEVER touched) ---------
        await self.app(scope, receive_body, logging_send)

        # --- log ----------------------------------------------------
        resp_ct = b""
        for k, v in resp_headers_raw:
            if k == b"content-type":
                resp_ct = v
                break
        resp_ct_str = resp_ct.decode("utf-8", errors="replace").lower()

        if self.skip_html and "text/html" in resp_ct_str:
            return

        if _is_textual(resp_ct_str):
            resp_log = resp_body.decode("utf-8", errors="replace")
        else:
            resp_log = f"<{len(resp_body)} bytes binary>"

        dt_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "%s %s - %d (%d ms) | reqCT=%s | respCT=%s | req=%s | resp=%s",
            method, path, resp_status, dt_ms,
            req_ct_val, resp_ct_str, req_log, resp_log
        )
