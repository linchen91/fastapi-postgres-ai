import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from urllib.parse import quote_plus

username = os.getenv('MYSQL_USER', 'dzuser')
password = quote_plus(os.getenv('MYSQL_PASSWORD', 'L@12345678'))
host = os.getenv('MYSQL_HOST', 'localhost')
port = os.getenv('MYSQL_PORT', '3307')
db = os.getenv('MYSQL_DB', 'dzservice')

DATABASE_URL = f'mysql+pymysql://{username}:{password}@{host}:{port}/{db}'

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

