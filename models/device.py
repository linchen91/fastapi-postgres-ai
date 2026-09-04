from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric
from datetime import datetime
from database import Base
from sqlalchemy.orm import relationship
from models.roledevice import roledevices

class Device(Base):
    __tablename__ = 'devices'
    
    Id = Column('id', Integer, primary_key=True, index=True)
    Code = Column('code', String(50), unique=True, index=True)
    Name = Column('name', String(50))
    DeviceType = Column('devicetype', String(20))
    Params = Column('params', String(200))
    Lat = Column('lat', Numeric(9, 6))
    Lng = Column('lng', Numeric(9, 6))
    IsActive = Column('isactive', Boolean, default=True)
    Status = Column('status', String(20))
    CreatedDate = Column('createddate', DateTime, default=datetime.utcnow)
    UpdatedDate = Column('updateddate', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    Roles = relationship(
        'Role',
        secondary=roledevices,
        back_populates='Devices'
    )