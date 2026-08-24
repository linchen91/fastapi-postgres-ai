from sqlalchemy import Table, Column, Integer, ForeignKey
from database import Base

roledevices = Table(
    'roledevices',
    Base.metadata,
    Column('Id', Integer, primary_key=True),
    Column('RoleId', Integer, ForeignKey('roles.Id')),
    Column('DeviceId', Integer, ForeignKey('devices.Id'))
)
