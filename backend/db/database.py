from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.config import DB_URL

# Use PostgreSQL only (configured via env var). Enable pool_pre_ping to avoid stale connections
engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
# Explicit sessionmaker settings for clarity
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
