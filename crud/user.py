from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User
from schemas.user import UserCreate, UserUpdate
from datetime import datetime
from core import security

async def get_users(db: AsyncSession):
    result = await db.execute(select(User))
    return result.scalars().all()

async def get_user(db: AsyncSession, user_id: int):
    result = await db.execute(select(User).where(User.Id == user_id))
    return result.scalars().first()

async def create_user(db: AsyncSession, user: UserCreate):
    db_user = User(
        Account = user.Account,
        Name = user.Name,
        Email = user.Email,
        Pwd = security.get_password_hash(user.Pwd),
        IsActive = user.IsActive,
        RoleId = user.RoleId,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user(db: AsyncSession, user_id:int, user: UserUpdate):
    db_user = await get_user(db, user_id)
    if not db_user:
        return None
    for key, value in user.dict(exclude_unset=True).items():
        if key == 'Pwd' and value:
            value = security.get_password_hash(value)
        setattr(db_user, key, value)
    db_user.UpdatedDate = datetime.utcnow()
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def delete_user(db: AsyncSession, user_id: int):
    db_user = await get_user(db, user_id)
    if db_user:
        db.delete(db_user)
        await db.commit()
    return db_user
