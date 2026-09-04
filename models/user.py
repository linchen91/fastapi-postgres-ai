from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = 'users'

    Id = Column('id', Integer, primary_key=True, index=True)
    Account = Column('account', String(50), unique=True, index=True, nullable=False)
    Name = Column('name', String(50))
    Email = Column('email', String(50))
    Pwd = Column('pwd', String(200), nullable=False)
    IsActive = Column('isactive', Boolean, default=True)
    RoleId = Column('roleid', BigInteger)
    CreatedDate = Column('createddate', DateTime, default=datetime.utcnow)
    UpdatedDate = Column('updateddate', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)