import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from urllib.parse import quote_plus

# username = os.getenv('MYSQL_USER', 'dzuser')
# password = quote_plus(os.getenv('MYSQL_PASSWORD', 'L@12345678'))
# host = os.getenv('MYSQL_HOST', 'localhost')
# port = os.getenv('MYSQL_PORT', '3307')
# db = os.getenv('MYSQL_DB', 'dzservice')

# DATABASE_URL = f'mysql+pymysql://{username}:{password}@{host}:{port}/{db}'

username = os.getenv('POSTGRES_USER', 'postgres')
password = quote_plus(os.getenv('POSTGRES_PASSWORD', '123456'))
host = os.getenv('POSTGRES_HOST', 'localhost')
port = os.getenv('POSTGRES_PORT', '5432')
db = os.getenv('POSTGRES_DB', 'dzservice')

DATABASE_URL = f'postgresql+asyncpg://{username}:{password}@{host}:{port}/{db}'

DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '10'))
DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '20'))
DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '30'))
DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', '1800'))
DB_ECHO = os.getenv('DB_ECHO', 'true').lower() in ('1', 'true', 'yes')

engine = create_async_engine(
    DATABASE_URL,
    echo=DB_ECHO,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db