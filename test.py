from fastapi import FastAPI
import pymysql
app = FastAPI()

def get_db_connection():
    return pymysql.connect(
        host="localhost",
        port=3307,
        user="root",
        password="123456",
        database="dzservice",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
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