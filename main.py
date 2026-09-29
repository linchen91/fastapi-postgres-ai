from contextlib import asynccontextmanager
from pathlib import Path
import warnings
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
from core.security import get_current_user
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI, Depends, Request
from sqlalchemy import select
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from routers import auth, user, device, role, event, ai_summary, traffic, news, ai_search
from routers.news import preload_cache
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from api_io_log import ApiIOMiddleware
from database import engine, Base, AsyncSessionLocal
from models.user import User
# Register all tables on Base.metadata (side-effect imports; must not shadow
# the router names user/device/role imported above)
import models.user, models.device, models.role, models.roledevice  # noqa: F401

ADMIN_ACCOUNT = 'admin'
# bcrypt hash of 'admin123' — replace before any real deployment
ADMIN_PWD_HASH = '$2b$12$8V10P4sVOhZ9UhTxyXIOFuEtb3.ZDEgW8JTqndVQKL/B5mlx34ggi'

STATIC_DIR = Path(__file__).parent / "static"
API_PATHS = ("/docs", "/redoc", "/openapi.json", "/auth", "/ai")


class SPAMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_api_call = any(path.startswith(p) for p in API_PATHS)
        if not is_api_call:
            file_path = STATIC_DIR / path.lstrip("/")
            if file_path.is_file():
                return FileResponse(file_path)
        # For browser page navigation (GET + Accept: text/html), always serve
        # index.html so React Router handles client-side routing.  This fixes
        # page-refresh 405 errors on SPA routes that share a prefix with API
        # paths (e.g. /ai/search).  Axios API calls use Accept: application/json
        # and pass through to the backend router unchanged.
        accept = request.headers.get("accept", "")
        if "text/html" in accept and request.method == "GET":
            index = STATIC_DIR / "index.html"
            if index.is_file():
                return HTMLResponse(content=index.read_text())
        return await call_next(request)

async def seed_admin():
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(User).where(User.Account == ADMIN_ACCOUNT)
        )
        if existing is None:
            session.add(User(
                Account=ADMIN_ACCOUNT,
                Name='Admin',
                Email='admin@example.com',
                Pwd=ADMIN_PWD_HASH,
                IsActive=True,
                RoleId=1,
            ))
            await session.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_admin()
    await preload_cache()
    yield
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

app.add_middleware(SPAMiddleware)

app.add_middleware(ApiIOMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)

app.include_router(auth.router)
app.include_router(user.router, prefix='/users', tags=['Users'], dependencies=[Depends(get_current_user)])
app.include_router(device.router, prefix='/devices', tags=['Devices'], dependencies=[Depends(get_current_user)])
app.include_router(role.router, prefix='/roles', tags=['Roles'], dependencies=[Depends(get_current_user)])
app.include_router(event.router, prefix='/events', tags=['Events'])
app.include_router(ai_summary.router, prefix='/ai', tags=['AI'], dependencies=[Depends(get_current_user)])
app.include_router(ai_search.router, prefix='/ai', tags=['AI'])
app.include_router(traffic.router, prefix='/ai/traffic', tags=['AI'], dependencies=[Depends(get_current_user)])
app.include_router(news.router, prefix='/news', tags=['News'])

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title = 'your API',
        version = '1.0.0',
        description = 'checked by JWT Token',
        routes = app.routes
    )
    openapi_schema['openapi'] = '3.1.0'
    openapi_schema['components']['securitySchemes'] = {
        'BearerAuth': {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT'
        }
    }
    for path in openapi_schema['paths'].values():
        for method in path.values():
            method['security'] = [{'BearerAuth': []}]
    app.openapi_schema = openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
