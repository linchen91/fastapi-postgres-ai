from fastapi import FastAPI
import psycopg2
import psycopg2.cursors

app = FastAPI()

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="123456",
        database="dzservice",
        cursor_factory=psycopg2.cursors.RealDictCursor
    )

@app.get("/")
async def read_root():
    return {"Message": "Hello FastApi"}

@app.get("/users")
async def read_users():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM users LIMIT 10"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()
