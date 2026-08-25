from sqlalchemy.orm import Session
from models.user import User
from schemas.user import UserCreate, UserUpdate
from datetime import datetime
from core import security

def get_users(db: Session):
    return db.query(User).all()

def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.Id == user_id).first()

def create_user(db: Session, user: UserCreate):
    db_user = User(
        Account = user.Account,
        Name = user.Name,
        Email = user.Email,
        Pwd = security.get_password_hash(user.Pwd),
        IsActive = user.IsActive,
        RoleId = user.RoleId,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id:int, user: UserUpdate):
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    for key, value in user.dict(exclude_unset=True).items():
        if key == 'Pwd' and value:
            value = security.get_password_hash(value)
        setattr(db_user, key, value)
    db_user.UpdatedDate = datetime.utcnow()
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    db_user = get_user(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user