from sqlalchemy import Table, Column, BigInteger, ForeignKey
from database import Base

roledevices = Table(
    'roledevices',
    Base.metadata,
    Column('roleid', BigInteger, ForeignKey('roles.id'), primary_key=True),
    Column('deviceid', BigInteger, ForeignKey('devices.id'), primary_key=True),
)
