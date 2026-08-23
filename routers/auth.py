from fastapi import APIRouter, Depends, HTTPException, Body
from schemas.user import LoginRequest
from sqlalchemy.orm import Session
from database import SessionLocal
from models.user import User
from core import security
from database import get_db

router = APIRouter(prefix='/auth', tags=['Auth'])

@router.post('/token')
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.Account == data.account).first()
    if not user or not security.verif_password(data.password, user.Pwd):
        raise HTTPException(status_code=400, detail='Account or Password error')
    token = security.create_access_token({'sub': user.Account})
    return {'access_token': token, 'token_type': 'bearer'}

@router.post('/hashpwd')
def hash_password(password: str = Body(..., embed=True)):
    hashed = security.get_password_hash(password)
    return {'hashed_password': hashed}
