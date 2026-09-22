from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from crud import user as crud_user
from schemas import user as schemas_user

router = APIRouter()

@router.get('/', response_model=list[schemas_user.UserOut])
async def read_users(db: AsyncSession = Depends(get_db)):
    return await crud_user.get_users(db)

@router.get('/{user_id}', response_model=schemas_user.UserOut)
async def read_user(user_id:int, db: AsyncSession = Depends(get_db)):
    user =  await crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return user

@router.post('/', response_model=schemas_user.UserOut)
async def create_user(user: schemas_user.UserCreate, db: AsyncSession = Depends(get_db)):
    return await crud_user.create_user(db, user)

@router.put('/{user_id}', response_model=schemas_user.UserOut)
async def update_user(user_id:int, user: schemas_user.UserUpdate, db: AsyncSession = Depends(get_db)):
    updated = await crud_user.update_user(db, user_id, user)
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    return updated

@router.delete('/{user_id}')
async def delete_user(user_id:int, db: AsyncSession = Depends(get_db)):
    deleted = await crud_user.delete_user(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='User not found')
    return {'message': 'User deleted'}