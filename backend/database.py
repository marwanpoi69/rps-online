from sqlmodel import create_engine, SQLModel
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///./rps_game.db"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=True  # Log all SQL statements
)

def create_db_and_tables():
    try:
        logger.info("Creating database tables...")
        SQLModel.metadata.create_all(engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {str(e)}")
        raise
