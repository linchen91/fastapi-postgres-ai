from fastapi import status
from database import username
import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from models.user import User

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def verif_password(plain_pwd, hashed_pwd):
    try:
        return bcrypt.checkpw(plain_pwd.encode('utf-8'), hashed_pwd.encode('utf-8'))
    except (ValueError, TypeError):
        return False

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({'exp': expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    return jwt.decode(token, SECRET_KEY, algorithm=[ALGORITHM])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/token')

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    try:
        payload = decode_token(token)
        username = payload.get('sub')
        if username is None:
            raise HTTPException(status_code=401, detail='Token invalid')
        user = db.query(User).filter(User.Account == username).first()
        if user is None:
            raise HTTPException(status_code=401, detail='User not found')
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail='Token check failed')
