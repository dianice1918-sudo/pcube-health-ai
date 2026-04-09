from .database import engine, Base
from . import models  # Import all models to register them with Base
import os


def create_tables(reset: bool = False):
    if reset:
        Base.metadata.drop_all(bind=engine)
        print("Dropped all existing tables.")

    Base.metadata.create_all(bind=engine)
    print("All tables created successfully.")

if __name__ == "__main__":
    create_tables(reset=os.getenv("RESET_DB", "false").lower() == "true")




