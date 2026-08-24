from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from database import Base
from models.roledevice import roledevices

class Role(Base):
    __tablename__ = 'roles'

    Id = Column(Integer, primary_key=True)
    Name = Column(String(50))
    CreatedDate = Column(DateTime)
    UpdatedDate = Column(DateTime)
    
    Devices = relationship(
        'Device',
        secondary=roledevices,
        back_populates='Roles'
    )
