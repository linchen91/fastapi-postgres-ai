from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from models.role import Role
from models.device import Device
from models.roledevice import roledevices
from datetime import datetime

async def get_all_roles(db: AsyncSession):
    result = await db.execute(select(Role).options(joinedload(Role.Devices)))
    return result.unique().scalars().all()

async def get_role_by_id(db: AsyncSession, role_id: int):
    result = await db.execute(select(Role).options(joinedload(Role.Devices)).where(Role.Id==role_id))
    return result.unique().scalars().first()

async def create_role(db: AsyncSession, name: str, device_ids: list[int]):
    now = datetime.utcnow()
    new_role = Role(Name=name, CreatedDate=now, UpdatedDate=now)
    db.add(new_role)
    await db.commit()
    await db.refresh(new_role)

    insert_values = [{'roleid': new_role.Id, 'deviceid': d} for d in device_ids]
    if insert_values:
        await db.execute(roledevices.insert(), insert_values)
        await db.commit()
    return new_role

async def update_role(db: AsyncSession, role_id: int, name: str, device_ids: list[int]):
    result = await db.execute(select(Role).where(Role.Id==role_id))
    role = result.scalars().first()
    if not role:
        return None

    role.Name = name
    role.UpdatedDate = datetime.utcnow()
    await db.commit()

    await db.execute(delete(roledevices).where(roledevices.c.roleid == role_id))
    await db.commit()

    insert_values = [{'roleid': role_id, 'deviceid': d} for d in device_ids]
    if insert_values:
        await db.execute(roledevices.insert(), insert_values)
        await db.commit()
    return role

async def delete_role(db: AsyncSession, role_id: int):
    await db.execute(delete(roledevices).where(roledevices.c.roleid == role_id))
    await db.execute(delete(Role).where(Role.Id == role_id))
    await db.commit()
