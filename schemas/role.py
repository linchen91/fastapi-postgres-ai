from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class RoleCreateDto(BaseModel):
    Name: str
    DeviceIds: Optional[list[int]] = []


class RoleUpdateDto(BaseModel):
    Name: str
    DeviceIds: Optional[list[int]] = []

class DeviceDto(BaseModel):
    Id: int
    Code: str
    Name: str
    DeviceType: str
    Params: Optional[str] = None
    Lat: float
    Lng: float
    IsActive: bool
    Status: Optional[str] = None
    CreatedDate: datetime
    UpdatedDate: datetime

    class Config:
        from_attributes = True

class RoleDto(BaseModel):
    Id: int
    Name: str
    Devices: list[DeviceDto] = []
    CreatedDate: datetime
    UpdatedDate: datetime

    class Config:
        from_attributes = True
