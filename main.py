from core.security import get_current_user
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI, Depends
from routers import auth, user, device, role, event
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from api_io_log import ApiIOMiddleware

app = FastAPI()

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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
