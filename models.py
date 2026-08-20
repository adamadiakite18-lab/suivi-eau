from sqlalchemy import Column, Integer, String, Text, DateTime
from database import Base
from datetime import datetime

class Entry(Base):
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True, index=True)
    project_slug = Column(String, index=True)
    form_ref = Column(String)
    ec5_uuid = Column(String, unique=True, index=True)
    created_at = Column(String)
    data = Column(Text)  # On stocke toutes les données en JSON texte
    synced_at = Column(DateTime, default=datetime.utcnow)