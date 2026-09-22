from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.device import Device
from models.user import User
from models.roledevice import  roledevices
from schemas.device import DeviceCreate, DeviceUpdate
from datetime import datetime

async def get_devices(db: AsyncSession, user_account: str = None):
    if user_account:
        result = await db.execute(select(User.RoleId).where(User.Account == user_account))
        role_id = result.scalar()
        if role_id is None:
            return []
        stmt = (
            select(Device)
            .join(roledevices, Device.Id == roledevices.c.deviceid)
            .where(roledevices.c.roleid == role_id)
        )
        result = await db.execute(stmt)
        return result.scalars().all()
    result = await db.execute(select(Device))
    return result.scalars().all()

async def get_device(db: AsyncSession, device_id: int):
    result = await db.execute(select(Device).where(Device.Id == device_id))
    return result.scalars().first()

async def create_device(db: AsyncSession, device: DeviceCreate):
    db_device = Device(**device.dict())
    db.add(db_device)
    await db.commit()
    await db.refresh(db_device)
    return db_device

async def update_device(db: AsyncSession, device_id: int, device: DeviceUpdate):
    db_device = await get_device(db, device_id)
    if not db_device:
        return None
    for key, value in device.dict(exclude_unset=True).items():
        setattr(db_device, key, value)
    await db.commit()
    await db.refresh(db_device)
    return db_device

async def delete_device(db: AsyncSession, device_id: int):
    db_device = await get_device(db, device_id)
    if db_device:
        db.delete(db_device)
        await db.commit()
    return db_device
