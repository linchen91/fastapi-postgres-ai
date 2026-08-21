from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = 'users'

    Id = Column(Integer, primary_key=True, index=True)
    Account = Column(String(45), unique=True, index=True, nullable=False)
    Name = Column(String(45))
    Email = Column(String(45))
    Pwd = Column(String(200))
    IsActive = Column(Boolean, default=True)
    RoleId = Column(Integer)
    CreatedDate = Column(DateTime, default=datetime.utcnow)
    UpdatedDate = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)