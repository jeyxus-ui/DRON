from sqlalchemy import Column, Integer, Float, Boolean, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True)
    altitude = Column(Float)
    speed = Column(Float)
    pitch = Column(Float)
    roll = Column(Float)
    yaw = Column(Float)
    battery = Column(Float)
    timestamp = Column(TIMESTAMP, default=datetime.datetime.utcnow)
