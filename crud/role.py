from sqlalchemy.orm import Session, joinedload
from sqlalchemy import delete
from models.role import Role
from models.device import Device
from models.roledevice import roledevices
from datetime import datetime

def get_all_roles(db: Session):
    return db.query(Role).options(joinedload(Role.Devices)).all()

def get_role_by_id(db: Session, role_id: int):
    return db.query(Role).options(joinedload(Role.Devices)).filter(Role.Id==role_id).first()

def create_role(db: Session, name: str, device_ids: list[int]):
    now = datetime.utcnow()
    new_role = Role(Name=name, CreatedDate=now, UpdatedDate=now)
    db.add(new_role)
    db.commit()
    db.refresh(new_role)

    insert_values = [{'roleid': new_role.Id, 'deviceid': d} for d in device_ids]
    if insert_values:
        db.execute(roledevices.insert(), insert_values)
        db.commit()
    return new_role

def update_role(db: Session, role_id: int, name: str, device_ids: list[int]):
    role = db.query(Role).filter(Role.Id==role_id).first()
    if not role:
        return None

    role.Name = name
    role.UpdatedDate = datetime.utcnow()
    db.commit()

    db.execute(delete(roledevices).where(roledevices.c.roleid == role_id))
    db.commit()

    insert_values = [{'roleid': role_id, 'deviceid': d} for d in device_ids]
    if insert_values:
        db.execute(roledevices.insert(), insert_values)
        db.commit()
    return role

def delete_role(db: Session, role_id: int):
    db.execute(delete(roledevices).where(roledevices.c.roleid == role_id))
    db.execute(delete(Role).where(Role.Id == role_id))
    db.commit()
