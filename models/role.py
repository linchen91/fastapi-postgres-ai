from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from sqlalchemy.orm import relationship
from database import Base
from models.roledevice import roledevices

class Role(Base):
    __tablename__ = 'roles'

    Id = Column('id', Integer, primary_key=True, index=True)
    Name = Column('name', String(50))
    CreatedDate = Column('createddate', DateTime, default=datetime.utcnow)
    UpdatedDate = Column('updateddate', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    Devices = relationship(
        'Device',
        secondary=roledevices,
        back_populates='Roles'
    )
