from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "polymarket.db"

engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(bind=engine)

