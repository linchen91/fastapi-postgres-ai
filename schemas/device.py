from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DeviceBase(BaseModel):
    Code: str
    Name: Optional[str] = None
    DeviceType: Optional[str] = None
    Params: Optional[str] = None
    Lat: Optional[float] = None
    Lng: Optional[float] = None
    IsActive: Optional[bool] = None
    Status: Optional[str] = None

class DeviceCreate(DeviceBase):
    pass

class DeviceUpdate(DeviceBase):
    pass

class DeviceOut(DeviceBase):
    Id: int
    CreatedDate: Optional[datetime]
    UpdatedDate: Optional[datetime]
    
    class Config:
        from_attributes = True
