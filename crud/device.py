from sqlalchemy.orm import Session
from sqlalchemy import select
from models.device import Device
from models.user import User
from models.roledevice import  roledevices
from schemas.device import DeviceCreate, DeviceUpdate
from datetime import datetime

def get_devices(db: Session, user_account: str = None):
    if user_account:
        role_id = db.query(User.RoleId).filter(User.Account == user_account).scalar()
        if role_id is None:
            return []
        stmt = (
            select(Device)
            .join(roledevices, Device.Id == roledevices.c.deviceid)
            .where(roledevices.c.roleid == role_id)
        )
        return db.execute(stmt).scalars().all()
    return db.query(Device).all()

def get_device(db: Session, device_id: int):
    return db.query(Device).filter(Device.Id == device_id).first()

def create_device(db: Session, device: DeviceCreate):
    db_device = Device(**device.dict())
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device

def update_device(db: Session, device_id: int, device: DeviceUpdate):
    db_device = get_device(db, device_id)
    if not db_device:
        return None
    for key, value in device.dict(exclude_unset=True).items():
        setattr(db_device, key, value)
    db.commit()
    db.refresh(db_device)
    return db_device

def delete_device(db: Session, device_id: int):
    db_device = get_device(db, device_id)
    if db_device:
        db.delete(db_device)
        db.commit()
    return db_device
