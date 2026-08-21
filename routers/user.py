from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from crud import user as crud_user
from schemas import user as schemas_user

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get('/', response_model=list[schemas_user.UserOut])
def read_users(db: Session = Depends(get_db)):
    return crud_user.get_users(db)

@router.get('/{user_id}', response_model=schemas_user.UserOut)
def read_user(user_id:int, db: Session = Depends(get_db)):
    user =  crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return user

@router.post('/', response_model=schemas_user.UserOut)
def create_user(user: schemas_user.UserCreate, db: Session = Depends(get_db)):
    return crud_user.create_user(db, user)

@router.put('/{user_id}', response_model=schemas_user.UserOut)
def update_user(user_id:int, user: schemas_user.UserUpdate, db: Session = Depends(get_db)):
    updated = crud_user.update_user(db, user_id, user)
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    return updated

@router.delete('/{user_id}')
def delete_user(user_id:int, db: Session = Depends(get_db)):
    deleted = crud_user.delete_user(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='User not found')
    return {'message': 'User deleted'}