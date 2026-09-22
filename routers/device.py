from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from database import get_db
from crud import device as crud_device
from schemas import device as schemas_device
from typing import Optional

router = APIRouter()

@router.get('/', response_model=list[schemas_device.DeviceOut])
async def read_devices(user_account: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await crud_device.get_devices(db, user_account)

@router.get('/{device_id}', response_model=schemas_device.DeviceOut)
async def read_device(device_id:int, db: AsyncSession = Depends(get_db)):
    device = await crud_device.get_device(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail='Device not found')
    return device

@router.post('/', response_model=schemas_device.DeviceOut)
async def create_device(device: schemas_device.DeviceCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await crud_device.create_device(db, device)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f'Device with code "{device.Code}" already exists')

@router.put('/{device_id}', response_model=schemas_device.DeviceOut)
async def update_device(device_id:int, device: schemas_device.DeviceUpdate, db: AsyncSession = Depends(get_db)):
    updated = await crud_device.update_device(db, device_id, device)
    if not updated:
        raise HTTPException(status_code=404, detail='Device not found')
    return updated

@router.delete('/{device_id}')
async def delete_device(device_id:int, db: AsyncSession = Depends(get_db)):
    deleted = await crud_device.delete_device(db, device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='Device not found')
    return {'message': 'Device deleted'}