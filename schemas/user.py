from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    Account: str
    Name: Optional[str] = None
    Email: Optional[str] = None
    IsActive: Optional[bool] = None
    RoleId: Optional[int] = None

class UserCreate(UserBase):
    Pwd: str

class UserUpdate(BaseModel):
    Account: Optional[str] = None
    Name: Optional[str] = None
    Email: Optional[str] = None
    Pwd: Optional[str] = None
    IsActive: Optional[bool] = None
    RoleId: Optional[int] = None

class UserOut(UserBase):
    Id: int
    CreatedDate: Optional[datetime] = None
    UpdatedDate: Optional[datetime] = None

    class Config:
        from_attributes = True