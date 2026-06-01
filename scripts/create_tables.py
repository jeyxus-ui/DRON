from backend.db.database import engine
from backend.db.models import Base

def create_tables():
    Base.metadata.create_all(bind=engine)
    print("Tables created")

if __name__ == "__main__":
    create_tables()