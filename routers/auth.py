from fastapi import APIRouter, Depends, HTTPException, Body
from schemas.user import LoginRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.user import User
from core import security

router = APIRouter(prefix='/auth', tags=['Auth'])

@router.post('/token')
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.Account == data.account))
    user = result.scalars().first()
    if not user or not security.verif_password(data.password, user.Pwd):
        raise HTTPException(status_code=400, detail='Account or Password error')
    if user.IsActive == 0:
        raise HTTPException(status_code=400, detail='Account is inactive')
    token = security.create_access_token({'sub': user.Account})
    return {'access_token': token, 'token_type': 'bearer'}

@router.post('/hashpwd')
def hash_password(password: str = Body(..., embed=True)):
    hashed = security.get_password_hash(password)
    return {'hashed_password': hashed}
