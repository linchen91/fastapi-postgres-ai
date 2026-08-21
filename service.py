from fastapi import FastAPI

app = FastAPI()

@app.get('/test')
def get_city():
    return{'test':'Hello, FastAPI!'}