from fastapi import FastAPI
from routers import user
import uvicorn

app = FastAPI()

app.include_router(user.router, prefix='/users', tags=['Users'])

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
