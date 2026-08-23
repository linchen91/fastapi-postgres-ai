from sqlalchemy import Column, Integer, String, Boolean, DateTime, DECIMAL
from datetime import datetime
from database import Base

class Device(Base):
    __tablename__ = 'devices'
    
    Id = Column(Integer, primary_key=True, index=True)
    Code = Column(String(50), unique=True, index=True)
    Name = Column(String(50))
    DeviceType = Column(String(20))
    Params = Column(String(200))
    Lat = Column(DECIMAL(9, 6))
    Lng = Column(DECIMAL(9, 6))
    IsActive = Column(Boolean, default=True)
    Status = Column(String(20))
    CreatedDate = Column(DateTime, default=datetime.utcnow)