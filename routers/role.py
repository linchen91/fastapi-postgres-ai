from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from schemas.role import RoleDto, RoleCreateDto, RoleUpdateDto
from crud.role import (
    get_all_roles, get_role_by_id, create_role, update_role, delete_role
)

router = APIRouter()

@router.get('/', response_model=list[RoleDto])
async def read_roles(db: AsyncSession = Depends(get_db)):
    return await get_all_roles(db)

@router.get('/{role_id}', response_model=RoleDto)
async def read_role(role_id: int, db: AsyncSession = Depends(get_db)):
    role = await get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=404, detail='Role not found')
    return role

@router.post('/', response_model=RoleDto)
async def create_new_role(role_data: RoleCreateDto, db: AsyncSession = Depends(get_db)):
    return await create_role(db, role_data.Name, role_data.DeviceIds)

@router.put('/{role_id}', response_model=RoleDto)
async def update_existing_role(role_id: int, role_data: RoleUpdateDto, db: AsyncSession = Depends(get_db)):
    updated = await update_role(db, role_id, role_data.Name, role_data.DeviceIds)
    if not updated:
        raise HTTPException(status_code=404, detail='Role not found')
    return await get_role_by_id(db, role_id)

@router.delete('/{role_id}')
async def delete_role_by_id(role_id: int, db: AsyncSession = Depends(get_db)):
    await delete_role(db, role_id)
    return {'message': 'Role deleted'}