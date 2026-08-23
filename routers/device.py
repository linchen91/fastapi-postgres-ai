from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from crud import device as crud_device
from schemas import device as schemas_device

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get('/', response_model=list[schemas_device.DeviceOut])
def read_devices(db: Session = Depends(get_db)):
    return crud_device.get_devices(db)

@router.get('/{device_id}', response_model=schemas_device.DeviceOut)
def read_device(device_id:int, db: Session = Depends(get_db)):
    device = crud_device.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail='Device not found')
    return device

@router.post('/', response_model=schemas_device.DeviceOut)
def create_device(device: schemas_device.DeviceCreate, db: Session = Depends(get_db)):
    return crud_device.create_device(db, device)

@router.put('/{device_id}', response_model=schemas_device.DeviceOut)
def update_device(device_id:int, device: schemas_device.DeviceUpdate, db: Session = Depends(get_db)):
    updated = crud_device.update_device(db, device_id, device)
    if not updated:
        raise HTTPException(status_code=404, detail='Device not found')
    return updated

@router.delete('/{device_id}')
def delete_device(device_id:int, db: Session = Depends(get_db)):
    deleted = crud_device.delete_device(db, device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='Device not found')
    return {'message': 'Device deleted'}